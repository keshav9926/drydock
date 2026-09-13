"""The signals inbox and its drain (§4.10, §5.6, §29.1).

Everything that is not the lease holder influences a run through one table. Not a second control
path beside the fence — *the* path, and the MVP's direct `runnable_at` UPDATE is deleted rather
than kept beside it, because two ways to influence a run is one more than the fence can defend.

Three properties decide whether the inbox is safe, and each is a test below:

    consumed with its event     one fenced transaction, or a signal could be applied and forgotten
    decided at the drain        the API refuses almost nothing; the holder decides from state *now*
    deterministic on replay     a cancel lands at the index the journal records, not near it

The third is the one a reader should be most suspicious of. A cancel that stopped the program
"somewhere around step 3" would make a cancelled run unreproducible, and every replay-based claim
in this project rests on being able to re-execute a run and get the same history back.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import pytest

from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.server import WorldServer
from keel import Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.core.ids import uuid7
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import SignalRow
from keel.providers.scripted import ScriptedProvider
from keel.state.fold import fold

TTL = 2.0


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


def _keel(clock: FakeClock) -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue_tool("EXTERNAL")],
        programs=[demo.tool_chain],
        clock=clock,
    )


def _row(run_id, type_: str, **kw) -> SignalRow:
    return SignalRow(signal_id=uuid7(), run_id=run_id, type=type_, **kw)


async def _work(k: Keel, worker_id: str = "w1") -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


async def test_a_signal_is_consumed_in_the_same_transaction_as_its_event(world) -> None:
    """The inbox's whole guarantee. A signal cannot be applied without the journal saying so, and
    cannot be marked consumed without the event that says what was done about it — the same
    same-database-transaction argument that gives TRANSACTIONAL tools theirs."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    assert await k.journal.insert_signal(_row(handle.run_id, "cancel", payload={"reason": "no"}))

    await _work(k)

    events = await k.events(handle.run_id)
    received = [e for e in events if e.type == "SIGNAL_RECEIVED"]
    assert len(received) == 1
    assert await k.journal.pending_signals(handle.run_id) == [], "consumed, so never re-read"
    consumed = next(iter(k.journal._signals.values()))
    assert consumed.consumed_seq == received[0].seq, "the event's own seq, not a later one"


async def test_cancel_is_acknowledged_at_a_step_boundary_and_the_run_ends_cancelled(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "cancel", payload={"reason": "operator"}))

    await _work(k)

    state = fold(await k.events(handle.run_id))
    assert state.phase == "CANCELLED"
    assert state.cancel_acknowledged_at == 0, "the next boundary, which is the first step"
    assert state.steps == {}, "nothing ran: the cancel arrived before the program's first step"
    assert world.applied_counts() == {}, "and so nothing reached the World"


async def test_a_cancel_mid_run_lands_where_the_journal_says_and_nowhere_else(world) -> None:
    """The determinism property. The cancel arrives after two steps are journaled, so it is
    acknowledged at step 2 — and a successor re-executing this journal must raise at step 2 too,
    not run one step further because the second pass happened to be faster."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    # Let the run get two steps in, then stop it where a crash would.
    from keel.runtime import hooks

    def crash_after_step_1(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:outcome_commit" and detail.get("step_index") == 1:
            raise hooks.Crash("power cut")

    hooks.install(crash_after_step_1)
    await _work(k, "w1")
    hooks.reset()

    mid = fold(await k.events(handle.run_id))
    assert set(mid.steps) == {0, 1}, "two steps journaled, nothing more"

    await k.journal.insert_signal(_row(handle.run_id, "cancel"))
    clock.advance(TTL + 2)
    await k.journal.reap()
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "CANCELLED"
    assert state.cancel_acknowledged_at == 2, "the first boundary the successor reached"
    assert set(state.steps) == {0, 1}, "step 2 was never attempted"

    # The proof that it is reproducible: fold the journal again and re-run VERIFY against it. The
    # recorded index is what a replay raises at, so the second pass stops in the same place.
    from keel.replay.verify import verify as run_verify

    out = await run_verify(k.journal, handle.run_id, demo.tool_chain.fn, tools=k.tools)
    assert out.ok, out.as_dict()


async def test_the_inbox_is_at_least_once_and_the_second_cancel_is_ignored_not_obeyed(world) -> None:
    """A retried click is the ordinary case, not an error. The API refuses almost nothing; the
    holder decides, and journals `SIGNAL_IGNORED` with the reason so "nothing happened" is an
    auditable answer rather than a silence."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    for _ in range(3):
        assert await k.journal.insert_signal(_row(handle.run_id, "cancel"))

    await _work(k)

    events = await k.events(handle.run_id)
    assert len([e for e in events if e.type == "SIGNAL_RECEIVED"]) == 3, "all three consumed"
    assert len([e for e in events if e.type == "CANCEL_ACKNOWLEDGED"]) == 1, "acted on once"
    ignored = [e for e in events if e.type == "SIGNAL_IGNORED"]
    assert len(ignored) == 2
    assert {e.body.reason for e in ignored} == {"already_cancelling"}
    assert await k.journal.pending_signals(handle.run_id) == []


