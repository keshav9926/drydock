"""`KeelMachine` — §12.3's rules over the real runtime, §12.4's invariants after every one.

The conformance table fires one fault at one boundary and checks the window it leaves. This asks the
harder question: what happens when a worker paused past its lease comes back after a successor has
drained a cancel, while a child it spawned is being taken over and a stale approval click lands? Those
sequences are where a recovery table is actually wrong, and nobody writes them by hand.

Rules, mapped to §12.3 (the fault type each mirrors is in `sim.to_fault_spec`):

    advance(n)              the workload progressing: land up to n held calls with `ok`
    complete_effect         land one held call with a generated outcome (ok · 5xx · refused · dropped)
    crash_at_boundary       kill a worker at a hook boundary, or mid-effect (`during:effect_exec`)
    drain                   SIGTERM with a drawn grace; past the grace it is a kill
    restart_worker          the reaper's sweeps, then the real claim, into a free slot
    retry                   tick past a journaled `next_attempt_at` or an in-process backoff
    deliver_signal          approve · reject (naming the open, a decided, an unknown or no approval),
                            cancel · pause · resume · custom — to the root or any open child
    duplicate_signal        the last signal again, same `client_key` or fresh
    duplicate_response      a request whose attempt timed out lands late
    timeout                 tick past a held attempt's deadline
    lease_expiry            pause a worker and tick past its lease; the reaper marks the run orphaned
    zombie_resume           the paused worker resumes: its request lands, its outcome must be fenced
    tick                    time passes; live workers heartbeat on schedule
    expire_approval         tick past an open approval's `expires_at`
    journal_fault           the next n commits at a boundary raise `StoreUnavailable`
    stray_child             a child whose parent is already terminal, for the reaper's liveness rule

Delegation's rules are the script's: `delegate` spawns 1–2 children whose own scripts complete, fail
or violate the contract under `escalate | retry | fail_parent`; a cancel to the parent with children
open, then time past `cancel_grace`, is the forced takeover.

**Seams, not rules.** §29.2's segments and streaming are Phase 9 mechanisms and do not exist:
`truncate_stream(k)` (`model_stream_truncate`, `during:stream(chunk=k)`) and a segment rule (a forced
`SEGMENT_STARTED` at `before:segment_write`, judged by C2) go beside `timeout` and `journal_fault`
when they land — each is one `Sim` method and one `_entry` form in `sim.to_fault_spec`.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from hypothesis import HealthCheck, settings, target
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

from keel.runtime.hooks import BOUNDARIES
from keel.state.fold import fold
from tests.property.sim import JOURNAL_FAULT_BOUNDARIES, SLOTS, TTL, Sim, ToolDecl

MAX_SIGNALS = 4

# --- generators (§12.5): every choice simplest-first, so a surviving value is load-bearing ------
TOOL = st.builds(
    ToolDecl,
    name=st.just("t"),
    cls=st.sampled_from(("PURE", "IDEMPOTENT", "EXTERNAL")),
    resolution=st.sampled_from(("escalate", "probe")),
    dedup=st.sampled_from((True, False)),
    gated=st.sampled_from((False, True)),
    timeout=st.sampled_from((1.0, 5.0)),
)
CHILD_OP = st.one_of(
    st.fixed_dictionaries({"op": st.just("tool"), "tool": st.integers(0, 2)}),
    st.fixed_dictionaries({"op": st.just("model")}),
)
OP = st.one_of(
    st.fixed_dictionaries({"op": st.just("tool"), "tool": st.integers(0, 2), "expires_in": st.sampled_from((None, 30.0))}),
    st.fixed_dictionaries({"op": st.just("model")}),
    st.fixed_dictionaries({
        "op": st.just("delegate"),
        "n": st.integers(1, 2),
        "child": st.lists(CHILD_OP, max_size=2),
        "on_failure": st.sampled_from(("escalate", "retry", "fail_parent")),
        "violate": st.sampled_from((False, True)),
        "fail": st.sampled_from((False, True)),
    }),
)


def resolve(tools: list[ToolDecl], script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tool indices to names. A gated tool is only ever called through its approval, and a child
    only calls ungated tools, so S7 can hold every application at a gated endpoint to a grant."""
    ungated = [t.name for t in tools if not t.gated]

    def child(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"op": "tool", "tool": ungated[c["tool"] % len(ungated)]} if c["op"] == "tool" and ungated
                else {"op": "model"} for c in ops]

    out = []
    for op in script:
        op = dict(op)
        if op["op"] == "tool":
            t = tools[op["tool"] % len(tools)]
            op.update(tool=t.name, gated=t.gated)
            if not t.gated:
                op.pop("expires_in")
        elif op["op"] == "delegate":
            op["child"] = child(op["child"])
        out.append(op)
    return out


