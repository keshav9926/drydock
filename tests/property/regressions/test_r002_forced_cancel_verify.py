"""r002 — VERIFY failed a force-cancelled child whose program raises past its last step (§12.8).

Shrunk from `KeelMachine` (the hand copy below drops the rules that only moved the clock):

    state.start(tools=[t0 PURE], script=[delegate n=1 child=[] fail=True], retry='none', model_retry='none')
    state.restart_worker(slot='W0')                          # the parent spawns, parks
    state.deliver_signal(run=root, kind='cancel')
    state.restart_worker(slot='W0')                          # acknowledged; the child is told
    state.deliver_signal(run=root, kind='custom')            # the parent is claimable before the child
    state.tick(seconds=31.0); state.tick(seconds=31.0)       # past cancel_grace
    state.restart_worker(slot='W1')                          # takeover: the child, never claimed, is CANCELLED
    # C1: "RuntimeError: the child's own failure" — VERIFY of the child

The takeover acknowledges at `next_step_index` (§7.6.2). The child's program, replayed, issues every
journaled step (none) and raises before reaching that index — which is exactly what the original
would have done, had the cancel not won. A program that *returned* there already passed; one that
raised was reported as a replay failure. Fixed in `keel/replay/verify.py`.

No fault spec: the sequence needs a `cancel`, which no Crashproof mode can send.
"""

from __future__ import annotations

import pytest

from keel.state.fold import fold
from tests.property.sim import GRACE, Inexpressible, Sim, ToolDecl, to_fault_spec


def test_r002_a_forced_cancel_past_the_programs_end_verifies() -> None:
    sim = Sim([ToolDecl("t0")], [{"op": "delegate", "n": 1, "child": [], "on_failure": "escalate",
                                  "violate": False, "fail": True}])
    try:
        sim.restart_worker("W0")
        sim.deliver(sim.root, "cancel")
        sim.restart_worker("W0")
        sim.deliver(sim.root, "custom")
        sim.tick(GRACE + 1)
        sim.restart_worker("W1")
        [child] = [r for r in sim.run_ids() if r != sim.root]
        state = fold(sim.events(child))
        assert state.phase == "CANCELLED" and state.forced_by is not None, state.phase
        sim.check()  # C1 on every run that became terminal
        # No spec: a cancel is not a fault type in any mode (§14.3), so §12.8's second artefact cannot
        # be written for this one, and saying so is the artefact.
        with pytest.raises(Inexpressible, match="cancel"):
            to_fault_spec(sim.example("r002"), out_dir=None)
        sim.quiesce()
        sim.check_teardown()
    finally:
        sim.close()
