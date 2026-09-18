"""`ctx.sleep`: a durable timer that costs one row while it runs (§18.4, §10.4).

The wait is the approval park with a clock instead of a human: INTENT, STARTED, RUN_WAITING{sleep}
and the release commit together, `wake_at` is the store's `now()` plus the duration, the timer sweep
rings the doorbell, and the step completes on the first wake the store's clock says is due.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from keel import Keel, program
from keel.core.clock import FakeClock
from keel.core.ids import uuid7
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import SignalRow
from keel.replay.verify import verify
from keel.state.fold import fold

TTL = 2.0


@program(name="napper", version="1.0")
async def napper(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    await ctx.sleep(args["seconds"])
    return {"when": (await ctx.now()).isoformat()}


def _keel(clock: FakeClock) -> Keel:
    return Keel(journal=MemoryJournal(clock=clock), programs=[napper], clock=clock)


async def _work(k: Keel, worker_id: str) -> bool:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is None:
        return False
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
    return True


async def test_the_sleep_parks_with_no_lease_and_wakes_on_the_stores_clock() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(napper, {"seconds": 5})
    t0 = clock.now()
    await _work(k, "w1")

    row = await k.journal.run_row(handle.run_id)
    assert (row.phase, row.lease_expires_at, row.runnable_at) == ("SLEEPING", None, None)
    assert row.wake_at == t0 + timedelta(seconds=5), "wake_at is the store's now() plus the duration"
    events = await k.events(handle.run_id)
    intent = next(e for e in events if e.type == "STEP_INTENDED")
    parked = [e for e in events if e.seq > intent.seq]
    assert [e.type for e in parked] == ["STEP_ATTEMPT_STARTED", "RUN_WAITING"], "one transaction, no outcome"
    assert parked[1].body.reason == "sleep" and parked[1].body.wake_at == row.wake_at

    clock.advance(4.9)
    assert await k.journal.sweep_timers() == 0, "not before wake_at"
    assert not await _work(k, "w2"), "a sleeping run is claimable by nothing but its timer"
    clock.advance(0.1)
    assert await k.journal.sweep_timers() == 1
    assert await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    step = state.steps[0]
    assert (step.kind, step.state) == ("SLEEP", "COMPLETED")
    assert step.result["woke_at"] == (t0 + timedelta(seconds=5)).isoformat()
    assert (await verify(k.journal, handle.run_id, napper)).ok


async def test_a_spurious_wake_before_wake_at_parks_again_without_completing() -> None:
    """Whatever wakes a sleeping run — a resume nobody needed, a signal for something else — the
    step completes only when the store's clock is past `wake_at`. Otherwise it re-parks, for the
    price of one row, keeping the original deadline."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(napper, {"seconds": 60})
    await _work(k, "w1")
    wake_at = (await k.journal.run_row(handle.run_id)).wake_at

    clock.advance(10)
    await k.journal.insert_signal(SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="resume"))
    assert await _work(k, "w2")
    state = fold(await k.events(handle.run_id))
    assert state.phase == "SLEEPING" and state.steps[0].state == "RUNNING"
    row = await k.journal.run_row(handle.run_id)
    assert (row.wake_at, row.lease_expires_at, row.runnable_at) == (wake_at, None, None)
    assert [e.type for e in await k.events(handle.run_id)].count("STEP_INTENDED") == 1, "never re-issued"

    clock.advance(50)
    assert await k.journal.sweep_timers() == 1
    assert await _work(k, "w3")
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"


async def test_a_kill_after_the_timer_was_consumed_still_completes_by_the_clock() -> None:
    """The timer row is the doorbell, not the decision. A holder that drained it and died before
    the step's outcome committed leaves nothing in the inbox; the successor completes the sleep
    because the store's clock says it is due, not because a row told it so."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(napper, {"seconds": 5})
    await _work(k, "w1")
    clock.advance(6)
    assert await k.journal.sweep_timers() == 1

    from keel.runtime import hooks

    def die_after_the_drain(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:signal_consume":
            raise hooks.Crash("power cut after the timer was consumed")

    hooks.install(die_after_the_drain)
    try:
        await _work(k, "w2")
    finally:
        hooks.reset()
    assert not await k.journal.pending_signals(handle.run_id), "the timer is gone"
    clock.advance(TTL + 1)
    await k.journal.reap()
    assert await _work(k, "w3")
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert (await verify(k.journal, handle.run_id, napper)).ok


async def test_a_replay_memoizes_the_completed_sleep() -> None:
    """VERIFY re-executes the program and never waits: the SLEEP step's outcome is in the journal."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(napper, {"seconds": 1})
    await _work(k, "w1")
    clock.advance(1)
    await k.journal.sweep_timers()
    await _work(k, "w2")
    out = await verify(k.journal, handle.run_id, napper)
    assert out.ok and out.replayed_steps == 2 and out.projection_hash is not None
