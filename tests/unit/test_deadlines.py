"""Deadlines (§16.4, §17.7): `Budget.deadline_at`, `max_wall_clock` and a contract's `deadline_s`.

`max_wall_clock` is converted once, at RUN_CREATED, by the store's clock. The STARTED transaction
refuses an attempt past the deadline (STEP_FAILED{DeadlineExceeded} → RUN_FAILED); a waiting run's
`wake_at` is `least(wake_at, deadline_at)`, and a wait woken past it is STEP_CANCELLED with RUN_FAILED
after — its children cancelled first. A child's deadline is `least(contract, parent)`.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from keel import Budget, Keel, program
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import Decision, ScriptedProvider
from keel.replay.verify import verify
from keel.runtime.delegation import Delegation
from keel.state.fold import deadline_of, fold

TTL = 2.0
GRACE = 5.0


@program(name="deadline_sleeper", version="1.0")
async def sleeper(ctx: Any, args: dict[str, Any]) -> str:
    await ctx.sleep(float(args.get("seconds", 1000)))
    return "woke"


@program(name="deadline_asker", version="1.0")
async def asker(ctx: Any, args: dict[str, Any]) -> str:
    return (await ctx.model([{"role": "user", "content": "q"}], name="ask")).text


@program(name="deadline_gate", version="1.0")
async def gate(ctx: Any, args: dict[str, Any]) -> Any:
    return await ctx.approve({"what": "deploy"})


@program(name="deadline_parent", version="1.0")
async def parent(ctx: Any, args: dict[str, Any]) -> Any:
    child = await ctx.delegate(Delegation(
        program="deadline_sleeper", args={"seconds": 1000}, deadline_s=args.get("deadline_s"),
    ))
    return {"status": child.status, "error": child.error}


def _keel(clock: FakeClock) -> Keel:
    return Keel(journal=MemoryJournal(clock=clock), provider=ScriptedProvider([Decision(text="a")]),
                programs=[sleeper, asker, gate, parent], clock=clock)


async def _work(k: Keel, limit: int = 20) -> None:
    """Sweep the timers, then claim until nothing is runnable."""
    await k.journal.sweep_timers()
    for i in range(limit):
        lease = await k.journal.claim(f"w{i}", timedelta(seconds=TTL))
        if lease is None:
            return
        with contextlib.suppress(BaseException):
            await k.worker(worker_id=f"w{i}", lease_ttl=TTL, cancel_grace=GRACE).execute(lease)
    raise AssertionError("still runnable")


def _types(events: list[Any]) -> list[str]:
    return [e.type for e in events]


def test_max_wall_clock_becomes_a_deadline_once_and_the_earlier_one_wins() -> None:
    from datetime import UTC, datetime

    created = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    assert deadline_of({"max_wall_clock": 30}, created) == created + timedelta(seconds=30)
    assert deadline_of({"max_wall_clock": "PT1M", "deadline_at": (created + timedelta(seconds=10)).isoformat()},
                       created) == created + timedelta(seconds=10)
    assert deadline_of({}, created) is None


async def test_an_attempt_past_the_deadline_is_refused_before_the_barrier() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(asker, {}, budget=Budget(max_wall_clock=timedelta(seconds=5)))
    clock.advance(6)
    await _work(k)
    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "FAILED" and state.error == "DeadlineExceeded"
    [refusal] = [e for e in events if e.type == "STEP_FAILED"]
    assert (refusal.attempt_no, refusal.body.error) == (0, "DeadlineExceeded")
    assert "STEP_ATTEMPT_STARTED" not in _types(events), "no attempt, so nothing spent"


async def test_a_sleep_wakes_at_the_deadline_and_the_run_fails() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(sleeper, {"seconds": 100}, budget=Budget(max_wall_clock=timedelta(seconds=10)))
    t0 = clock.now()
    await _work(k)
    row = await k.journal.run_row(handle.run_id)
    waiting = [e for e in await k.events(handle.run_id) if e.type == "RUN_WAITING"][-1]
    assert row.wake_at == t0 + timedelta(seconds=10), "the runs row wakes at the deadline"
    assert waiting.body.wake_at == t0 + timedelta(seconds=100), "RUN_WAITING keeps the sleep's own"

    clock.advance(10)
    await _work(k)
    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "FAILED" and state.error == "DeadlineExceeded", state.phase
    [cancelled] = [e for e in events if e.type == "STEP_CANCELLED"]
    assert cancelled.body.reason == "DeadlineExceeded"
    assert _types(events)[-1] == "RUN_FAILED"
    assert (await verify(k.journal, handle.run_id, sleeper)).ok, "replay reproduces the failure"


async def test_an_approval_nobody_decides_is_cancelled_at_the_deadline() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(gate, {}, budget=Budget(max_wall_clock=timedelta(seconds=30)))
    await _work(k)
    assert (await k.journal.run_row(handle.run_id)).phase == "WAITING_APPROVAL"
    clock.advance(30)
    await _work(k)
    state = fold(await k.events(handle.run_id))
    assert state.phase == "FAILED" and state.error == "DeadlineExceeded"
    assert not await k.signal(handle.run_id, "approve", {"by": "late"}), "a terminal run takes no signal"


async def test_a_contract_deadline_fails_the_child_and_the_parent_applies_its_policy() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(parent, {"deadline_s": 5})
    await _work(k)
    [child_row] = await k.journal.delegations(handle.run_id)
    child_created = (await k.events(child_row.child_run_id))[0]
    assert child_created.body.budget["deadline_at"] is not None

    clock.advance(5)
    await _work(k)
    child = fold(await k.events(child_row.child_run_id))
    assert child.phase == "FAILED" and child.error == "DeadlineExceeded"
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED", "escalate: the failure is a value the program reads"
    assert state.result == {"status": "failed", "error": "DeadlineExceeded"}


async def test_a_parent_past_its_deadline_fails_only_after_its_children() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(parent, {}, budget=Budget(max_wall_clock=timedelta(seconds=10)))
    await _work(k)
    [child_row] = await k.journal.delegations(handle.run_id)
    assert (await k.events(child_row.child_run_id))[0].body.budget["deadline_at"] is not None, "least(parent)"

    clock.advance(10)
    await _work(k)
    clock.advance(GRACE + TTL + 1)  # a child that did not answer is taken over after the grace
    await _work(k)
    parent_events = await k.events(handle.run_id)
    child_events = await k.events(child_row.child_run_id)
    state = fold(parent_events)
    assert state.phase == "FAILED" and state.error == "DeadlineExceeded", state.phase
    assert fold(child_events).terminal
    assert child_events[-1].ts <= parent_events[-1].ts, "S8: the child is terminal before its parent"


async def test_a_contract_deadline_after_the_parents_is_refused() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(parent, {"deadline_s": 60}, budget=Budget(max_wall_clock=timedelta(seconds=10)))
    await _work(k)
    state = fold(await k.events(handle.run_id))
    assert state.phase == "FAILED" and "deadline_s" in (state.error or "")
    assert not await k.journal.delegations(handle.run_id), "refused before anything was spawned"
