"""Approvals: the zero-compute wait, and the binding that makes it mean something (§4.10, §7.5).

Two properties, and they are different claims.

**The wait costs nothing.** A run parked on an approval holds no lease *and* has no `runnable_at`.
Both NULLs matter: the first is why it costs no compute, the second is why it costs no *ticks* —
nothing polls it. A week of waiting is one row and one timer sweep. That is the headline property
§29.1 says to cut last.

**The approval names the effect it authorises.** `binds_effect_key` is computed before anyone
decides, because the runtime owns the step counter, so a grant authorises `effect_key(root, i+1,
tool, args)` and not "whatever happens next". Without it, an approval is a permission slip with the
payee left blank — and S7 ("exactly one GRANTED approval per gated effect, ≤ 1 applied") would be
unenforceable at the only moment it matters, which is *before* the effect.
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
        programs=[demo.tool_chain, demo.gated_tool_chain],
        clock=clock,
    )


async def _work(k: Keel, worker_id: str = "w1") -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is None:
        return
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


def _send(k: Keel, run_id, type_: str, **payload) -> Any:
    return k.journal.insert_signal(
        SignalRow(signal_id=uuid7(), run_id=run_id, type=type_, payload=payload)
    )


async def test_the_park_costs_no_lease_and_no_ticks(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "gate me"})

    await _work(k)

    state = fold(await k.events(handle.run_id))
    row = await k.journal.run_row(handle.run_id)
    assert state.phase == "WAITING_APPROVAL"
    assert state.waiting_reason == "approval"
    assert row.lease_expires_at is None, "no lease: zero compute"
    assert row.runnable_at is None, "and nothing polls it: zero ticks"
    assert world.applied_counts() == {}, "nothing was done before the human was asked"

    # And a worker looking for work finds none — the proof that the park is not a busy wait.
    assert await k.journal.claim("w2", timedelta(seconds=TTL)) is None


async def test_the_whole_request_commits_in_one_transaction(world) -> None:
    """INTENT, STARTED, APPROVAL_REQUESTED and RUN_WAITING together. A crash anywhere inside leaves
    either no step or a parked one — never a half-requested approval, and never a second
    `approval_id` for one gate (§7.3.1)."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "atomic"})
    await _work(k)

    events = await k.events(handle.run_id)
    seqs = {e.type: e.seq for e in events}
    assert {"STEP_INTENDED", "STEP_ATTEMPT_STARTED", "APPROVAL_REQUESTED", "RUN_WAITING"} <= set(seqs)
    ordered = [e.type for e in events if e.type in
               ("STEP_INTENDED", "STEP_ATTEMPT_STARTED", "APPROVAL_REQUESTED", "RUN_WAITING")]
    assert ordered == ["STEP_INTENDED", "STEP_ATTEMPT_STARTED", "APPROVAL_REQUESTED", "RUN_WAITING"]

    state = fold(events)
    [approval] = state.approvals.values()
    assert approval.state == "REQUESTED"
    assert approval.binds_effect_key is not None, "a gated approval names its effect"


async def test_approve_wakes_the_run_and_the_bound_effect_happens_once(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "ship it"})
    await _work(k, "w1")

    assert await _send(k, handle.run_id, "approve", by="keshav")
    assert (await k.journal.run_row(handle.run_id)).runnable_at is not None, "the signal is the wake"

    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    [approval] = state.approvals.values()
    assert approval.state == "GRANTED" and approval.by == "keshav"
    assert state.steps[0].result["decision"] == "granted", "the program sees a value, not an exception"
    assert world.applied_counts()["issues.create#1"] == 1, "exactly one applied effect per approval"