class KeelMachine(RuleBasedStateMachine):
    """Real journal, worker, engine, reaper and takeover; a sim clock, an in-process World that
    holds every call, and workers that die, pause and resume as tasks (`tests/property/sim.py`)."""

    def __init__(self) -> None:
        super().__init__()
        self.sim: Sim | None = None
        #: Set by every rule, cleared by the invariant that follows it. Still set at teardown means
        #: the example already failed, and the teardown checks would only bury that failure.
        self.pending = True

    @property
    def go(self) -> Sim:
        self.pending = True
        return self.sim

    @initialize(tools=st.lists(TOOL, min_size=1, max_size=3), script=st.lists(OP, min_size=1, max_size=6),
                retry=st.sampled_from(("none", "retry")), model_retry=st.sampled_from(("none", "retry")))
    def start(self, tools: list[ToolDecl], script: list[dict[str, Any]], retry: str, model_retry: str) -> None:
        tools = [replace(t, name=f"t{i}") for i, t in enumerate(tools)]
        self.sim = Sim(tools, resolve(tools, script), retry=retry, model_retry=model_retry)

    # --- the workload progressing ---------------------------------------------------------------
    @precondition(lambda self: any(h.worker.state == "live" for h in self.sim.completable()))
    @rule(n=st.integers(1, 4))
    def advance(self, n: int) -> None:
        self.go.advance(n)

    @precondition(lambda self: bool(self.sim.completable()))
    @rule(data=st.data(), outcome=st.sampled_from(("error", "rejected", "dropped")))  # `ok` is `advance`
    def complete_effect(self, data: st.DataObject, outcome: str) -> None:
        held = self.sim.completable()
        self.go.complete(held[data.draw(st.integers(0, len(held) - 1), label="held")], outcome)

    @precondition(lambda self: any(self.sim.slot(s) is None for s in SLOTS) and self.sim.claimable())
    @rule(slot=st.sampled_from(SLOTS))
    def restart_worker(self, slot: str) -> None:
        self.go.restart_worker(slot)

    # --- processes ------------------------------------------------------------------------------
    @precondition(lambda self: bool(self.sim.live()) or self.sim.claimable())
    @rule(slot=st.sampled_from(SLOTS), boundary=st.sampled_from(("during:effect_exec", *BOUNDARIES)))
    def crash_at_boundary(self, slot: str, boundary: str) -> None:
        self.go.crash(slot, boundary)

    @precondition(lambda self: bool(self.sim.live()))
    @rule(slot=st.sampled_from(SLOTS), grace=st.sampled_from((60.0, 1.0)))
    def drain(self, slot: str, grace: float) -> None:
        self.go.drain(slot, grace)

    @precondition(lambda self: bool(self.sim.live()))
    @rule(slot=st.sampled_from(SLOTS))
    def lease_expiry(self, slot: str) -> None:
        self.go.lease_expiry(slot)

    @precondition(lambda self: any(w.state == "paused" for w in self.sim.workers.values()))
    @rule(slot=st.sampled_from(SLOTS))
    def zombie_resume(self, slot: str) -> None:
        self.go.zombie_resume(slot)

    # --- time -----------------------------------------------------------------------------------
    @rule(seconds=st.sampled_from((0.5, 2.0, 11.0, TTL + 1)))
    def tick(self, seconds: float) -> None:
        self.go.tick(seconds)

    @precondition(lambda self: any(h.awaited and h.worker.state == "live" for h in self.sim.held))
    @rule(data=st.data())
    def timeout(self, data: st.DataObject) -> None:
        held = [h for h in self.sim.held if h.awaited and h.worker.state == "live"]
        self.go.timeout(held[data.draw(st.integers(0, len(held) - 1), label="held")])

    @precondition(lambda self: bool(self.sim.late()))
    @rule(data=st.data())
    def duplicate_response(self, data: st.DataObject) -> None:
        late = self.sim.late()
        self.go.duplicate_response(late[data.draw(st.integers(0, len(late) - 1), label="late")])

    @precondition(lambda self: bool(_backoffs(self.sim)))
    @rule()
    def retry(self) -> None:
        self.go.tick_to(min(_backoffs(self.sim)))

    @precondition(lambda self: bool(_approval_deadlines(self.sim)))
    @rule()
    def expire_approval(self) -> None:
        self.go.tick_to(min(_approval_deadlines(self.sim)))
        self.sim.log.append({"rule": "expire_approval"})

    # --- the inbox ------------------------------------------------------------------------------
    # Signals are capped per example. Uncapped, they were a quarter of every run's steps and a cancel
    # ended most runs before an effect was ever in flight — the machine explored the inbox and little else.
    @precondition(lambda self: bool(self.sim.open_runs()) and self.sim.signals_tried < MAX_SIGNALS)
    @rule(data=st.data(), kind=st.sampled_from(("approve", "reject", "cancel", "pause", "resume", "custom")),
          which=st.sampled_from(("open", "stale", "unknown", "none")))
    def deliver_signal(self, data: st.DataObject, kind: str, which: str) -> None:
        runs = self.sim.open_runs()
        self.go.deliver(runs[data.draw(st.integers(0, len(runs) - 1), label="run")], kind, which)

    @precondition(lambda self: self.sim.signals_sent and self.sim.signals_tried < MAX_SIGNALS
                  and self.sim.signals_sent[-1].run_id in self.sim.open_runs())
    @rule(same_key=st.sampled_from((True, False)))
    def duplicate_signal(self, same_key: bool) -> None:
        self.go.duplicate_signal(same_key)

    # --- the store ------------------------------------------------------------------------------
    @precondition(lambda self: (bool(self.sim.live()) or self.sim.claimable()) and sum(self.sim.journal_faults.values()) < 3)
    @rule(boundary=st.sampled_from(JOURNAL_FAULT_BOUNDARIES), n=st.integers(1, 2))
    def journal_fault(self, boundary: str, n: int) -> None:
        self.go.journal_faults[boundary] += n

    @precondition(lambda self: not self.sim.stray_parents and bool(self.sim.open_runs()))
    @rule(child=st.lists(CHILD_OP, max_size=2))
    def stray_child(self, child: list[dict[str, Any]]) -> None:
        tools = list(self.sim.decls.values())
        self.go.stray_child(resolve(tools, [{"op": "delegate", "n": 1, "child": child, "on_failure": "escalate",
                                             "violate": False, "fail": False}])[0]["child"])

    # --- invariants -----------------------------------------------------------------------------
    @invariant()
    def invariants_hold(self) -> None:
        if self.sim is not None:
            self.sim.check()
            self.pending = False

    def teardown(self) -> None:
        if self.sim is None:
            return
        try:
            if not self.pending:
                # Steer generation toward examples whose rules reached more of the runtime: a run that
                # ends in four rules explores nothing the next example will not. Once per example.
                target(float(len(self.sim.reached)), label="event types and faults reached")
                target(float(sum(1 for h in self.sim.held if h.decl is not None)), label="effects held")
                self.sim.quiesce()
                self.sim.check_teardown()
        finally:
            self.sim.close()


