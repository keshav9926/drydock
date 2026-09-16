"""r001 — a store outage at `before:lease_release` escaped `Worker.execute` (§12.8 regression).

Shrunk from `KeelMachine`:

    state.start(tools=[t0 PURE], script=[model], retry='none', model_retry='none')
    state.restart_worker(slot='W0')                          # the MODEL call is in flight
    state.lease_expiry(slot='W0')                            # paused past its lease; nobody takes it
    state.journal_fault(boundary='before:lease_release', n=1)
    state.zombie_resume(slot='W0')                           # finishes the run, then cannot release
    # worker: StoreUnavailable escaped Worker.execute

The run's terminal event was durable; only the release failed. `execute` let the error out, which
ends `run_forever`'s claim loop — one store blip at the last statement of one run stopped the
process serving every other. Fixed in `Worker._release`: nothing released, the lease lapses.

Hand-written, not `@reproduce_failure`: a blob is bound to the machine's exact rule set and fails
with `DidNotReproduce` the day a rule is added, which is every week of §29.2.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from keel.state.fold import fold
from tests.property.sim import Sim, ToolDecl, to_fault_spec

#: §12.8's second artefact, emitted by `to_fault_spec(sim.example("r001"))`: a hook-mode spec, because
#: `journal_unavailable` exists only there.
SPEC = Path(__file__).resolve().parents[3] / "bench" / "specs" / "regressions" / "r001.yaml"


def test_r001_a_store_outage_at_release_does_not_end_the_worker() -> None:
    sim = Sim([ToolDecl("t0")], [{"op": "model"}])
    try:
        sim.restart_worker("W0")
        sim.lease_expiry("W0")
        sim.journal_faults["before:lease_release"] += 1
        sim.zombie_resume("W0")
        assert yaml.safe_load(SPEC.read_text(encoding="utf8")) == to_fault_spec(sim.example("r001"), out_dir=None)
        sim.check()
        assert fold(sim.events(sim.root)).phase == "COMPLETED"
        assert sim.journal._runs[sim.root].lease_expires_at is not None, "not released: it lapses"
        sim.quiesce()
        sim.check_teardown()
    finally:
        sim.close()
