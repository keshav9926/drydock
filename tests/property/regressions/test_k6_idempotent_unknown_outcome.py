"""k6-idempotent — an IDEMPOTENT effect whose outcome was never known hid behind a clean FAILED.

Found by `KeelMachine` at teardown (C3: `applied_not_committed`), minimal form:

    state.start(tools=[t0 IDEMPOTENT dedup:true], script=[tool t0], retry='none', model_retry='none')
    state.restart_worker(slot='W0')                          # attempt 1 is in flight
    state.complete_effect(held=0, outcome='error')           # the receiver applied it, then answered 5xx
    # was: C3 — t0.call#1 applied in the World; the effects row said ABSENT; the run was FAILED

A decision in the document, not a coding slip, so K6's shape (§30): §7.4 made an IDEMPOTENT timeout or
5xx `STEP_FAILED{retryable}` with the row ABSENT, right while a retry under the same key is coming and
wrong when none is — `NO_RETRY`, attempts spent on more 5xx, a cancel during the backoff. §9.1 already
refused "a clean failure that would hide an applied one" for the crash case (KeyWindowExpired); the
amendment extends it to the live case. With no attempt left the step goes AMBIGUOUS then
RESOLVED_UNKNOWN{method=key_window_expired} and the run SUSPENDED for a human — EXTERNAL's `escalate`
path, so replay, VERIFY and C3 need nothing new. While a retry is pending the row reads AMBIGUOUS.
"""

from __future__ import annotations

import pytest

from keel.state.fold import fold
from tests.property.sim import Sim, ToolDecl


@pytest.mark.parametrize("retry", ["none", "retry"])
@pytest.mark.parametrize("outcome", ["error", "dropped"])
def test_k6_an_applied_idempotent_effect_with_an_unknown_outcome_is_journaled(outcome: str, retry: str) -> None:
    sim = Sim([ToolDecl("t0", cls="IDEMPOTENT", dedup=True)], [{"op": "tool", "tool": "t0", "gated": False}],
              retry=retry)
    try:
        sim.restart_worker("W0")
        [held] = sim.completable()
        sim.complete(held, outcome)
        if outcome == "dropped":
            sim.timeout(held)
        for _ in range(6):  # every retry the policy allows answers 5xx too, in-process or after a park
            if sim.completable():
                sim.complete(sim.completable()[0], "error")
            sim.tick(5.0)
            sim.restart_worker("W0")
        state = fold(sim.events(sim.root))
        assert state.phase == "SUSPENDED", state.phase
        assert state.steps[0].state == "RESOLVED_UNKNOWN" and state.steps[0].method == "key_window_expired"
        [row] = [e for e in sim.run(sim.journal.effects(sim.root)) if e.step_index == 0]
        assert row.status == "RESOLVED_UNKNOWN"
        assert sim.world.applied_counts() == {"t0.call#1": 1}
        sim._c3()
        sim.check()
    finally:
        sim.close()
