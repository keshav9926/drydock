"""k6-idempotent — C3 fails by design for an IDEMPOTENT effect whose outcome was never known.

Found by `KeelMachine` at teardown (C3: `applied_not_committed`), minimal form:

    state.start(tools=[t0 IDEMPOTENT dedup:true], script=[tool t0], retry='none', model_retry='none')
    state.restart_worker(slot='W0')                          # attempt 1 is in flight
    state.complete_effect(held=0, outcome='error')           # the receiver applied it, then answered 5xx
    # C3: t0.call#1 applied in the World; the effects row says ABSENT; the run is FAILED

Not a coding bug. §8.5 makes an IDEMPOTENT timeout or 5xx `STEP_FAILED{retryable}` — "re-execution is
safe by class" — and §7.4 gives that edge the row status `ABSENT`. Both are right while a retry is
coming: the same key lands once. When none lands — the default `NO_RETRY`, a policy's attempts spent on
more 5xx, a cancel drained during the backoff — the run ends FAILED with the effect applied and the
journal's committed set without it. §12.4's C3 exempts only surfaced RESOLVED_UNKNOWN effects, and
§8.7's IDEMPOTENT row names no such residual. A C3 failure whose cause is a decision in the document
is K6's shape (§30), so it is reported and not fixed here: the fix is a design choice (a status that
says "unknown, not absent"; C3's exemption list; or a class rule that an unknown IDEMPOTENT outcome is
retried until it is known) and belongs to the owner. The hook-mode conformance cells do not judge C3
at all, which is why no published cell shows it.

Strict xfail: the day the design changes so this holds, the test passes, the xfail fails, and the
sim's exemption in `Sim._c3` is deleted with it.
"""

from __future__ import annotations

import pytest

from keel.state.fold import fold
from tests.property.sim import Sim, ToolDecl


@pytest.mark.xfail(strict=True, reason="K6 candidate: IDEMPOTENT unknown outcome is ABSENT by design (§7.4, §8.5)")
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
        assert fold(sim.events(sim.root)).phase == "FAILED"
        assert sim.world.applied_counts() == {"t0.call#1": 1}
        sim._c3(strict_c3=True)
    finally:
        sim.close()
