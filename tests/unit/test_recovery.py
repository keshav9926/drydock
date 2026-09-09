"""Day 1's "done when": kill the worker mid-run, start another, and the journal shows two work
sessions, every earlier step reused from the record, and zero model calls repeated (§28.1).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from keel import Budget, Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider


TTL = 2.0


class CountingProvider(ScriptedProvider):
    """A model that answers from request content only — and counts, so the test can assert that a
    recovered run does not re-ask a question it already has an answer to."""

    def __init__(self, script) -> None:
        super().__init__(script)
        self.calls = 0

    async def complete(self, req):
        self.calls += 1
        return await super().complete(req)


@pytest.fixture
def sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "world.jsonl"
    monkeypatch.setattr(demo, "SINK", path)
    return path


def receipts(sink: Path) -> list[dict]:
    if not sink.exists():
        return []
    return [json.loads(x) for x in sink.read_text(encoding="utf8").splitlines() if x.strip()]


def _keel(clock: FakeClock, provider) -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=provider,
        tools=[demo.search, demo.create_issue],
        programs=[demo.tool_chain],
        clock=clock,
    )


async def test_clean_run(sink: Path) -> None:
    clock = FakeClock()
    provider = CountingProvider(demo.SCRIPT)
    k = _keel(clock, provider)
    result = await k.run(demo.tool_chain, {"task": "file an issue"}, budget=Budget(max_tokens=50_000))
    assert result.phase == "COMPLETED"
    assert result.result == {"answer": "filed the issue"}
    assert provider.calls == 3
    assert len(receipts(sink)) == 1


async def test_crash_after_effect_resumes_without_redeciding(sink: Path) -> None:
    clock = FakeClock()
    provider = CountingProvider(demo.SCRIPT)
    k = _keel(clock, provider)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    # --- epoch 1: run until create_issue has landed at the receiver, then die -----------
    w1 = k.worker(worker_id="w1", lease_ttl=TTL)
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    assert lease is not None
    task = asyncio.create_task(w1.execute(lease))
    for _ in range(200):
        if receipts(sink):
            break
        await asyncio.sleep(0.005)
    assert receipts(sink), "the effect never landed; nothing to be ambiguous about"
    task.cancel()  # SIGKILL-shaped: no release, no outcome event
    with contextlib.suppress(asyncio.CancelledError):
        await task
    calls_before = provider.calls
    assert calls_before == 2

    events = await k.events(handle.run_id)
    assert [e.type for e in events][-1] == "STEP_ATTEMPT_STARTED"  # STARTED, no outcome

    # --- the lease lapses, the reaper orphans, a successor claims ----------------------
    clock.advance(TTL + 1 + 1)  # past both lease_expires_at and attempt_deadline
    assert await k.journal.reap() == [handle.run_id]
    lease2 = await k.journal.claim("w2", timedelta(seconds=TTL))
    assert lease2 is not None
    assert lease2.cause == "ORPHANED"
    assert lease2.epoch == lease.epoch + 1

    # --- epoch 2: memoized re-execution, then the ambiguity is resolved, not guessed ---
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(lease2)

    view = await k.get(handle.run_id)
    assert view.phase == "COMPLETED"
    assert len(receipts(sink)) == 1, "the recovered run must not fire the effect twice"
    assert provider.calls == calls_before + 1, "only the one live model step may be asked"

    kinds = [(s.step_index, s.kind, s.state, s.origin) for s in view.steps]
    assert kinds[0] == (0, "MODEL", "COMPLETED", "memo")
    assert kinds[1] == (1, "TOOL", "COMPLETED", "memo")
    assert kinds[2] == (2, "MODEL", "COMPLETED", "memo")
    assert kinds[3] == (3, "TOOL", "RESOLVED_COMPLETED", "recovered")
    assert kinds[4] == (4, "MODEL", "COMPLETED", "live")

    types = [e.type for e in await k.events(handle.run_id)]
    assert types.count("RECOVERY_STARTED") == 2, "two work sessions"
    assert "STEP_AMBIGUOUS" in types
    assert "STEP_RESOLVED" in types
    assert types.count("STEP_COMPLETED") == 4  # steps 0,1,2 and the live 4 — step 3 is RESOLVED

    effect = next(e for e in view.effects if e.step_index == 3)
    assert effect.status == "RESOLVED_COMMITTED"
    assert effect.resolution == "probe"
    assert effect.external_ref == "issue#1"


async def test_escalate_suspends_instead_of_guessing(sink: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no probe, an ambiguous EXTERNAL effect is surfaced, never silently retried (L3)."""
    clock = FakeClock()
    k = _keel(clock, CountingProvider(demo.SCRIPT))
    monkeypatch.setattr(demo.create_issue, "resolution", "escalate")
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    w1 = k.worker(worker_id="w1", lease_ttl=TTL)
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    task = asyncio.create_task(w1.execute(lease))
    for _ in range(200):
        if receipts(sink):
            break
        await asyncio.sleep(0.005)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    clock.advance(TTL + 2)
    await k.journal.reap()
    lease2 = await k.journal.claim("w2", timedelta(seconds=TTL))
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(lease2)

    view = await k.get(handle.run_id)
    assert view.phase == "SUSPENDED"
    assert view.suspended_reason == "resolved_unknown"
    assert view.steps[3].state == "RESOLVED_UNKNOWN"
    assert len(receipts(sink)) == 1
