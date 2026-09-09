"""The same day-1 claims, against a real Postgres.

The MemoryJournal tests prove the *runtime* is right; these prove the four control-plane statements
are right, which is the only place the two can disagree. Skipped without a DSN:

    docker compose up -d postgres
    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

from keel import Keel
from keel.agents import demo
from keel.core.errors import Fenced
from keel.events import RunSuspended
from keel.journal.postgres import PostgresJournal
from keel.providers.scripted import ScriptedProvider

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = timedelta(seconds=2)


@pytest.fixture
async def journal():
    j = PostgresJournal(DSN)
    await j.migrate()
    pool = await j._ready()
    async with pool.connection() as conn:
        await conn.execute(
            "TRUNCATE artifacts, replays, recoveries, delegations, signals, effects, events,"
            " runs, blobs, programs RESTART IDENTITY CASCADE"
        )
    yield j
    await j.close()


@pytest.fixture
def sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "world.jsonl"
    monkeypatch.setattr(demo, "SINK", path)
    return path


def receipts(sink: Path) -> list[dict]:
    if not sink.exists():
        return []
    return [json.loads(x) for x in sink.read_text(encoding="utf8").splitlines() if x.strip()]


def _keel(journal) -> Keel:
    return Keel(
        journal=journal,
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue],
        programs=[demo.tool_chain],
    )


async def test_two_workers_one_run_only_one_appends(journal) -> None:
    k = _keel(journal)
    handle = await k.start(demo.tool_chain, {"task": "t"})
    first = await journal.claim("w1", TTL)
    assert first is not None and first.run_id == handle.run_id
    assert await journal.claim("w2", TTL) is None, "a live lease is not claimable"

    await asyncio.sleep(TTL.total_seconds() + 0.2)
    assert await journal.reap() == [handle.run_id]
    second = await journal.claim("w2", TTL)
    assert second is not None
    assert second.epoch == first.epoch + 1
    assert second.cause == "ORPHANED"

    with pytest.raises(Fenced):
        async with journal.append(first) as tx:
            await tx.append(RunSuspended(reason="zombie"))
    async with journal.append(second) as tx:
        await tx.append(RunSuspended(reason="successor"))

    events = await journal.read(handle.run_id)
    assert [e.type for e in events] == ["RUN_CREATED", "RUN_SUSPENDED"]
    assert events[-1].body.reason == "successor"


async def test_clean_run(journal, sink: Path) -> None:
    k = _keel(journal)
    result = await k.run(demo.tool_chain, {"task": "file an issue"})
    assert result.phase == "COMPLETED"
    assert len(receipts(sink)) == 1
    row = await journal.run_row(result.run_id)
    assert row.phase == "COMPLETED" and row.terminal_at is not None
    assert row.lease_expires_at is None


async def test_crash_after_effect_resumes_without_redeciding(journal, sink: Path) -> None:
    k = _keel(journal)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    lease = await journal.claim("w1", TTL)
    task = asyncio.create_task(k.worker(worker_id="w1", lease_ttl=2.0).execute(lease))
    for _ in range(400):
        if receipts(sink):
            break
        await asyncio.sleep(0.005)
    assert receipts(sink)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # wait past max(lease_expires_at, attempt_deadline) — the reaper's one predicate
    await asyncio.sleep(TTL.total_seconds() + 1.2)
    assert await journal.reap() == [handle.run_id]
    lease2 = await journal.claim("w2", TTL)
    assert lease2 is not None and lease2.cause == "ORPHANED"
    await k.worker(worker_id="w2", lease_ttl=2.0).execute(lease2)

    view = await k.get(handle.run_id)
    assert view.phase == "COMPLETED"
    assert len(receipts(sink)) == 1
    assert [(s.step_index, s.state, s.origin) for s in view.steps] == [
        (0, "COMPLETED", "memo"),
        (1, "COMPLETED", "memo"),
        (2, "COMPLETED", "memo"),
        (3, "RESOLVED_COMPLETED", "recovered"),
        (4, "COMPLETED", "live"),
    ]
    recs = await journal.recoveries(handle.run_id)
    assert [r.cause for r in recs] == ["START", "ORPHANED"]
    assert recs[0].outcome == "CRASHED"  # written retroactively by the next acquirer
    assert recs[1].outcome == "TERMINAL"


async def test_duplicate_effect_key_is_loud(journal) -> None:
    """The effects PK turns 'the runtime issued the same effect twice' into a unique violation at
    INTENT commit — loud, transactional, impossible to skip silently (§5.5)."""
    from keel.core.errors import DuplicateEffectKey
    from keel.journal.protocol import EffectRow

    k = _keel(journal)
    handle = await k.start(demo.tool_chain, {"task": "t"})
    lease = await journal.claim("w1", TTL)
    async with journal.append(lease) as tx:
        seq = await tx.append(RunSuspended(reason="anchor"))
        row = EffectRow(
            effect_key="a" * 32,
            run_id=handle.run_id,
            run_root_id=handle.run_id,
            step_index=0,
            tool="t",
            effect_class="EXTERNAL",
            status="INTENDED",
            intent_seq=seq,
        )
        await tx.write_effect(row)
    with pytest.raises(DuplicateEffectKey):
        async with journal.append(lease) as tx:
            seq = await tx.append(RunSuspended(reason="second"))
            await tx.write_effect(
                EffectRow(
                    effect_key="a" * 32,
                    run_id=handle.run_id,
                    run_root_id=handle.run_id,
                    step_index=1,
                    tool="t",
                    effect_class="EXTERNAL",
                    status="INTENDED",
                    intent_seq=seq,
                )
            )
