"""r004 — VERIFY failed a run paused between a decided failure and its RUN_FAILED (§12.8).

Found by `KeelMachine` on CI's first run of the deep rule set (hypothesis 6.168.0, the `ci` profile,
seed 0 on Linux); the hand copy below keeps the rules that matter:

    state.start(script=[delegate n=2 child=[] on_failure=fail_parent fail=True])
    state.restart_worker(slot='W0')     # the parent spawns both, parks on children
    state.restart_worker(slot='W0')     # child 1 runs its program, which raises
    state.restart_worker(slot='W0')     # child 2 likewise
    state.deliver_signal(run=root, kind='pause')
    state.restart_worker(slot='W0')     # one drain: CHILD_FAILED x2 -> STEP_FAILED (fail_parent) -> RUN_PAUSED
    # teardown C1 on the PAUSED root: "StepFailed: step 0: ChildFailed: ..."

The drain that fails the DELEGATE step consumes the pause in the same pass, so the run is PAUSED with
its step FAILED for good and no RUN_FAILED yet. Replayed, the program re-raises that failure, which is
exactly what the original does on resume. VERIFY scored the raise as a failed pass because the run was
not FAILED. Fixed in `keel/replay/verify.py`: a `StepFailed` for a step the journal records as FAILED
with no retry pending, raised after every journaled step was issued, is the run reproduced.

No fault spec: a pause is a signal, which no Crashproof mode can send.
"""

from __future__ import annotations

from keel.state.fold import fold
from tests.property.sim import Sim, ToolDecl


def test_r004_a_run_paused_after_its_step_failed_for_good_verifies() -> None:
    sim = Sim([ToolDecl("t0")], [{"op": "delegate", "n": 2, "child": [], "on_failure": "fail_parent",
                                  "violate": False, "fail": True}])
    try:
        for _ in range(3):
            sim.restart_worker("W0")
        sim.deliver(sim.root, "pause")
        sim.restart_worker("W0")
        state = fold(sim.events(sim.root))
        assert state.phase == "PAUSED" and state.steps[0].state == "FAILED", state.phase
        sim.check()
        sim.quiesce()
        sim.check_teardown()  # C1 on the non-terminal root
    finally:
        sim.close()
