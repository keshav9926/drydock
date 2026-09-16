"""The inbox, approvals and pause against a real Postgres (§5.4, §16.6, §18.4).

`tests/unit/test_{inbox,approvals}.py` prove the runtime on the MemoryJournal. These prove the
statements the two backends can disagree on — and the post-phase-8 audit found they did: the release
guarded by `runnable_at IS NULL` inside the waiting transaction, the claim that reads the inbox and
respects `paused_at`, the timer sweep that skips a held run, and the `signals.type` CHECK surfacing as
a KeelError rather than a driver traceback.

    docker compose up -d postgres
    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import contextlib
import os
from datetime import timedelta
from typing import Any

import pytest

from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.server import WorldServer
from keel import Keel
from keel.agents import demo
from keel.core.errors import IllegalTransition
from keel.core.ids import uuid7
from keel.journal.postgres import PostgresJournal
from keel.journal.protocol import SignalRow
from keel.providers.scripted import ScriptedProvider
from keel.state.fold import fold

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = 2.0


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
        programs=[demo.tool_chain, demo.gated_tool_chain, demo.orchestrator, demo.research_child],
    )


def _row(run_id: Any, type_: str, **payload: Any) -> SignalRow:
    return SignalRow(signal_id=uuid7(), run_id=run_id, type=type_, payload=payload)


async def _work(k: Keel, worker_id: str) -> bool:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is None:
        return False
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
    return True


async def test_the_park_releases_in_its_own_transaction(journal, world) -> None:
    k = _keel(journal)
    handle = await k.start(demo.gated_tool_chain, {"title": "park"})
    assert await _work(k, "w1")
    row = await journal.run_row(handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "WAITING_APPROVAL"
    assert row.phase == "WAITING_APPROVAL"
    assert row.lease_expires_at is None and row.runnable_at is None
    assert await journal.claim("idle", timedelta(seconds=TTL)) is None, "zero ticks: nothing to claim"


async def test_an_approve_racing_the_re_park_is_decided_not_lost(journal, world, monkeypatch) -> None:
    """The lost wakeup on the real statements: an approve committed on another connection between a
    woken run's drain and its re-park sets `runnable_at`; the guarded release matches 0 rows, the
    waiting transaction rolls back, and the drain decides it."""
    from keel.runtime.steps import StepEngine

    k = _keel(journal)
    handle = await k.start(demo.gated_tool_chain, {"title": "race on postgres"})
    assert await _work(k, "w1")
    assert await journal.insert_signal(_row(handle.run_id, "custom"))
    [approval] = fold(await k.events(handle.run_id)).approvals.values()

    original = StepEngine._commit_park
    raced: list[bool] = []

    async def approve_in_the_window(self: Any, *args: Any, **kwargs: Any) -> bool:
        if not raced:
            raced.append(True)
            assert await journal.insert_signal(
                _row(handle.run_id, "approve", by="alice", approval_id=str(approval.approval_id))
            )
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(StepEngine, "_commit_park", approve_in_the_window)
    assert await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert raced and state.phase == "COMPLETED", state.phase
    assert world.applied_counts()["issues.create#1"] == 1
    assert await journal.pending_signals(handle.run_id) == []


async def test_a_pause_holds_until_resume_and_resume_clears_the_column(journal, world) -> None:
    k = _keel(journal)
    handle = await k.start(demo.tool_chain, {"task": "pause me"})
    assert await journal.insert_signal(_row(handle.run_id, "pause"))
    assert await _work(k, "w1")
    row = await journal.run_row(handle.run_id)
    assert row.paused_at is not None and row.lease_expires_at is None and row.phase == "PAUSED"

    assert await journal.insert_signal(_row(handle.run_id, "custom"))
    assert await journal.claim("w2", timedelta(seconds=TTL)) is None, "a custom row does not lift a pause"

    assert await journal.insert_signal(_row(handle.run_id, "resume"))
    assert await _work(k, "w3")
    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED"
    assert "RUN_PAUSE_LIFTED" in [e.type for e in events]
    assert (await journal.run_row(handle.run_id)).paused_at is None


async def test_a_child_result_wakes_the_parent_through_the_inbox_alone(journal, world) -> None:
    """No second `runs` row is locked inside a child's terminal transaction — that bump took parent
    and child rows in the opposite order to a parent's cancel drain. The claim reads the inbox."""
    k = _keel(journal)
    handle = await k.start(demo.orchestrator, {"tasks": ["a"]})
    lease = await journal.acquire(handle.run_id, "p1", timedelta(seconds=TTL))
    with contextlib.suppress(BaseException):
        await k.worker(worker_id="p1", lease_ttl=TTL).execute(lease)
    [child] = await journal.children(handle.run_id)
    child_lease = await journal.acquire(child.run_id, "c1", timedelta(seconds=TTL))
    with contextlib.suppress(BaseException):
        await k.worker(worker_id="c1", lease_ttl=TTL).execute(child_lease)

    assert (await journal.run_row(handle.run_id)).runnable_at is None, "no cross-run bump"
    woken = await journal.claim("p2", timedelta(seconds=TTL))
    assert woken is not None and woken.run_id == handle.run_id
    with contextlib.suppress(BaseException):
        await k.worker(worker_id="p2", lease_ttl=TTL).execute(woken)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"


async def test_the_timer_sweep_skips_a_held_run(journal, world) -> None:
    """§5.4 (6). A timer fired under a lease is keyed `timer:<wake_at>`, so it would also block the
    re-fire after the release."""
    k = _keel(journal)
    handle = await k.start(demo.tool_chain, {"task": "held"})
    lease = await journal.acquire(handle.run_id, "holder", timedelta(seconds=30))
    pool = await journal._ready()
    async with pool.connection() as conn:
        await conn.execute("UPDATE runs SET wake_at = now() - interval '1 second' WHERE run_id = %s", (handle.run_id,))
    assert await journal.sweep_timers() == 0, "held: the holder drains its own timers"
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE runs SET lease_expires_at = NULL, wake_at = now() - interval '1 second' WHERE run_id = %s",
            (handle.run_id,),
        )
    assert await journal.sweep_timers() == 1
    del lease


async def test_a_client_clock_ahead_of_the_store_delays_neither_start_nor_handover(journal, world) -> None:
    """The claim compares `runnable_at` with the store's `now()`. Docker's VM clock drifts from the
    host's; a start or a drain stamped by a client ahead of it was unclaimable for the skew."""
    from datetime import UTC, datetime

    class Ahead:
        def now(self) -> datetime:
            return datetime.now(UTC) + timedelta(hours=1)

    k = Keel(
        journal=journal, provider=ScriptedProvider(demo.SCRIPT), clock=Ahead(),
        tools=[demo.search, demo.create_issue_tool("EXTERNAL")], programs=[demo.tool_chain],
    )
    handle = await k.start(demo.tool_chain, {"task": "skew"})
    lease = await journal.claim("w1", timedelta(seconds=TTL))
    assert lease is not None and lease.run_id == handle.run_id
    await journal.release(lease, runnable_at=Ahead().now(), runnable_reason="DRAIN")
    assert await journal.claim("w2", timedelta(seconds=TTL)) is not None


async def test_an_unknown_signal_type_is_a_keel_error_not_a_check_violation(journal, world) -> None:
    k = _keel(journal)
    handle = await k.start(demo.tool_chain, {"task": "x"})
    with pytest.raises(IllegalTransition):
        await journal.insert_signal(_row(handle.run_id, "deploy_now"))
