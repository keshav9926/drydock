"""The durable plan: `ctx.plan.*` as PLAN steps, the plan as a fold of PLAN_UPDATED (§16.2, §18.2).

Three claims. A plan op is one step whose four events commit together (§6.2). The plan the program
reads is bounded by the replay cursor, so a replay never sees what a later step did (§16.2). And the
plan is a projection of the journal, so `keel show` and a successor read the same plan.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from keel import Keel, program
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.replay.verify import verify
from keel.runtime import hooks
from keel.state.fold import fold
from keel.state.plan import plan_hash

TTL = 2.0


@program(name="planner", version="1.0")
async def planner(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    await ctx.plan.init(["survey", "patch", "ship"])
    # Control flow that depends on what the plan says. A replay that read the journal's final plan
    # instead of the plan at its cursor would find these already completed and skip the steps.
    for item in ctx.plan.items:
        if item["status"] == "pending" and item["title"] != "ship":
            await ctx.now()
            await ctx.plan.complete(item["id"])
    extra = await ctx.plan.add("follow up")
    return {"done": ctx.plan.done, "extra": extra, "statuses": [i["status"] for i in ctx.plan.items]}


@program(name="bad_planner", version="1.0")
async def bad_planner(ctx: Any, args: dict[str, Any]) -> None:
    await ctx.plan.init(["only"])
    await ctx.plan.complete("no-such-item")


def _keel(clock: FakeClock) -> Keel:
    return Keel(journal=MemoryJournal(clock=clock), programs=[planner, bad_planner], clock=clock)


async def _work(k: Keel, worker_id: str) -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


async def test_each_plan_op_is_one_step_and_the_plan_is_a_fold() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(planner)
    await _work(k, "w1")
    events = await k.events(handle.run_id)
    state = fold(events)

    assert state.phase == "COMPLETED"
    assert state.result == {"done": False, "extra": "5", "statuses": ["completed", "completed", "pending", "pending"]}
    assert [(i["id"], i["title"], i["status"]) for i in state.plan] == [
        ("0.0", "survey", "completed"), ("0.1", "patch", "completed"), ("0.2", "ship", "pending"),
        ("5", "follow up", "pending"),
    ]
    plan_steps = [s for s in state.steps.values() if s.kind == "PLAN"]
    assert [s.name for s in plan_steps] == ["plan.init", "plan.complete", "plan.complete", "plan.add"]
    assert plan_steps[-1].result == plan_hash(state.plan), "a PLAN step completes with the plan it left"
    for s in plan_steps:
        # INTENT, STARTED, PLAN_UPDATED, COMPLETED: consecutive, one transaction (§6.2).
        types = [e.type for e in events if s.intent_seq <= e.seq < s.intent_seq + 4]
        assert types == ["STEP_INTENDED", "STEP_ATTEMPT_STARTED", "PLAN_UPDATED", "STEP_COMPLETED"]
    assert (await k.get(handle.run_id)).plan == state.plan, "`keel show` prints the fold"
    assert (await verify(k.journal, handle.run_id, planner)).ok, "reads bounded by the cursor replay identically"


async def test_a_successor_reads_the_plan_as_it_was_at_its_cursor() -> None:
    """Killed after the first `complete` committed: the successor re-executes, reads the plan at each
    step as the original did, memoizes what is journaled and ends where an uncrashed run ends."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(planner)

    def die(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:intent_commit" and detail.get("step_index") == 3:
            raise hooks.Crash("killed before the second now()")

    hooks.install(die)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()
    assert [i["status"] for i in fold(await k.events(handle.run_id)).plan] == ["completed", "pending", "pending"]
    clock.advance(TTL + 1)
    await k.journal.reap()
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    assert state.result["statuses"] == ["completed", "completed", "pending", "pending"]
    assert sum(1 for e in await k.events(handle.run_id) if e.type == "PLAN_UPDATED") == 4, "no op twice"
    assert (await verify(k.journal, handle.run_id, planner)).ok


async def test_completing_an_item_the_plan_does_not_hold_is_refused_before_any_step() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(bad_planner)
    await _work(k, "w1")
    state = fold(await k.events(handle.run_id))
    assert state.phase == "FAILED" and "no-such-item" in state.error
    assert [s.name for s in state.steps.values()] == ["plan.init"], "nothing journaled for the bad op"
