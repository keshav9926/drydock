"""r005 — a forced cut still pending when the program returned `Continue` wrote a stale boundary (§12.8).

Found by `KeelMachine` (the `ci` profile, `--hypothesis-seed=0`, on the run that added streaming to
the generator — the new op moved the search, not the bug; nothing here streams):

    state.start(tools=[t PURE], script=[tool, tool, tool, tool, continue, model], segment_steps=2)
    state.restart_worker(slot='W0')     # four reads; a forced boundary before the third
    state.advance(n=1)                  # the model answers; the run completes
    # was: C1 — "VERIFY did not reproduce the journal" (NondeterminismDetected at step 4)

With N = 2 the safe point before the `continue` op asked for a forced cut (state i=4), and then the
program returned `Continue(state i=5)`, which cut boundary 2 at step 4. The forced request was never
dropped, so the next step's `_run` cut boundary 3 — also at step 4, from the older state i=4. Re-execution
from boundary 3 runs the `continue` op again and returns a `Continue` over the journaled model step:
nondeterminism in a run that had none. A coding slip, not a design question: a returned `Continue` *is*
the boundary the forced cut was waiting for, so `Ctx._continue` now drops the pending request.

No fault spec: the sequence has no fault in it — `to_fault_spec` would write a baseline.
"""

from __future__ import annotations

from keel.state.fold import fold
from tests.property.sim import Sim, ToolDecl


def test_r005_a_returned_continue_supersedes_a_pending_forced_cut() -> None:
    read = {"op": "tool", "tool": "t0", "gated": False}
    sim = Sim([ToolDecl("t0")], [read, read, read, read, {"op": "continue"}, {"op": "model"}], segment_steps=2)
    try:
        assert sim.restart_worker("W0")
        sim.advance(1)
        events = sim.events(sim.root)
        assert fold(events).phase == "COMPLETED"
        segs = [(e.body.segment_no, e.body.first_step_index, e.body.state_blob["i"])
                for e in events if e.type == "SEGMENT_STARTED"]
        assert segs == [(1, 2, 2), (2, 4, 5)], "one boundary per cut; none from a superseded request"
        sim.check()  # C1 on the terminal run
        sim.quiesce()
        sim.check_teardown()
    finally:
        sim.close()
