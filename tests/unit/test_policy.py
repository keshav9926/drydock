"""Policy: capabilities and approval gates as a pre-step verdict (§20.2, §20.3, §4.3, §9.4).

Three verdicts and one rule under all of them: the journal decides, the Policy only ever answers a
*live* index. Each test below is one of §20.2's journal-state rows, and the parked-run cases are the
point — a policy edited while a run sits on an approval must not renumber its steps.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from typing import Any

import pytest

from keel import EffectClass, Keel, program, tool
from keel.core.clock import FakeClock
from keel.core.errors import StepFailed
from keel.journal.memory import MemoryJournal
from keel.replay.verify import verify
from keel.runtime.delegation import Delegation
from keel.runtime.policy import StaticPolicy
from keel.state.fold import fold

TTL = 2.0
CALLS: list[str] = []


@tool(effect=EffectClass.PURE, timeout=1.0, name="look")
async def look(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    CALLS.append("look")
    return {"seen": args.get("q")}


@tool(effect=EffectClass.EXTERNAL, timeout=1.0, name="deploy")
async def deploy(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    CALLS.append("deploy")
    return {"deployed": args.get("svc"), "external_ref": f"deploy#{args.get('svc')}"}


@tool(effect=EffectClass.EXTERNAL, timeout=0.05, name="quick")
async def quick(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    CALLS.append("quick")
    return {}


@program(name="deployer", version="1.0")
async def deployer(ctx: Any, args: dict[str, Any]) -> Any:
    seen = await ctx.tool("look", q="status")
    try:
        done = await ctx.tool("deploy", svc="api")
    except StepFailed as exc:
        return {"refused": exc.error, "seen": seen}
    return {"done": done}


@program(name="self_gated", version="1.0")
async def self_gated(ctx: Any, args: dict[str, Any]) -> Any:
    decision = await ctx.approve({"why": "ship"}, gates=("deploy", {"svc": "api"}))
    if decision["decision"] != "granted":
        return {"stopped": decision["decision"]}
    return await ctx.tool("deploy", svc="api")


@program(name="parent", version="1.0")
async def parent(ctx: Any, args: dict[str, Any]) -> Any:
    [r] = await ctx.delegate_many(
        [Delegation(program="child", task="t", allowed_tools=frozenset(args["grant"]), result_schema=None)]
    )
    return {"status": r.status, "result": r.result}


@program(name="child", version="1.0")
async def child(ctx: Any, args: dict[str, Any]) -> Any:
    try:
        await ctx.tool("deploy", svc="child")
    except StepFailed as exc:
        return {"refused": exc.error}
    return {"refused": None}


class Counting(StaticPolicy):
    """StaticPolicy that also records what it was asked and what the run looked like."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.asked: list[tuple[str, int]] = []

    async def pre_step(self, intent: Any, run: Any) -> Any:
        self.asked.append((intent.name, run.next_step_index))
        return await super().pre_step(intent, run)


@pytest.fixture(autouse=True)
def _calls() -> None:
    CALLS.clear()


def _keel(journal: MemoryJournal, policy: Any, clock: FakeClock) -> Keel:
    return Keel(journal=journal, tools=[look, deploy, quick],
                programs=[deployer, self_gated, parent, child], clock=clock, policy=policy)


async def _work(k: Keel, worker_id: str) -> bool:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is None:
        return False
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
    return True


def _intents(events: list[Any]) -> list[tuple[int, str, str, str]]:
    return [(e.body.step_index, e.body.kind, e.body.name, e.body.policy_verdict) for e in events
            if e.type == "STEP_INTENDED"]


async def test_deny_is_a_journaled_refusal_the_program_can_route_around() -> None:
    clock = FakeClock()
    policy = Counting(allowed_tools={"look"})
    k = _keel(MemoryJournal(clock=clock), policy, clock)
    handle = await k.start(deployer, {})
    await _work(k, "w1")

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED" and state.result["refused"].startswith("PolicyDenied")
    assert CALLS == ["look"], "a denied tool never reaches STEP_ATTEMPT_STARTED"
    assert _intents(events) == [(0, "TOOL", "look", "allow"), (1, "TOOL", "deploy", "deny")]
    [failed] = [e.body for e in events if e.type == "STEP_FAILED"]
    assert (failed.step_index, failed.attempt_no, failed.retryable) == (1, 0, False)
    rows = {r.tool: r.status for r in await k.journal.effects(handle.run_id)}
    assert rows == {"look": "COMMITTED", "deploy": "DENIED"}
    assert policy.asked == [("look", 0)], "outside the capability set, the Policy is not even asked"
    assert (await verify(k.journal, handle.run_id, deployer, tools=k.tools)).ok