def _backoffs(sim: Sim) -> list[Any]:
    """When a retry the runtime decided on comes due: a parked backoff's `wake_at`, or a live
    worker's in-process backoff timer."""
    parked = [r.wake_at for r in sim.journal._runs.values() if r.phase == "SLEEPING" and r.wake_at is not None]
    sleeping = [t[0] for t in sim.clock.timers if t[2] == "sleep" and t[1] is not None and t[1].state == "live"]
    return parked + sleeping


def _approval_deadlines(sim: Sim) -> list[Any]:
    return [r.wake_at for r in sim.journal._runs.values() if r.phase == "WAITING_APPROVAL" and r.wake_at is not None]


def test_the_sim_can_actually_lose_and_recover_a_run() -> None:
    """The machine's own smoke test. Every rule is allowed to be a no-op, and a machine where every
    rule *is* one explores thousands of sequences of nothing and reports green. This pins one that
    must do real work: a kill mid-effect, the request landing anyway, and a successor that probes
    rather than re-fires."""
    sim = Sim([ToolDecl("t0", cls="EXTERNAL", resolution="probe", dedup=False)],
              [{"op": "tool", "tool": "t0", "gated": False}])
    try:
        assert sim.restart_worker("W0")
        [held] = sim.completable()
        sim.crash("W0", "during:effect_exec")
        assert sim.workers["W0"].state == "dead" and held.orphaned
        sim.complete(held, "ok")
        assert sim.world.applied_counts() == {"t0.call#1": 1}, "the request had left; it landed"
        sim.check()

        sim.tick(TTL + 2)
        assert sim.restart_worker("W1"), "a successor finds its work in the journal"
        state = fold(sim.events(sim.root))
        assert state.phase == "COMPLETED", state.phase
        assert state.steps[0].state == "RESOLVED_COMPLETED", "probed, not re-fired"
        assert sim.world.applied_counts() == {"t0.call#1": 1}
        sim.check()
        sim.quiesce()
        sim.check_teardown()
    finally:
        sim.close()


#: `ci` is what `.github/workflows/ci.yml` runs (with `--hypothesis-seed=0`); `deep` is for a
#: targeted local run: `KEEL_PBT_PROFILE=deep uv run pytest tests/property/test_runtime_machine.py`.
PROFILES = {
    "ci": dict(max_examples=200, stateful_step_count=40),
    "deep": dict(max_examples=2000, stateful_step_count=60),
}
KeelMachine.TestCase.settings = settings(
    **PROFILES[os.environ.get("KEEL_PBT_PROFILE", "ci")],
    deadline=None,
    # One bug at a time: shrinking several distinct failures at once ran into Hypothesis's own
    # five-minute shrink limit and left 40-rule examples nobody could read.
    report_multiple_bugs=False,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
)
TestKeelMachine = KeelMachine.TestCase