async def test_a_rejection_completes_the_step_and_refuses_the_bound_call(world) -> None:
    """The APPROVAL step always completes — for all three decisions — and what a rejection *means*
    is the program's business. What is not the program's business is whether the gated effect may
    run: the runtime refuses it before an attempt starts, so no effect was ever reachable."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "nope"})
    await _work(k, "w1")
    await _send(k, handle.run_id, "reject", by="keshav", reason="too risky")
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    assert state.steps[0].result["decision"] == "rejected"
    assert state.result["answer"] == "not filed: rejected"
    assert world.applied_counts() == {}, "nothing reached the World"


async def test_the_runtime_refuses_a_gated_call_the_program_makes_anyway(world) -> None:
    """The program above returns early on a rejection. A program that did *not* — one that ignored
    the decision and called the tool — must still be refused, because S7 is the runtime's rule and
    not the program's good manners. `attempt_no=0` is the pre-dispatch marker: no attempt was
    started, so no effect was reachable (§7.5)."""

    from keel.client import program as as_program

    @as_program(name="ignores_rejection", version="1.0")
    async def ignores_rejection(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        issue = {"title": "regardless", "body": "b"}
        await ctx.approve({"what": "file"}, gates=("create_issue", issue))
        return await ctx.tool("create_issue", **issue)

    clock = FakeClock()
    k = _keel(clock)
    k.register(ignores_rejection)
    handle = await k.start(ignores_rejection, {})
    await _work(k, "w1")
    await _send(k, handle.run_id, "reject", by="keshav")
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "FAILED"
    assert state.steps[1].error == "ApprovalRejected"
    assert state.steps[1].attempts == 0, "refused before an attempt, so no effect was reachable"
    assert world.applied_counts() == {}
    effects = await k.journal.effects(handle.run_id)
    assert [e.status for e in effects] == ["DENIED"]


async def test_a_second_decision_is_ignored_and_the_first_one_stands(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "once"})
    await _work(k, "w1")
    await _send(k, handle.run_id, "approve", by="first")
    await _send(k, handle.run_id, "reject", by="second")
    await _work(k, "w2")

    events = await k.events(handle.run_id)
    decided = [e for e in events if e.type == "APPROVAL_DECIDED"]
    assert len(decided) == 1 and decided[0].body.decision == "granted"
    ignored = [e for e in events if e.type == "SIGNAL_IGNORED"]
    assert [e.body.reason for e in ignored] == ["approval_terminal"]
    assert world.applied_counts()["issues.create#1"] == 1


async def test_expiry_is_judged_by_the_store_clock_and_outranks_arrival_order(world) -> None:
    """The rule that is deliberately not "first row wins". A decision made in time but *drained*
    late — a worker that died and took four seconds to be replaced — must not be honoured on the
    wrong side of a deadline somebody else is relying on."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "too late", "expires_in": 60})
    await _work(k, "w1")

    await _send(k, handle.run_id, "approve", by="slow")   # inserted before the deadline …
    clock.advance(61)                                      # … drained after it
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    [approval] = state.approvals.values()
    assert approval.state == "EXPIRED", "expiry outranks seq order"
    assert state.steps[0].result["decision"] == "expired"
    assert world.applied_counts() == {}
    ignored = [e for e in await k.events(handle.run_id) if e.type == "SIGNAL_IGNORED"]
    assert [e.body.reason for e in ignored] == ["expired"]


async def test_the_timer_sweep_is_what_wakes_a_deadline_nobody_is_watching(world) -> None:
    """A parked run is polled by nothing, so something has to notice the deadline passed. The sweep
    inserts one `timer` row per due run, keyed so two schedulers firing at once produce one."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "nobody answers", "expires_in": 60})
    await _work(k, "w1")

    assert await k.journal.sweep_timers() == 0, "not due yet"
    clock.advance(61)
    assert await k.journal.sweep_timers() == 1
    assert await k.journal.sweep_timers() == 0, "idempotent: one row per deadline, not per sweep"

    await _work(k, "w2")
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    assert state.steps[0].result["decision"] == "expired"
    assert state.result["answer"] == "not filed: expired"


async def test_a_crash_while_parked_does_not_re_request_the_approval(world) -> None:
    """§7.3.1's reason for treating a waiting step apart from an abandoned attempt. Its normal life
    *is* STARTED-without-outcome, for days. Re-attempting it would mint a second `approval_id`, and
    then "exactly one GRANTED approval per gated effect" would be false by construction."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "still parked"})
    await _work(k, "w1")

    # A spurious wake: something makes the run runnable with no decision in the inbox.
    clock.advance(TTL + 2)
    await k.journal.reap()
    await _send(k, handle.run_id, "custom", note="not a decision")
    await _work(k, "w2")

    events = await k.events(handle.run_id)
    assert len([e for e in events if e.type == "APPROVAL_REQUESTED"]) == 1, "requested once, ever"
    state = fold(events)
    assert state.phase == "WAITING_APPROVAL", "parked again, for the price of one row"
    assert len(state.approvals) == 1

    # And it still works afterwards.
    await _send(k, handle.run_id, "approve", by="eventually")
    await _work(k, "w3")
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert world.applied_counts()["issues.create#1"] == 1


