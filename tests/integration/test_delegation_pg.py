"""Delegation against a real Postgres: the fifth statement, and the three things that commit with
the append (§5.10, §7.6).

`tests/unit/test_delegation.py` proves the runtime is right on the MemoryJournal. These prove the
statements the two backends can disagree on: the spawn transaction's four rows, the `child_result`
row committed with the child's terminal event, the `delegations_contract_key` index, and the
takeover UPDATE with its grace judged by `now()` on the server.

    docker compose up -d postgres
    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import timedelta
from typing import Any

import pytest
from psycopg.rows import dict_row

from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.server import WorldServer
from keel import Keel
from keel.agents import demo
from keel.core.ids import uuid7
from keel.journal.postgres import PostgresJournal
from keel.journal.protocol import SignalRow
from keel.providers.scripted import ScriptedProvider
from keel.state.fold import fold

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = 2.0
GRACE = 0.5


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
async def world(monkeypatch: pytest.MonkeyPatch):
    w = build_world()
    server = WorldServer(w, port=0)
    await server.start()
    monkeypatch.setattr(demo, "WORLD_URL", server.base_url)
    try:
        yield w
    finally:
        await server.stop()


def _keel(journal: PostgresJournal) -> Keel:
    return Keel(
        journal=journal,
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue_tool("EXTERNAL")],
        programs=[demo.tool_chain, demo.orchestrator, demo.research_child],
    )


async def _acquire(k: Keel, run_id: Any, worker_id: str) -> None:
    lease = await k.journal.acquire(run_id, worker_id, timedelta(seconds=TTL))
    assert lease is not None, f"{worker_id} could not acquire {run_id}"
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL, cancel_grace=GRACE).execute(lease)


async def _rows(journal: PostgresJournal, sql: str, *args: Any) -> list[dict[str, Any]]:
    pool = await journal._ready()
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, args)
        return await cur.fetchall()


async def test_the_spawn_commits_four_rows_or_none(journal, world) -> None:
    k = _keel(journal)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")

    runs = await _rows(journal, "SELECT * FROM runs WHERE parent_run_id = %s ORDER BY created_at", handle.run_id)
    assert len(runs) == 2 and all(r["phase"] == "CREATED" and r["runnable_at"] is not None for r in runs)
    born = await _rows(journal, "SELECT run_id, lease_epoch, type FROM events WHERE run_id = ANY(%s)",
                       [r["run_id"] for r in runs])
    assert sorted((b["type"], b["lease_epoch"]) for b in born) == [("RUN_CREATED", 0), ("RUN_CREATED", 0)]
    rows = await journal.delegations(handle.run_id)
    assert [(d.child_ordinal, d.retry_no, d.status) for d in rows] == [(0, 0, "SPAWNED"), (1, 0, "SPAWNED")]
    parent = await journal.run_row(handle.run_id)
    assert parent.phase == "WAITING_CHILDREN" and parent.lease_expires_at is None and parent.runnable_at is None

    # The natural key is a real index: a second row for (parent, step, ordinal, retry) is refused.
    import psycopg

    with pytest.raises(psycopg.errors.UniqueViolation):
        pool = await journal._ready()
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO delegations (delegation_id, parent_run_id, parent_step_index, child_run_id,"
                " role, contract, budget_reserved, status, spawned_seq, child_ordinal, retry_no)"
                " VALUES (%s, %s, 0, %s, 'worker', '{}', '{}', 'SPAWNED', 1, 0, 0)",
                (uuid7(), handle.run_id, runs[0]["run_id"]),
            )


async def test_the_child_result_commits_with_the_terminal_event_and_wakes_the_parent(journal, world) -> None:
    k = _keel(journal)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")
    a, b = await journal.children(handle.run_id)

    await _acquire(k, a.run_id, "ca")
    [wake] = await _rows(journal, "SELECT * FROM signals WHERE run_id = %s", handle.run_id)
    assert wake["type"] == "child_result" and wake["client_key"] == f"child_result:{a.run_id}"
    assert (await journal.run_row(handle.run_id)).runnable_at is not None, "the row is the wake"

    await _acquire(k, b.run_id, "cb")
    await _acquire(k, handle.run_id, "w2")
    state = fold(await journal.read(handle.run_id))
    assert state.phase == "COMPLETED", state.error
    assert [r["status"] for r in state.steps[0].result] == ["completed", "completed"]
    assert all(d.status == "COMPLETED" and d.settled_seq for d in await journal.delegations(handle.run_id))
    assert await journal.pending_signals(handle.run_id) == []


async def test_takeover_is_refused_inside_the_grace_and_goes_through_after_it(journal, world) -> None:
    """The fifth statement, with the grace judged by the server's `now()`. Nothing sleeps on the
    worker's clock: the parent's wake comes from the timer sweep on `wake_at`."""
    k = _keel(journal)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")
    a, b = await journal.children(handle.run_id)
    await _acquire(k, a.run_id, "ca")

    assert await journal.insert_signal(
        SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="cancel", payload={"by": "test"})
    )
    await _acquire(k, handle.run_id, "w2")
    parent = fold(await journal.read(handle.run_id))
    assert parent.phase == "WAITING_CHILDREN" and parent.cancel_acknowledged_at == 0
    [told] = await journal.pending_signals(b.run_id)
    assert told.type == "cancel"

    assert await journal.takeover(b.run_id, "eager", timedelta(seconds=TTL), cancel_grace=timedelta(seconds=GRACE)) is None
    assert (await journal.run_row(b.run_id)).lease_epoch == 0, "refused: the child has not had its grace"

    await asyncio.sleep(GRACE + 0.3)
    assert await journal.sweep_timers() == 1
    await _acquire(k, handle.run_id, "w3")

    child = fold(await journal.read(b.run_id))
    assert child.phase == "CANCELLED" and child.forced_by == f"parent:{handle.run_id}"
    [rec] = await journal.recoveries(b.run_id)
    assert rec.cause == "ORPHANED" and rec.outcome == "FORCED_CANCEL"
    parent = fold(await journal.read(handle.run_id))
    assert parent.phase == "CANCELLED" and parent.steps[0].state == "CANCELLED"
    assert parent.children[b.run_id].state == "CANCELLED"
    assert await journal.stray_children() == []


async def test_takeover_honours_an_open_non_pure_attempt_deadline(journal, world) -> None:
    """The same `attempt_deadline` bound the reaper applies: a child mid-request is not jumped."""
    k = _keel(journal)
    handle = await k.start(demo.orchestrator, {"tasks": ["a"]})
    await _acquire(k, handle.run_id, "w1")
    [child] = await journal.children(handle.run_id)
    await journal.insert_signal(SignalRow(signal_id=uuid7(), run_id=child.run_id, type="cancel", payload={}))
    pool = await journal._ready()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE runs SET attempt_deadline = now() + interval '1 minute' WHERE run_id = %s", (child.run_id,)
        )
    await asyncio.sleep(0.1)
    assert await journal.takeover(child.run_id, "w", timedelta(seconds=TTL), cancel_grace=timedelta(0)) is None
    async with pool.connection() as conn:
        await conn.execute("UPDATE runs SET attempt_deadline = NULL WHERE run_id = %s", (child.run_id,))
    lease = await journal.takeover(child.run_id, "w", timedelta(seconds=TTL), cancel_grace=timedelta(0))
    assert lease is not None and lease.cause == "ORPHANED" and lease.epoch == 1
