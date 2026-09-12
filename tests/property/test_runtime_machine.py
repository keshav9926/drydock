"""`KeelMachine` — crashes in sequences nobody wrote down (§12.3, §28.6).

The conformance table fires one fault at one boundary and checks the window it leaves. This asks
the harder question: what happens when a crash at `after:effect_exec` is followed by a store
outage during the recovery, and then the successor is fenced before it can finish? Those sequences
are where a recovery table is actually wrong, and there are more of them than anyone will write by
hand.

The invariants are checked after **every** rule, not only at the end, and they are the same
functions the benchmark verifier calls (§28.6's mitigation for the sim drifting from the runtime).
Three more are checked here that a single trial cannot see:

    monotonic world     the World never *un*-applies; a rule may only add to it
    claims hold always  EXTERNAL may apply more than once, PURE and IDEMPOTENT may not, at every
                        intermediate state and not merely at the terminal one
    terminal is final   once a run is COMPLETED no later rule may move it

The last one is the one worth having. A run that reaches COMPLETED and then does more work — a
zombie that comes back, a successor that re-runs a settled step — passes every end-state check
ever written, because by the time anyone looks it has settled again.
"""

from __future__ import annotations

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

from crashproof.verifier import invariants as verifier
from keel.runtime.hooks import BOUNDARIES
from tests.property.sim import TTL, Sim

#: Boundaries a fault may be aimed at. All ten that exist, because the point of the machine is the
#: sequences rather than any one of them.
AIMABLE = sorted(BOUNDARIES)
#: Which of the run's *still-unsettled* steps to aim at, as an index into them rather than as a
#: step number: a fault aimed behind the run fires nothing, and a machine that spends its budget
#: aiming behind the run explores sequences of no-ops. `None` means "wherever this boundary fires
#: first", which is how the lease boundaries are reached at all — they carry no step.
WHICH_STEP = st.one_of(st.none(), st.integers(min_value=0, max_value=4))

JUDGED = ("S1", "S3", "S4", "S5", "C1")


class KeelMachine(RuleBasedStateMachine):
    """Real journal, real engine, real program; a fake clock, the harness's World, and crashes
    delivered as `BaseException` at named boundaries (`tests/property/sim.py`)."""

    def __init__(self) -> None:
        super().__init__()
        self.sim: Sim | None = None
        self.applied_high_water = 0
        self.was_terminal = False

    @initialize(variant=st.sampled_from(("EXTERNAL", "IDEMPOTENT")))
    def start(self, variant: str) -> None:
        self.sim = Sim(variant)

    # --- rules ---------------------------------------------------------------
    @rule(boundary=st.sampled_from(AIMABLE), which=WHICH_STEP)
    def crash_at(self, boundary: str, which: int | None) -> None:
        """A worker takes the run and dies at a named boundary. If the lease has not lapsed the
        acquire refuses and the rule is a no-op — which is the fence doing its job, not a skip."""
        self.sim.work(boundary=boundary, fault="crash", step=self._step(which))

    @rule(boundary=st.sampled_from(AIMABLE), which=WHICH_STEP)
    def journal_fault_at(self, boundary: str, which: int | None) -> None:
        """The store stops answering. Not a crash: the worker is alive and must decline to write a
        verdict it cannot durably record, which is the `Abandon` path phase 6 found the hard way."""
        self.sim.work(boundary=boundary, fault="journal_error", step=self._step(which))

    def _step(self, which: int | None) -> int | None:
        pending = self.sim.pending_steps()
        return None if which is None or not pending else pending[which % len(pending)]

    @rule()
    def restart_worker(self) -> None:
        """A successor, with no handoff: it finds its work in the journal or it finds none."""
        self.sim.work()

    @rule(seconds=st.floats(min_value=0.1, max_value=5.0))
    def tick(self, seconds: float) -> None:
        self.sim.tick(seconds)

    @rule()
    def lease_expiry(self) -> None:
        """Time enough for the lease to lapse, then the reaper predicate over the real rows."""
        self.sim.tick(TTL + 1)
        self.sim.reap()

    @precondition(lambda self: self.sim is not None and self.sim.phase() != "COMPLETED")
    @rule(ms=st.sampled_from((1200.0, 2000.0)))
    def hold_the_effect(self, ms: float) -> None:
        """A receiver that takes longer than the tool timeout. The effect still lands — the World
        fsyncs the receipt before it computes the response — so this is the ambiguity window
        reached without a crash at all."""
        self.sim.hold(ms)

    # --- invariants ----------------------------------------------------------
    @invariant()
    def the_verifier_agrees(self) -> None:
        if self.sim is None:
            return
        verdicts = verifier.verify(self.sim.facts())
        failed = [n for n in JUDGED if verdicts.as_dict().get(n) == "FAIL"]
        assert not failed, {n: verdicts.findings[n].detail for n in failed}

    @invariant()
    def the_world_only_ever_grows(self) -> None:
        """A rule may add to the World and may not take away. An applied count that fell would
        mean the sim, not the runtime, was rewriting the evidence."""
        if self.sim is None:
            return
        applied = self.sim.world.applied_counts().get(self.sim.identity, 0)
        assert applied >= self.applied_high_water
        self.applied_high_water = applied

    @invariant()
    def a_terminal_run_stays_terminal(self) -> None:
        """The check a single trial cannot make. A run that completes, does more work, and settles
        again passes every end-state assertion ever written."""
        if self.sim is None:
            return
        phase = self.sim.phase()
        if self.was_terminal:
            assert phase == "COMPLETED", f"a COMPLETED run moved to {phase}"
        self.was_terminal = self.was_terminal or phase == "COMPLETED"

    def teardown(self) -> None:
        if self.sim is not None:
            self.sim.close()


def test_the_sim_can_actually_lose_and_recover_a_run() -> None:
    """The machine's own smoke test, and the reason it is worth writing down.

    Every rule in `KeelMachine` is allowed to be a no-op — a worker cannot take a lease another
    worker still holds, and that refusal is the fence working rather than a skip. The failure mode
    is a machine where *every* rule is a no-op: it would explore thousands of sequences of nothing
    and report a clean green suite. This pins one sequence that must do real work, so a change that
    silently stops the sim from crashing anything fails here rather than passing quietly there.
    """
    sim = Sim("EXTERNAL")
    try:
        assert sim.work(boundary="after:effect_exec", fault="crash", step=3)
        assert sim.crashes == 1, "the fault fired"
        assert sim.phase() == "RUNNING", "the run is neither finished nor failed; it is abandoned"
        assert sim.world.applied_counts()[sim.identity] == 1, "the World has the effect"
        assert sim.state().steps[3].state == "RUNNING", "and the journal does not know"

        sim.tick(TTL + 1)
        assert sim.reap() == [sim.run_id], "the reaper predicate, over the real rows"
        assert sim.work(), "a successor finds its work in the journal, with no handoff"

        assert sim.phase() == "COMPLETED"
        assert sim.state().steps[3].state == "RESOLVED_COMPLETED", "probed, not re-fired"
        assert sim.world.applied_counts()[sim.identity] == 1, "and never applied twice"
    finally:
        sim.close()


KeelMachine.TestCase.settings = settings(
    max_examples=25,
    stateful_step_count=8,
    deadline=None,
    # Each example builds a World on an ephemeral port and runs a program end to end, so the
    # per-example cost is milliseconds of real work rather than the microseconds Hypothesis's
    # default timing expects.
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
TestKeelMachine = KeelMachine.TestCase