async def test_a_granted_run_replays_without_asking_again(world) -> None:
    """The property the whole park rests on: after the decision, re-execution returns `granted`
    from the journal. A policy or prompt edit while the run sat parked cannot manufacture a
    disagreement, which is the point of parking cheaply for days."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "replay me"})
    await _work(k, "w1")
    await _send(k, handle.run_id, "approve", by="keshav")
    await _work(k, "w2")

    from keel.replay.verify import verify as run_verify

    out = await run_verify(k.journal, handle.run_id, demo.gated_tool_chain.fn, tools=k.tools)
    assert out.ok, out.as_dict()
    assert await k.journal.pending_signals(handle.run_id) == []


# --- the post-phase-8 audit: each test below is a finding that reproduced -----------------------
from keel.client import program as _program  # noqa: E402


@_program(name="two_gates", version="1.0")
async def two_gates(ctx: Any, args: dict[str, Any]) -> str:
    for env in ("staging", "prod"):
        issue = {"title": f"deploy {env}", "body": env}
        decision = await ctx.approve({"env": env}, gates=("create_issue", issue))
        if decision["decision"] != "granted":
            return decision["decision"]
        await ctx.tool("create_issue", **issue)
    return "both"


async def test_a_click_naming_a_decided_gate_never_decides_the_next_one(world) -> None:
    """A retried approve aimed at gate A, drained while gate B is open, used to grant B — deploying
    to prod on a click nobody made for prod. The decision names its gate and is judged against it."""
    clock = FakeClock()
    k = _keel(clock)
    k.register(two_gates)
    handle = await k.start(two_gates, {})
    await _work(k, "w1")
    [a] = fold(await k.events(handle.run_id)).approvals.values()
    await _send(k, handle.run_id, "approve", by="alice", approval_id=str(a.approval_id))
    await _work(k, "w2")                                     # A granted, staging filed, parked on B
    await _send(k, handle.run_id, "approve", by="retry", approval_id=str(a.approval_id))
    await _work(k, "w3")                                     # the stale click is drained at B

    state = fold(await k.events(handle.run_id))
    b = next(x for x in state.approvals.values() if x.step_index == 2)
    assert b.state == "REQUESTED", "prod was never approved"
    assert sum(world.applied_counts().values()) == 1
    ignored = [e.body.reason for e in await k.events(handle.run_id) if e.type == "SIGNAL_IGNORED"]
    assert ignored == ["approval_terminal"]


async def test_the_program_is_handed_exactly_the_decision_the_journal_records(world) -> None:
    """Two copies of the decision once differed by `decided_at`: a program that passed it on issued
    different args live than on replay, and suspended for nondeterminism with unchanged code."""

    @_program(name="passes_it_on", version="1.0")
    async def passes_it_on(ctx: Any, args: dict[str, Any]) -> Any:
        decision = await ctx.approve({"what": "note it"})
        return {"seen": decision}

    clock = FakeClock()
    k = _keel(clock)
    k.register(passes_it_on)
    handle = await k.start(passes_it_on, {})
    await _work(k, "w1")
    await _send(k, handle.run_id, "approve", by="alice")
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    assert state.result["seen"] == state.steps[0].result
    assert state.result["seen"]["decided_at"] is not None

    from keel.replay.verify import verify as run_verify

    out = await run_verify(k.journal, handle.run_id, passes_it_on.fn, tools=k.tools)
    assert out.ok, out.as_dict()


@pytest.mark.parametrize("slip", ["other_args", "other_kind"])
async def test_a_bound_approval_refuses_anything_but_the_call_it_names(world, slip: str) -> None:
    """`ApprovalBindingError` was declared and never raised: a granted approval for one issue let a
    different issue — or anything else — run ungated at i+1. The step after a bound approval must be
    exactly the bound call, or it fails before an attempt (§7.5, §24.2)."""

    @_program(name=f"slips_{slip}", version="1.0")
    async def slips(ctx: Any, args: dict[str, Any]) -> Any:
        await ctx.approve({"what": "one issue"}, gates=("create_issue", {"title": "approved", "body": "b"}))
        if slip == "other_args":
            return await ctx.tool("create_issue", title="something else", body="b")
        return await ctx.now()

    clock = FakeClock()
    k = _keel(clock)
    k.register(slips)
    handle = await k.start(slips, {})
    await _work(k, "w1")
    await _send(k, handle.run_id, "approve", by="alice")
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "FAILED"
    assert state.steps[1].error.startswith("ApprovalBindingError") and state.steps[1].attempts == 0
    assert world.applied_counts() == {}
    if slip == "other_args":
        assert [e.status for e in await k.journal.effects(handle.run_id)] == ["DENIED"]


async def test_expires_in_zero_is_a_deadline_already_due(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "now or never", "expires_in": 0})
    await _work(k, "w1")
    assert (await k.journal.run_row(handle.run_id)).wake_at == clock.now(), "0 was read as 'no deadline'"
    assert await k.journal.sweep_timers() == 1
    await _work(k, "w2")
    [approval] = fold(await k.events(handle.run_id)).approvals.values()
    assert approval.state == "EXPIRED"


async def test_an_approve_drained_after_a_cancel_is_ignored(world) -> None:
    """§7.5.1: cancel then approve in one drain used to record a GRANTED approval — an authorisation
    nobody would ever act on — on a cancelled run."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "never mind"})
    await _work(k, "w1")
    await _send(k, handle.run_id, "cancel", reason="changed my mind")
    await _send(k, handle.run_id, "approve", by="alice")
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "CANCELLED"
    assert [a.state for a in state.approvals.values()] == ["REQUESTED"]
    ignored = [e.body.reason for e in await k.events(handle.run_id) if e.type == "SIGNAL_IGNORED"]
    assert ignored == ["step_terminal"]