async def test_require_approval_takes_two_indices_and_parks_for_free() -> None:
    clock = FakeClock()
    policy = Counting(require_approval={"deploy"})
    k = _keel(MemoryJournal(clock=clock), policy, clock)
    handle = await k.start(deployer, {})
    await _work(k, "w1")
    # The Policy is shown the run as the journal has it now — the step this epoch just ran included,
    # which the engine's own working state (folded at acquisition) would not show it.
    assert policy.asked == [("look", 0), ("deploy", 1)]

    state = fold(await k.events(handle.run_id))
    row = await k.journal.run_row(handle.run_id)
    assert state.phase == "WAITING_APPROVAL" and row.lease_expires_at is None and row.runnable_at is None
    [approval] = state.approvals.values()
    assert approval.step_index == 1
    assert approval.payload["tool"] == "deploy" and approval.payload["args"] == {"svc": "api"}
    assert CALLS == ["look"]

    assert await k.approve(handle.run_id, approval.approval_id, by="keshav")
    await _work(k, "w2")

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED" and state.result == {"done": {"deployed": "api", "external_ref": "deploy#api"}}
    assert _intents(events) == [
        (0, "TOOL", "look", "allow"),
        (1, "APPROVAL", "deploy", "require_approval"),
        (2, "TOOL", "deploy", "require_approval"),
    ]
    assert approval.binds_effect_key == state.steps[2].effect_key, "the grant names the effect at i+1"
    assert CALLS == ["look", "deploy"]
    assert (await verify(k.journal, handle.run_id, deployer, tools=k.tools)).ok


async def test_a_rejection_refuses_the_bound_call_before_an_attempt() -> None:
    clock = FakeClock()
    k = _keel(MemoryJournal(clock=clock), StaticPolicy(require_approval={"deploy"}), clock)
    handle = await k.start(deployer, {})
    await _work(k, "w1")
    [approval] = fold(await k.events(handle.run_id)).approvals.values()
    assert await k.reject(handle.run_id, approval.approval_id, by="keshav")
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED" and state.result["refused"] == "ApprovalRejected"
    assert CALLS == ["look"]
    assert {r.tool: r.status for r in await k.journal.effects(handle.run_id)}["deploy"] == "DENIED"


@pytest.mark.parametrize("allowed", [None, {"look"}])
async def test_a_policy_edited_while_parked_does_not_renumber_the_run(allowed: Any) -> None:
    """Parked under `require_approval`; woken by a worker whose Policy says allow-all, or would even
    deny the tool. The journaled APPROVAL at i is the gate this call inserted: nothing is asked."""
    now = Counting(allowed_tools=allowed)
    clock = FakeClock()
    journal = MemoryJournal(clock=clock)
    k = _keel(journal, StaticPolicy(require_approval={"deploy"}), clock)
    handle = await k.start(deployer, {})
    await _work(k, "w1")
    [approval] = fold(await k.events(handle.run_id)).approvals.values()
    assert await k.approve(handle.run_id, approval.approval_id, by="keshav")

    edited = _keel(journal, now, clock)
    await _work(edited, "w2")
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED", (state.phase, state.suspended_reason, state.error)
    assert CALLS == ["look", "deploy"]
    assert now.asked == [], "the journal decided every index; the Policy was never consulted"


async def test_a_call_the_program_already_gated_is_not_gated_twice() -> None:
    clock = FakeClock()
    k = _keel(MemoryJournal(clock=clock), StaticPolicy(require_approval={"deploy"}), clock)
    handle = await k.start(self_gated, {})
    await _work(k, "w1")
    [approval] = fold(await k.events(handle.run_id)).approvals.values()
    assert await k.approve(handle.run_id, approval.approval_id, by="keshav")
    await _work(k, "w2")

    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED"
    assert [e.type for e in events].count("APPROVAL_REQUESTED") == 1
    assert _intents(events) == [(0, "APPROVAL", "approve", "allow"), (1, "TOOL", "deploy", "require_approval")]


async def test_a_policy_that_does_not_answer_in_time_is_a_deny() -> None:
    class Slow(StaticPolicy):
        async def pre_step(self, intent: Any, run: Any) -> Any:
            await asyncio.sleep(1.0)
            return "allow"

    @program(name="quicker", version="1.0")
    async def quicker(ctx: Any, args: dict[str, Any]) -> Any:
        await ctx.tool("quick")

    clock = FakeClock()
    k = _keel(MemoryJournal(clock=clock), Slow(), clock)
    k.register(quicker)
    handle = await k.start(quicker, {})
    await _work(k, "w1")
    state = fold(await k.events(handle.run_id))
    assert state.phase == "FAILED" and state.error.startswith("PolicyTimeout")
    assert CALLS == []


@pytest.mark.parametrize(("grant", "phase", "why"), [
    ({"look", "deploy"}, "FAILED", "are not the parent's"),  # it may not pass on what it lacks
    ({"look"}, "COMPLETED", None),                      # granted look only; the child's deploy is denied
])
async def test_delegation_passes_on_a_subset_and_the_child_is_held_to_it(grant: set[str], phase: str, why: Any) -> None:
    clock = FakeClock()
    k = _keel(MemoryJournal(clock=clock), StaticPolicy(allowed_tools={"look"}), clock)
    handle = await k.start(parent, {"grant": sorted(grant)})
    for _ in range(6):
        if not await _work(k, "w"):
            break
    state = fold(await k.events(handle.run_id))
    assert state.phase == phase, (state.phase, state.error)
    if why:
        assert why in state.error
        return
    assert state.result["status"] == "completed"
    assert state.result["result"]["refused"].startswith("PolicyDenied")
    assert CALLS == [], "the child's deploy never started"
    [kid] = await k.journal.children(handle.run_id)
    created = (await k.events(kid.run_id))[0].body
    assert created.policy == {"allowed_tools": ["look"]}, "the child's capability set is in its own journal"
