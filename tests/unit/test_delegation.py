"""Delegation: children under contracts, and the two things the parent owes them (§4.11, §7.6, §17).

Four claims, each a different mechanism.

**Spawn is one fact.** CHILD_SPAWNED, the child's `runs` row, its RUN_CREATED and the `delegations`
row commit in the parent's fenced transaction. A crash cannot separate "the parent says it spawned"
from "the child exists", and a re-executed spawn is a unique violation, not a twin.

**Completion is the outbox in the other direction.** A child's terminal event and the parent's
`child_result` row commit together, so a child cannot become terminal and die before notifying.

**The parent grades the result, not the child.** `result_schema` is judged at the drain: a child
whose own journal says COMPLETED can still be CHILD_FAILED{ContractViolation} to its parent.

**Cancel is asked first and forced second.** CANCEL_ACKNOWLEDGED puts a `cancel` in every open
child's inbox in the same transaction; a child that has not acknowledged within `cancel_grace` has
its lease taken over, and the takeover writer closes it in a new epoch. A child cannot outlive its
parent's terminal state either: the reaper applies the same two moves to strays.
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
from keel.client import program as as_program
from keel.core.clock import FakeClock
from keel.core.ids import uuid7
from keel.events import ChildSpawned, RecoveryStarted, RunCreated
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import DelegationRow, RunRow, SignalRow
from keel.providers.scripted import ScriptedProvider
from keel.runtime.reaper import Reaper
from keel.state.fold import fold

TTL = 2.0
GRACE = 5.0


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
        programs=[demo.tool_chain, demo.orchestrator, demo.research_child],
        clock=clock,
    )


async def _run(k: Keel, lease: Any, worker_id: str) -> None:
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL, cancel_grace=GRACE).execute(lease)


async def _claim(k: Keel, worker_id: str = "w") -> Any:
    """Whatever is runnable next — a child, usually, since a parked parent is never runnable."""
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is not None:
        await _run(k, lease, worker_id)
    return lease


async def _acquire(k: Keel, run_id: Any, worker_id: str) -> Any:
    lease = await k.journal.acquire(run_id, worker_id, timedelta(seconds=TTL))
    assert lease is not None, f"{worker_id} could not acquire {run_id}"
    await _run(k, lease, worker_id)
    return lease


async def _until_idle(k: Keel, limit: int = 20) -> None:
    for i in range(limit):
        if await _claim(k, f"w{i}") is None:
            return
    raise AssertionError("still runnable after the limit")


async def _state(k: Keel, run_id: Any) -> Any:
    return fold(await k.events(run_id))


async def test_the_spawn_is_one_transaction_and_the_park_costs_nothing(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")

    events = await k.events(handle.run_id)
    kinds = [e.type for e in events if e.type not in ("RUN_CREATED", "RECOVERY_STARTED", "RECOVERY_COMPLETED")]
    assert kinds == ["STEP_INTENDED", "STEP_ATTEMPT_STARTED", "CHILD_SPAWNED", "CHILD_SPAWNED", "RUN_WAITING"]
    state = fold(events)
    assert state.phase == "WAITING_CHILDREN" and state.waiting_reason == "children"
    assert state.charged.tokens_charged == 200, "both slices reserved at spawn (§17.4)"

    row = await k.journal.run_row(handle.run_id)
    assert row.lease_expires_at is None, "no lease: zero compute"
    assert row.runnable_at is None, "nothing polls it: zero ticks"

    children = await k.journal.children(handle.run_id)
    assert len(children) == 2 and all(c.parent_run_id == handle.run_id for c in children)
    assert all(c.runnable_at is not None and c.phase == "CREATED" for c in children)
    for c in children:
        [created] = await k.events(c.run_id)
        assert created.type == "RUN_CREATED" and created.body.parent_run_id == handle.run_id
        assert created.lease_epoch == 0, "born, not appended to: no lease exists yet"
        assert created.body.budget == {"max_tokens": 100}
    rows = await k.journal.delegations(handle.run_id)
    assert [(d.child_ordinal, d.retry_no, d.status, d.role) for d in rows] == [
        (0, 0, "SPAWNED", "worker"), (1, 0, "SPAWNED", "worker"),
    ]
    assert {d.child_run_id for d in rows} == {c.run_id for c in children}


async def test_children_run_and_their_results_wake_the_parent(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")

    # Each child's terminal event commits with the parent's wake — the inbox row itself. The claim
    # reads the inbox (§18.4), so no second `runs` row is bumped inside the child's transaction,
    # which is what keeps parent and child locks in one order.
    a, b = await k.journal.children(handle.run_id)
    await _acquire(k, a.run_id, "ca")
    assert (await k.journal.run_row(handle.run_id)).runnable_at is None, "no cross-run bump"
    claimable = []
    while (lease := await k.journal.claim("probe", timedelta(seconds=TTL))) is not None:
        claimable.append(lease)
    assert handle.run_id in {l.run_id for l in claimable}, "the child_result is the wake"
    for lease in claimable:
        await k.journal.release(lease)  # hand them straight back; the work below is the workers'
    await _acquire(k, b.run_id, "cb")
    pending = await k.journal.pending_signals(handle.run_id)
    assert [s.type for s in pending] == ["child_result", "child_result"]
    assert all(s.client_key.startswith("child_result:") for s in pending)

    await _acquire(k, handle.run_id, "w2")
    state = await _state(k, handle.run_id)
    assert state.phase == "COMPLETED", state.error
    assert state.result["answers"] == [{"task": "a", "hits": 3}, {"task": "b", "hits": 3}]
    assert state.result["failed"] == []
    [r0, r1] = state.steps[0].result
    assert (r0["status"], r1["status"]) == ("completed", "completed")
    assert all(c.state == "COMPLETED" for c in state.children.values())
    assert state.charged.tokens_charged == 0, "slices swapped for what the children charged"
    rows = await k.journal.delegations(handle.run_id)
    assert all(d.status == "COMPLETED" and d.settled_seq is not None for d in rows)
    assert await k.journal.pending_signals(handle.run_id) == []
    # The parent read nothing but the contract result. Its journal names the children and their
    # results — never a step of theirs.
    assert not any(e.type == "STEP_INTENDED" and e.body.kind == "TOOL" for e in await k.events(handle.run_id))


async def test_the_parent_grades_the_result_and_the_two_journals_may_disagree(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    schema = {"type": "object", "required": ["verdict"]}
    handle = await k.start(demo.orchestrator, {"tasks": ["a"], "result_schema": schema})
    await _acquire(k, handle.run_id, "w1")
    await _until_idle(k)
    await _acquire(k, handle.run_id, "w2")

    state = await _state(k, handle.run_id)
    [child] = state.children.values()
    assert child.state == "FAILED" and child.error == "ContractViolation" and child.policy_applied == "escalate"
    assert (await _state(k, child.child_run_id)).phase == "COMPLETED", "the child is right by its own lights"
    assert state.phase == "COMPLETED", "escalate: the program decides what a failed child means"
    assert state.result["failed"][0]["error"] == "ContractViolation"
    [row] = await k.journal.delegations(handle.run_id)
    assert row.status == "FAILED"


async def test_fail_parent_fails_the_delegate_step(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(
        demo.orchestrator,
        {"tasks": ["a"], "result_schema": {"type": "object", "required": ["verdict"]}, "on_failure": "fail_parent"},
    )
    await _acquire(k, handle.run_id, "w1")
    await _until_idle(k)
    await _acquire(k, handle.run_id, "w2")

    state = await _state(k, handle.run_id)
    assert state.phase == "FAILED"
    assert state.steps[0].state == "FAILED" and state.steps[0].error == "ChildFailed: ContractViolation"


async def test_retry_spawns_a_new_child_under_the_same_contract(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(
        demo.orchestrator,
        {"tasks": ["a"], "result_schema": {"type": "object", "required": ["verdict"]},
         "on_failure": "retry", "max_retries": 1},
    )
    await _acquire(k, handle.run_id, "w1")
    await _until_idle(k)
    await _acquire(k, handle.run_id, "w2")       # first result: retry
    await _until_idle(k)                         # the replacement child runs
    await _acquire(k, handle.run_id, "w3")       # second result: retries exhausted, escalate

    state = await _state(k, handle.run_id)
    by_retry = sorted(state.children.values(), key=lambda c: c.retry_no)
    assert [(c.child_ordinal, c.retry_no, c.state, c.policy_applied) for c in by_retry] == [
        (0, 0, "FAILED", "retry"), (0, 1, "FAILED", "escalate"),
    ]
    assert by_retry[0].contract == by_retry[1].contract, "the same contract, a new child (§17.6)"
    assert by_retry[0].child_run_id != by_retry[1].child_run_id
    assert state.phase == "COMPLETED" and len(state.result["failed"]) == 1
    assert len(await k.journal.delegations(handle.run_id)) == 2
    [r] = state.steps[0].result
    assert r["child_run_id"] == str(by_retry[1].child_run_id), "the outcome carries the latest retry"


async def test_a_crash_while_parked_does_not_spawn_twins(world) -> None:
    """§7.3.1's rule for waiting kinds, applied to children: a spurious wake re-parks, it does not
    re-issue the spawn. A second CHILD_SPAWNED per ordinal would be two children under one
    contract, and the unique key would make it a loud violation rather than a quiet one."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")

    clock.advance(TTL + 2)
    await k.journal.reap()
    await k.journal.insert_signal(SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="custom", payload={}))
    await _acquire(k, handle.run_id, "w2")

    events = await k.events(handle.run_id)
    assert sum(1 for e in events if e.type == "CHILD_SPAWNED") == 2, "spawned once, ever"
    assert sum(1 for e in events if e.type == "RUN_WAITING") == 2, "re-parked, journaled"
    assert (await _state(k, handle.run_id)).phase == "WAITING_CHILDREN"
    assert len(await k.journal.children(handle.run_id)) == 2

    await _until_idle(k)
    await _acquire(k, handle.run_id, "w3")
    assert (await _state(k, handle.run_id)).phase == "COMPLETED"


