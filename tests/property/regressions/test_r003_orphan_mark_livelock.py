"""r003 — a worker spun for ever on WakeRaced after the reaper marked its lapsed lease (§12.8).

Sequence (sim rules; found by aiming the sim at `_commit_park`'s callers rather than by the random
search, and confirmed by its spin limit):

    state.start(tools=[t0 PURE], script=[model], retry='none', model_retry='retry')
    state.restart_worker(slot='W0')                          # MODEL attempt 1 in flight
    state.complete_effect(held=0, outcome='error')           # 503: backoff 0.5 s, in-process
    state.lease_expiry(slot='W0')                            # paused past its lease; the reaper marks it ORPHANED
    state.zombie_resume(slot='W0')                           # nobody took it: the fence still passes, attempt 2
    state.complete_effect(held=0, outcome='error')           # 503 again: backoff 1.0 s, so it parks
    # worker: 2000 journal calls without parking

The reaper's mark sets `runnable_at` with no signal behind it. The park's release is guarded by
`runnable_at IS NULL` (§5.4 (4)) and raised WakeRaced; the caller drained again, but a drain opens its
transaction — and clears the wake — only when a signal is pending, so the next park raced the same mark,
and so on without end: a hot loop of rolled-back transactions against the store, holding the lease it
keeps extending. Reachable in production by any pause past the TTL that no other worker claims in time.
Fixed in `StepEngine`: a lost park race makes the next drain clear the wake even with an empty inbox.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from keel.state.fold import fold
from tests.property.sim import Sim, ToolDecl, to_fault_spec

SPEC = Path(__file__).resolve().parents[3] / "bench" / "specs" / "regressions" / "r003.yaml"


def test_r003_a_lapsed_lease_marked_orphaned_does_not_livelock_the_park() -> None:
    sim = Sim([ToolDecl("t0")], [{"op": "model"}], model_retry="retry")
    try:
        sim.restart_worker("W0")
        sim.complete(sim.completable()[0], "error")
        sim.lease_expiry("W0")
        assert sim.journal._runs[sim.root].runnable_reason == "ORPHANED"
        sim.zombie_resume("W0")
        sim.complete(sim.completable()[0], "error")
        assert yaml.safe_load(SPEC.read_text(encoding="utf8")) == to_fault_spec(sim.example("r003"), out_dir=None)
        sim.check()
        state = fold(sim.events(sim.root))
        assert state.phase == "SLEEPING" and state.waiting_reason == "retry_backoff", state.phase
        row = sim.journal._runs[sim.root]
        assert row.lease_expires_at is None and row.runnable_at is None, "parked at zero compute"
        sim.quiesce()
        sim.check_teardown()
        assert fold(sim.events(sim.root)).phase == "COMPLETED"
    finally:
        sim.close()