async def test_a_signal_racing_the_first_park_is_drained_not_parked_over(world) -> None:
    """§5.4 (4): the release is the park's last statement, guarded by `runnable_at IS NULL`. A row
    that lands after the boundary drain and before the park must roll the park back, be drained,
    and the park then commits — once, with nothing left unconsumed."""
    from keel.runtime import hooks

    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "race me"})

    def land_a_signal(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:intent_commit" and detail.get("kind") == "approval":
            k.journal._put_signal(SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="custom", payload={}))

    hooks.install(land_a_signal)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()

    events = await k.events(handle.run_id)
    row = await k.journal.run_row(handle.run_id)
    assert fold(events).phase == "WAITING_APPROVAL"
    assert len([e for e in events if e.type == "APPROVAL_REQUESTED"]) == 1
    assert row.lease_expires_at is None and row.runnable_at is None
    assert await k.journal.pending_signals(handle.run_id) == [], "the racing row was drained"


async def test_an_approve_racing_the_re_park_is_decided_not_lost(world, monkeypatch) -> None:
    """The lost wakeup itself: an approve that commits between a woken run's drain and its re-park
    used to have its wake erased by the release, leaving the human's decision unconsumed for ever."""
    from keel.runtime.steps import StepEngine

    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.gated_tool_chain, {"title": "decide in the window"})
    await _work(k, "w1")
    await _send(k, handle.run_id, "custom")                  # a spurious wake: nothing decides
    [approval] = fold(await k.events(handle.run_id)).approvals.values()

    original = StepEngine._commit_park
    raced: list[bool] = []

    async def approve_in_the_window(self: Any, *args: Any, **kwargs: Any) -> bool:
        if not raced:
            raced.append(True)
            self.journal._put_signal(SignalRow(
                signal_id=uuid7(), run_id=handle.run_id, type="approve",
                payload={"by": "alice", "approval_id": str(approval.approval_id)},
            ))
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(StepEngine, "_commit_park", approve_in_the_window)
    await _work(k, "w2")

    assert raced
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED", state.phase
    assert [a.state for a in state.approvals.values()] == ["GRANTED"]
    assert world.applied_counts()["issues.create#1"] == 1
    assert await k.journal.pending_signals(handle.run_id) == []