async def test_a_contract_the_parent_cannot_honour_is_refused_before_anything_commits(world) -> None:
    """Σ budget_slice over the parent's remaining is `ContractInvalid`, journaled the way a budget
    refusal is: the step's INTENT and a STEP_FAILED at attempt 0, no child, no reservation."""
    clock = FakeClock()
    k = _keel(clock)
    from keel.client import Budget

    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]}, budget=Budget(max_tokens=150))
    await _acquire(k, handle.run_id, "w1")

    state = await _state(k, handle.run_id)
    assert state.phase == "FAILED"
    assert state.steps[0].attempts == 0 and state.steps[0].error.startswith("Σ budget_slice.max_tokens 200")
    assert state.children == {} and await k.journal.children(handle.run_id) == []
    assert state.charged.tokens_charged == 0


async def test_cancel_is_asked_first_and_forced_after_the_grace(world) -> None:
    """§7.6.2 end to end. The parent acknowledges, tells both children in the same transaction,
    and parks for `cancel_grace`. One child had already finished. The other was never claimed —
    the shape of a wedged or starved child — so after the grace its lease is taken over and the
    takeover writer closes it: RECOVERY_STARTED{ORPHANED, forced_by}, CANCEL_ACKNOWLEDGED,
    RUN_CANCELLED{forced_by}, with the parent's wake in the same transaction."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")
    a, b = await k.journal.children(handle.run_id)
    await _acquire(k, a.run_id, "ca")                       # a finishes; b is never claimed

    assert await k.journal.insert_signal(
        SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="cancel", payload={"by": "keshav"})
    )
    await _acquire(k, handle.run_id, "w2")

    state = await _state(k, handle.run_id)
    assert state.cancel_acknowledged_at == 0
    assert state.phase == "WAITING_CHILDREN", "acknowledged, not yet cancelled: the child is being asked"
    assert state.wake_at == clock.now() + timedelta(seconds=GRACE)
    assert state.children[a.run_id].state == "COMPLETED"
    assert state.children[b.run_id].state == "CANCELLING"
    [told] = await k.journal.pending_signals(b.run_id)
    assert told.type == "cancel" and told.client_key.startswith(f"cancel:{handle.run_id}:")

    # Inside the grace a wake forces nothing: the store refuses the takeover.
    await _acquire(k, handle.run_id, "w3")
    assert (await _state(k, b.run_id)).phase == "CREATED"
    assert (await _state(k, handle.run_id)).phase == "WAITING_CHILDREN"

    # After it, the timer wakes the parent and the takeover goes through.
    clock.advance(GRACE + 1)
    assert await k.journal.sweep_timers() == 1
    await _acquire(k, handle.run_id, "w4")

    child = await _state(k, b.run_id)
    assert child.phase == "CANCELLED" and child.forced_by == f"parent:{handle.run_id}"
    assert [e.type for e in await k.events(b.run_id)] == [
        "RUN_CREATED", "RECOVERY_STARTED", "CANCEL_ACKNOWLEDGED", "RUN_CANCELLED",
    ]
    [taken] = [e for e in await k.events(b.run_id) if e.type == "RECOVERY_STARTED"]
    assert taken.body.cause == "ORPHANED" and taken.body.forced_by == f"parent:{handle.run_id}"
    [rec] = await k.journal.recoveries(b.run_id)
    assert rec.outcome == "FORCED_CANCEL"

    parent = await _state(k, handle.run_id)
    assert parent.phase == "CANCELLED"
    assert parent.children[b.run_id].state == "CANCELLED" and parent.children[b.run_id].error == "ChildCancelled"
    assert parent.children[b.run_id].usage_settled["tokens_charged"] == 100, "a cancelled child settles at its slice"
    assert parent.charged.tokens_charged >= 100, "and the ledger keeps it charged, in its own unit"
    assert parent.steps[0].state == "CANCELLED"
    # STEP_CANCELLED closes the open step immediately before RUN_CANCELLED, in the epoch that saw
    # the last child terminal (§7.6.2) — and that epoch owes its RECOVERY_COMPLETED like any other.
    tail = [e.type for e in await k.events(handle.run_id)][-5:]
    assert tail == ["SIGNAL_RECEIVED", "CHILD_FAILED", "STEP_CANCELLED", "RECOVERY_COMPLETED", "RUN_CANCELLED"]
    assert await k.journal.stray_children() == []


async def test_a_child_that_acknowledges_in_time_is_never_forced(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
    await _acquire(k, handle.run_id, "w1")
    a, b = await k.journal.children(handle.run_id)
    await _acquire(k, a.run_id, "ca")
    await k.journal.insert_signal(SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="cancel", payload={}))
    await _acquire(k, handle.run_id, "w2")

    await _acquire(k, b.run_id, "cb")                        # drains the cancel at its first boundary
    child = await _state(k, b.run_id)
    assert child.phase == "CANCELLED" and child.forced_by is None and child.cancel_acknowledged_at == 0
    assert [r.outcome for r in await k.journal.recoveries(b.run_id)] == ["TERMINAL"]

    await _acquire(k, handle.run_id, "w3")
    parent = await _state(k, handle.run_id)
    assert parent.phase == "CANCELLED"
    assert parent.children[b.run_id].state == "CANCELLED"
    assert not any(e.body.forced_by for e in await k.events(b.run_id) if e.type == "RECOVERY_STARTED")


async def test_the_reaper_collects_a_child_that_outlived_its_parent(world) -> None:
    """S8's residual, closed by the liveness rule (§17.7): parent terminal, child not. The reaper
    tells the child and, after the grace, takes it over — as a holder, in a new epoch."""

    @as_program(name="noop", version="1.0")
    async def noop(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    clock = FakeClock()
    k = _keel(clock)
    k.register(noop)
    handle = await k.start(noop, {})
    # A child the program never asked for — appended through the public transaction API, which
    # is the only way a child comes to exist — so the parent completes with it still open.
    lease = await k.journal.acquire(handle.run_id, "w0", timedelta(seconds=TTL))
    child_id = uuid7()
    async with k.journal.append(lease) as tx:
        await tx.append(RecoveryStarted(lease_epoch=lease.epoch, cause="RESUME", from_seq=1))
        seq = await tx.append(ChildSpawned(step_index=0, child_run_id=child_id, delegation_id=uuid7()))
        await tx.create_child(
            RunRow(run_id=child_id, run_root_id=handle.run_id, program="research_child",
                   program_version=demo.research_child.version, keel_version="test", phase="CREATED",
                   trace_id=handle.run_id, args={"task": "x"}, parent_run_id=handle.run_id),
            RunCreated(program="research_child", program_version=demo.research_child.version,
                       args={"task": "x"}, parent_run_id=handle.run_id),
            DelegationRow(delegation_id=uuid7(), parent_run_id=handle.run_id, parent_step_index=0,
                          child_run_id=child_id, role="worker", contract={}, budget_reserved={},
                          spawned_seq=seq),
        )
    await k.journal.release(lease)
    await _acquire(k, handle.run_id, "w1")
    assert (await _state(k, handle.run_id)).phase == "COMPLETED"

    reaper = Reaper(k.journal, cancel_grace=GRACE)
    [stray] = await k.journal.stray_children()
    assert stray.run_id == child_id
    assert await reaper.strays() == 0, "told, not yet forced"
    [told] = await k.journal.pending_signals(child_id)
    assert told.client_key == f"cancel:reaper:{child_id}"
    assert await reaper.strays() == 0 and len(await k.journal.pending_signals(child_id)) == 1, "one row per stray"

    clock.advance(GRACE + 1)
    assert await reaper.strays() == 1
    child = await _state(k, child_id)
    assert child.phase == "CANCELLED" and child.forced_by == "reaper"
    assert await k.journal.stray_children() == []
    assert await reaper.strays() == 0


async def test_fan_out_waits_for_a_slot_rather_than_failing(world) -> None:
    """`max_children_in_flight` (§17.5): six contracts, four children at once, the rest as slots
    free. All six results come back in ordinal order."""
    clock = FakeClock()
    k = _keel(clock)
    tasks = [f"t{i}" for i in range(6)]
    handle = await k.start(demo.orchestrator, {"tasks": tasks})
    await _acquire(k, handle.run_id, "w1")
    first = await k.journal.children(handle.run_id)
    assert len(first) == 4

    for i, c in enumerate(first):
        await _acquire(k, c.run_id, f"c{i}")
    await _acquire(k, handle.run_id, "w2")
    later = [c for c in await k.journal.children(handle.run_id) if c.run_id not in {f.run_id for f in first}]
    assert len(later) == 2, "two more, as slots freed"
    assert (await _state(k, handle.run_id)).phase == "WAITING_CHILDREN"

    for i, c in enumerate(later):
        await _acquire(k, c.run_id, f"d{i}")
    await _acquire(k, handle.run_id, "w3")
    state = await _state(k, handle.run_id)
    assert state.phase == "COMPLETED"
    assert [a["task"] for a in state.result["answers"]] == tasks


async def test_the_delegate_step_replays_from_the_journal_and_a_new_schema_is_a_different_step(world) -> None:
    """The result schema is part of the step's identity (§17.8). A redeploy that changes what a
    child is asked to return trips `NondeterminismDetected` at the DELEGATE step rather than
    re-grading children spawned under the old contract."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.orchestrator, {"tasks": ["a"]})
    await _acquire(k, handle.run_id, "w1")
    await _until_idle(k)
    await _acquire(k, handle.run_id, "w2")
    assert (await _state(k, handle.run_id)).phase == "COMPLETED"

    from keel.replay.verify import verify as run_verify

    same = await run_verify(k.journal, handle.run_id, demo.orchestrator.fn, tools=k.tools)
    assert same.ok, same.as_dict()
    assert len(await k.journal.children(handle.run_id)) == 1, "VERIFY spawned nothing"

    async def redeployed(ctx: Any, args: dict[str, Any]) -> Any:
        return await demo.orchestrator.fn(ctx, {**args, "result_schema": {"type": "object", "required": ["verdict"]}})

    changed = await run_verify(k.journal, handle.run_id, redeployed, tools=k.tools)
    assert not changed.ok and changed.diff["step_index"] == 0