async def test_a_client_key_deduplicates_the_retry_before_it_reaches_the_inbox(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    assert await k.journal.insert_signal(_row(handle.run_id, "cancel", client_key="op-42"))
    assert not await k.journal.insert_signal(_row(handle.run_id, "cancel", client_key="op-42"))
    assert len(await k.journal.pending_signals(handle.run_id)) == 1


async def test_a_signal_to_a_terminal_run_is_refused_rather_than_left_unconsumed(world) -> None:
    """§5.6: there is no future holder to drain it, so a row inserted here would sit unconsumed for
    the life of the run. The inbox must not grow on late clicks."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await _work(k)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"

    assert not await k.journal.insert_signal(_row(handle.run_id, "cancel"))
    assert await k.journal.pending_signals(handle.run_id) == []


async def test_pause_parks_the_run_and_resume_brings_it_back(world) -> None:
    """The zero-compute wait, in its simplest form. A paused run holds no lease and has no
    `runnable_at`, so nothing polls it — the same park the approval wait uses."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "pause"))

    await _work(k, "w1")

    row = await k.journal.run_row(handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "PAUSED"
    assert row.lease_expires_at is None, "no lease held"
    assert row.runnable_at is None, "and nothing to poll: zero ticks, not just zero compute"

    assert await k.resume(handle.run_id)
    assert (await k.journal.run_row(handle.run_id)).runnable_at is not None, "the signal is the wake"
    await _work(k, "w2")
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"


async def test_a_signal_nothing_handles_is_consumed_and_journaled(world) -> None:
    """An unknown type is not an error at the API and not a silent drop at the drain. It is one
    `SIGNAL_IGNORED{no_handler}`, which is what stops it being re-read at every boundary."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "custom", payload={"hello": "world"}))

    await _work(k)

    events = await k.events(handle.run_id)
    ignored = [e for e in events if e.type == "SIGNAL_IGNORED"]
    assert [e.body.reason for e in ignored] == ["no_handler"]
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED", "and the run is unaffected"


async def test_verify_never_drains(world) -> None:
    """VERIFY appends nothing, so it must not consume anything either. A signal drained by a replay
    would be applied to a run whose history already ran without it."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    # The run must be non-terminal for the signal to be accepted at all, so stop it mid-flight.
    from keel.runtime import hooks

    def crash(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:outcome_commit" and detail.get("step_index") == 1:
            raise hooks.Crash("power cut")

    hooks.install(crash)
    await _work(k, "w1")
    hooks.reset()
    assert await k.journal.insert_signal(_row(handle.run_id, "custom"))

    from keel.replay.verify import verify as run_verify

    before = await k.journal.read(handle.run_id)
    await run_verify(k.journal, handle.run_id, demo.tool_chain.fn, tools=k.tools)
    assert await k.journal.read(handle.run_id) == before, "VERIFY wrote nothing"
    assert len(await k.journal.pending_signals(handle.run_id)) == 1, "and consumed nothing"