# --- the post-phase-8 audit: each test below is a finding that reproduced -----------------------
from keel.client import Budget  # noqa: E402
from keel.providers.protocol import ModelRequest, ModelResponse, Usage  # noqa: E402
from keel.runtime.delegation import Delegation, json_schema_ok  # noqa: E402


class _BillsItsMaxTokens:
    """A provider that charges exactly what a call reserves, so a budget test counts real spend."""

    name = "bills"

    async def count_tokens(self, req: ModelRequest) -> int:
        return 0

    async def complete(self, req: ModelRequest) -> ModelResponse:
        return ModelResponse(text="ok", usage=Usage(input_tokens=req.max_tokens, output_tokens=0))


@as_program(name="spender", version="1.0")
async def spender(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    if args["task"] != "free-fail":
        await ctx.model([{"role": "user", "content": args["task"]}], name="m", max_tokens=100)
    if "fail" in args["task"]:
        raise RuntimeError("failed")
    return {"hits": 1}


@as_program(name="retrying_parent", version="1.0")
async def retrying_parent(ctx: Any, args: dict[str, Any]) -> Any:
    results = await ctx.delegate_many([
        Delegation(program="spender", task=t, on_failure=args.get("on_failure", "retry"), max_retries=1,
                   budget_slice={"max_tokens": 100}, result_schema=args.get("result_schema"))
        for t in args["tasks"]
    ])
    return [r.status for r in results]


def _budget_keel(clock: FakeClock) -> Keel:
    return Keel(journal=MemoryJournal(clock=clock), provider=_BillsItsMaxTokens(),
                programs=[spender, retrying_parent], clock=clock)


async def test_a_child_has_its_own_root_so_a_retry_does_real_work(world) -> None:
    """Children inherited the parent's `run_root_id`, so a retried child's first tool call had the
    same effect key as the failed one's and died on DuplicateEffectKey — retry never did any work."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(
        demo.orchestrator,
        {"tasks": ["a"], "result_schema": {"type": "object", "required": ["verdict"]},
         "on_failure": "retry", "max_retries": 1},
    )
    await _acquire(k, handle.run_id, "w1")
    await _until_idle(k)
    await _acquire(k, handle.run_id, "w2")
    await _until_idle(k)
    await _acquire(k, handle.run_id, "w3")

    for c in await k.journal.children(handle.run_id):
        assert c.run_root_id == c.run_id, "a child's effect keys are its own"
    retried = [c for c in (await _state(k, handle.run_id)).children.values() if c.retry_no == 1]
    assert retried[0].error == "ContractViolation", "the replacement ran and was graded, not refused a key"


async def test_retry_admission_settles_first_and_counts_the_ordinals_still_waiting(world) -> None:
    """Admission checked the failed child's slice before refunding it (refusing a retry that fits),
    and ignored slices promised to ordinals still waiting for a slot (so six children billed 600
    under a 500 budget). Σ reservations ≤ remaining must hold for the whole tree (§17.4, S9)."""
    clock = FakeClock()
    k = _budget_keel(clock)
    fits = await k.start(retrying_parent, {"tasks": ["free-fail"]}, budget=Budget(max_tokens=100))
    await _acquire(k, fits.run_id, "p1")
    [c] = await k.journal.children(fits.run_id)
    await _acquire(k, c.run_id, "c")
    await _acquire(k, fits.run_id, "p2")
    assert [x.policy_applied for x in (await _state(k, fits.run_id)).children.values()][0] == "retry"

    k = _budget_keel(clock)
    tree = await k.start(retrying_parent, {"tasks": ["fail", "b", "c", "d", "e"]}, budget=Budget(max_tokens=500))
    await _until_idle(k, limit=40)
    events = await k.events(tree.run_id)
    peak = max(fold(events[:i]).charged.tokens_charged for i in range(1, len(events) + 1))
    spent = sum([(await _state(k, ch.run_id)).charged.tokens_charged for ch in await k.journal.children(tree.run_id)])
    assert peak <= 500 and spent <= 500, (peak, spent)


async def test_nothing_is_retried_under_a_parent_that_is_cancelling(world) -> None:
    """A child failing after the parent acknowledged a cancel was replaced anyway — by a child with
    no cancel row, which the takeover could never force, running its whole program."""
    clock = FakeClock()
    k = _budget_keel(clock)
    handle = await k.start(retrying_parent, {"tasks": ["a"], "result_schema": {"type": "object", "required": ["verdict"]}},
                           budget=Budget(max_tokens=1000))
    await _acquire(k, handle.run_id, "w1")
    [c0] = await k.journal.children(handle.run_id)
    await k.journal.insert_signal(SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="cancel", payload={}))
    clock.advance(0.001)
    await _acquire(k, c0.run_id, "c0")          # completes with a result that violates the schema
    await _acquire(k, handle.run_id, "w2")     # drains [cancel, child_result]

    assert len(await k.journal.children(handle.run_id)) == 1, "no replacement"
    assert (await _state(k, handle.run_id)).phase == "CANCELLED"


async def test_fail_parent_cancels_the_siblings_and_spawns_nothing_more(world) -> None:
    """§17.6/§17.7: a fatal child failure cancels the subtree first. Siblings used to run to their
    end, and ordinals past the in-flight bound were still spawned after the fatal CHILD_FAILED."""

    @as_program(name="fails_first", version="1.0")
    async def fails_first(ctx: Any, args: dict[str, Any]) -> Any:
        await ctx.now()
        if args["task"] == "t0":
            raise RuntimeError("boom")
        return {"ok": True}

    @as_program(name="fatal_parent", version="1.0")
    async def fatal_parent(ctx: Any, args: dict[str, Any]) -> Any:
        rs = await ctx.delegate_many([Delegation(program="fails_first", task=f"t{i}", on_failure="fail_parent")
                                      for i in range(6)])
        return [r.status for r in rs]

    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), programs=[fails_first, fatal_parent], clock=clock)
    handle = await k.start(fatal_parent, {})
    await _acquire(k, handle.run_id, "p1")
    first = await k.journal.children(handle.run_id)
    # By task, not by position: under a FakeClock every child shares one `created_at`.
    failing = next(c for c in first if c.args["task"] == "t0")
    await _acquire(k, failing.run_id, "c0")
    await _acquire(k, handle.run_id, "p2")

    for sibling in (c for c in first if c.run_id != failing.run_id):
        assert [s.type for s in await k.journal.pending_signals(sibling.run_id)] == ["cancel"]
    await _until_idle(k, limit=40)
    assert len(await k.journal.children(handle.run_id)) == 4, "ordinals 4 and 5 never spawned"
    state = await _state(k, handle.run_id)
    assert state.phase == "FAILED" and state.error.startswith("ChildFailed")


async def test_a_forced_cancel_closes_the_deepest_run_first(world) -> None:
    """§17.7: RUN_CANCELLED of a child follows its own children's terminal events (S8). The parent
    used to take a mid-tree child over while its leaf was still open."""

    @as_program(name="leaf", version="1.0")
    async def leaf(ctx: Any, args: dict[str, Any]) -> Any:
        return {"ok": True}

    @as_program(name="mid", version="1.0")
    async def mid(ctx: Any, args: dict[str, Any]) -> Any:
        [r] = await ctx.delegate_many([Delegation(program="leaf", task="x")])
        return r.status

    @as_program(name="top", version="1.0")
    async def top(ctx: Any, args: dict[str, Any]) -> Any:
        [r] = await ctx.delegate_many([Delegation(program="mid", task="y")])
        return r.status

    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), programs=[leaf, mid, top], clock=clock)
    handle = await k.start(top, {})
    await _acquire(k, handle.run_id, "t1")
    [m] = await k.journal.children(handle.run_id)
    await _acquire(k, m.run_id, "m1")
    [lf] = await k.journal.children(m.run_id)
    await k.journal.insert_signal(SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="cancel", payload={}))
    await _acquire(k, handle.run_id, "t2")      # top acknowledges, asks mid
    clock.advance(1)
    await _acquire(k, m.run_id, "m2")           # mid acknowledges, asks leaf; leaf never answers

    order: list[Any] = []
    for _ in range(6):                          # grace after grace, until the tree is closed
        clock.advance(GRACE + 1)
        await k.journal.sweep_timers()
        while (lease := await k.journal.claim("w", timedelta(seconds=TTL))) is not None:
            if lease.run_id == lf.run_id:
                await k.journal.release(lease)  # the leaf is wedged: claimed, never run
                break
            await _run(k, lease, "w")
        for rid in (lf.run_id, m.run_id, handle.run_id):
            if rid not in order and (await k.journal.run_row(rid)).terminal_at is not None:
                order.append(rid)
    assert order == [lf.run_id, m.run_id, handle.run_id], "leaf, then mid, then top"


async def test_two_reapers_on_one_stray_lose_a_race_not_a_task(world) -> None:
    """A second reaper's takeover fencing the first used to raise `Fenced` out of `Reaper.strays`,
    silently ending that process's reaper loop for good."""
    from keel.events import RunCompleted
    from keel.journal.memory import memory_run_row

    clock = FakeClock()
    j = MemoryJournal(clock=clock)
    pid, cid = uuid7(), uuid7()
    await j.create_run(memory_run_row(run_id=pid, program="p", program_version="v", keel_version="t",
                                      args={}, budget={}, model_config={}),
                       RunCreated(program="p", program_version="v", args={}), runnable_at=clock.now())
    lease = await j.acquire(pid, "w", timedelta(seconds=5))
    async with j.append(lease) as tx:
        await tx.append(RecoveryStarted(lease_epoch=lease.epoch, cause="RESUME", from_seq=1))
        s = await tx.append(ChildSpawned(step_index=0, child_run_id=cid, delegation_id=uuid7()))
        await tx.create_child(
            RunRow(run_id=cid, run_root_id=cid, program="kid", program_version="v", keel_version="t",
                   phase="CREATED", trace_id=pid, args={}, parent_run_id=pid),
            RunCreated(program="kid", program_version="v", args={}, parent_run_id=pid),
            DelegationRow(delegation_id=uuid7(), parent_run_id=pid, parent_step_index=0, child_run_id=cid,
                          role="worker", contract={}, budget_reserved={}, spawned_seq=s),
        )
        await tx.append(RunCompleted(result={}))
    await j.release(lease, phase="COMPLETED")

    a, b = Reaper(j, cancel_grace=GRACE), Reaper(j, cancel_grace=GRACE)
    await a.strays()
    clock.advance(GRACE + 1)
    real_run_row = j.run_row
    ticked: list[int] = []

    async def run_row(run_id: Any) -> Any:
        # A has taken the lease and folded the journal; its closing append is next. B ticks now.
        if run_id == cid and not ticked:
            ticked.append(-1)                   # set first: B's own read comes back through here
            ticked[0] = await b.strays()
        return await real_run_row(run_id)

    j.run_row = run_row  # type: ignore[method-assign]
    assert await a.strays() == 0, "A lost the race — and did not raise"
    j.run_row = real_run_row  # type: ignore[method-assign]
    assert ticked == [1]
    assert [r.outcome for r in await j.recoveries(cid)] == ["FENCED", "FORCED_CANCEL"]
    assert (await j.run_row(cid)).terminal_at is not None


async def test_a_paused_parent_stays_paused_when_its_child_finishes(world) -> None:
    @as_program(name="quick", version="1.0")
    async def quick(ctx: Any, args: dict[str, Any]) -> Any:
        return {"ok": True}

    @as_program(name="pausable", version="1.0")
    async def pausable(ctx: Any, args: dict[str, Any]) -> Any:
        await ctx.delegate_many([Delegation(program="quick", task="x")])
        await ctx.now()
        return "done"

    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), programs=[quick, pausable], clock=clock)
    handle = await k.start(pausable, {})
    await _acquire(k, handle.run_id, "p1")
    [child] = await k.journal.children(handle.run_id)
    await k.journal.insert_signal(SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="pause", payload={}))
    await _acquire(k, handle.run_id, "p2")
    await _acquire(k, child.run_id, "c1")
    await _until_idle(k)
    assert (await _state(k, handle.run_id)).phase == "PAUSED", "a child_result does not lift a pause"


def test_result_schema_is_graded_all_the_way_down() -> None:
    """Grading checked top-level required keys and types only: bounds, literals, Optional unions and
    nested models all passed (§17.8's injection wall)."""
    from typing import Literal

    from pydantic import BaseModel, Field

    class Item(BaseModel):
        id: int

    class Verdict(BaseModel):
        score: int = Field(le=10)
        kind: Literal["yes", "no"]
        note: str | None = None
        items: list[Item] = []

    schema = Verdict.model_json_schema()
    assert json_schema_ok(schema, {"score": 3, "kind": "yes", "note": None, "items": [{"id": 1}]}) == (True, None)
    for bad in (
        {"score": 99, "kind": "yes"},
        {"score": 1, "kind": "maybe"},
        {"score": 1, "kind": "no", "note": 7},
        {"score": 1, "kind": "no", "items": [{"id": "not-an-int"}]},
    ):
        ok, why = json_schema_ok(schema, bad)
        assert not ok and why, bad
