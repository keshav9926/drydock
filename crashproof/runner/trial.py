"""One trial, end to end (§4.13, §11.9).

    expand → World up → dependency up → cursor 0 → spawn → submit
           → restart loop → collect → verify → one JSONL row

The order is the specification's, and two details in it are load-bearing. The World starts before
the SUT, because it is the witness and a witness that arrives late has nothing to say. And the
worker is spawned *before* the run is submitted, because that is the only order in which the
supervisor never has to tell a restarted worker what to resume.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from crashproof.adapters.base import SutHandle
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import Schedule, expand
from crashproof.faults.spec import FaultSpec
from crashproof.faults.supervisor import Supervisor
from crashproof.verifier import invariants, metrics
from crashproof.workloads.spec import Workload
from crashproof.world import oracle
from crashproof.world.server import WorldServer
from crashproof.world.services import world_from_endpoints


@dataclass(slots=True)
class TrialRow:
    """The published unit. Every column that could change a number travels with it, so a reader
    can tell a stale row from a current one without trusting the report's own footer."""

    trial_id: str
    cell_id: str
    adapter: str
    workload: str
    workload_variant: str
    mode: str
    spec_hash: str
    schedule_hash: str
    seed: int
    key_source: str
    recovery_mechanism: str
    claims: dict[str, str]
    config_pin: dict[str, Any]
    started_at: float
    ended_at: float
    wall_ms: float
    status: str
    result: Any
    verdicts: dict[str, str]
    counterexamples: list[dict[str, Any]]
    metrics: dict[str, Any]
    faults: list[dict[str, Any]] = field(default_factory=list)
    recoveries: list[dict[str, Any]] = field(default_factory=list)
    restarts: int = 0
    valid: bool = True
    stale: bool = False
    keel_commit: str = ""

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import fields

        return {f.name: getattr(self, f.name) for f in fields(self)}


async def run_trial(
    *,
    adapter: Any,
    workload: Workload,
    variant: str,
    spec: FaultSpec,
    seed: int,
    out_dir: Path,
    cell_id: str = "",
    baseline: metrics.Metrics | None = None,
    keel_commit: str = "",
) -> TrialRow:
    trial_id = f"t-{seed}"
    trial = TrialDir(out_dir / trial_id, fresh=True)
    schedule = expand(spec, seed, workload)
    schedule.write(trial.schedule_path)
    _write_spec(trial.path / "spec.yaml", spec)

    # 1. the witness, first and per trial: fresh state, its own receipt log
    world = world_from_endpoints(workload.endpoint_decls(), log_path=trial.receipts_path)
    server = WorldServer(world, port=0)
    await server.start()

    handle = SutHandle(trial_dir=trial.path, dependency=None, world_url=server.base_url)  # type: ignore[arg-type]
    started = time.time()
    try:
        # 2. the SUT's own store, owned by the adapter that knows what belongs in it
        handle.dependency = await adapter.start_dependency(handle)
        worker_count = adapter.worker_count(spec)

        supervisor = Supervisor(
            trial,
            schedule,
            trial_id=trial_id,
            argv=adapter.worker_argv(handle),
            env=adapter.worker_env(handle),
            is_terminal=lambda: _terminal(adapter, handle, workload),
            worker_count=worker_count,
            secondary_env={"CRASHPROOF_KEEL_ROLE": "successor"},
        )
        sup = await supervisor.run(lambda: adapter.submit(handle))

        # 3. collection: canonical result, the SUT's export, the World's word, the fault log
        result = await adapter.collect(handle)
        executed = supervisor.executed_flags()
        fault_rows = [
            {**row.model_dump(), "executed": executed.get(row.fault_id, True)}
            for row in trial.faults()
        ]
        # A trial is scored only if it tested what it claimed to. Two ways it might not have: a
        # fault row recorded for a fault that did not happen, or a schedule that never fired at
        # all — which would otherwise read as a clean recovery from a crash that never occurred.
        valid = all(row["executed"] for row in fault_rows) and bool(fault_rows or spec.is_baseline)

        facts = invariants.TrialFacts(
            world_receipts=[_receipt(r) for r in world.receipts],
            world_applied=world.applied_counts(),
            sut_committed=result.committed_effects,
            journal=_journal(result.export),
            status=result.status,
            expected_status=workload.expected.status,
            required_effects=workload.variant(variant).required_effects,
            claims=adapter.claims,
            effect_class=_class_under_test(workload, variant),
            faults=fault_rows,
            restarts=sup.restarts,
            max_recoveries=spec.max_recoveries,
            timed_out=sup.timed_out,
            reached_terminal=sup.terminal,
        )
        verdicts = invariants.verify(facts)
        # Model calls are counted at the wire, from the shim's own observation log, not from each
        # adapter's self-report. Measuring one runtime from inside its process and another from
        # outside it is how an economy metric becomes a statement about instrumentation (§14.3);
        # counting `before:model_call` is the same act in every arm, and it is the only way the
        # column exists at all for a runtime that keeps no model-call tally of its own.
        observed = [o for o in trial.observations() if o.boundary == "before:model_call"]
        model_calls = len(observed)
        # Charged at the send, not at the return: an attempt that never came back was still billed
        # (§16.4), and counting at the return would make every crashed attempt free — which is the
        # accounting error the column exists to expose.
        billed = sum(o.tokens or 0 for o in observed) or None
        m = metrics.compute(
            world_applied=facts.world_applied,
            world_receipts=facts.world_receipts,
            sut_committed=facts.sut_committed,
            required_effects=facts.required_effects,
            status=result.status,
            expected_status=workload.expected.status,
            expected_world_state=workload.variant(variant).world_state,
            faults=fault_rows,
            t_restarts=sup.t_restarts,
            wall_ms=sup.wall_ms,
            model_calls=model_calls,
            tokens=billed,
            storage_bytes=result.storage_bytes,
            detect_ms=result.detect_ms,
            verdicts=verdicts.as_dict(),
            world_probes=list(world.probes),
            valid=valid,
            baseline=baseline,
        )

        row = TrialRow(
            trial_id=trial_id,
            cell_id=cell_id or f"{adapter.name}.default.{variant}.{spec.name}",
            adapter=adapter.name,
            workload=workload.workload,
            workload_variant=variant,
            mode=spec.mode,
            spec_hash=spec.spec_hash,
            schedule_hash=schedule.hash(),
            seed=seed,
            key_source=workload.variant(variant).key_source,
            recovery_mechanism=adapter.recovery_mechanism,
            claims=dict(adapter.claims),
            config_pin=adapter.config_pin(worker_count=worker_count).as_dict(),
            started_at=started,
            ended_at=time.time(),
            wall_ms=sup.wall_ms,
            status=result.status,
            result=result.result,
            verdicts=verdicts.as_dict(),
            counterexamples=verdicts.counterexamples(),
            metrics=m.as_dict(),
            faults=fault_rows,
            recoveries=result.recoveries,
            restarts=sup.restarts,
            valid=valid,
            keel_commit=keel_commit,
        )
        (trial.path / "result.json").write_text(_dumps(row.as_dict()), encoding="utf8")
        return row
    finally:
        await adapter.stop_dependency(handle)
        await server.stop()


async def _terminal(adapter: Any, handle: SutHandle, workload: Workload) -> bool:
    """A trial ends when the run reaches a terminal state — or a waiting state the workload calls
    legitimate. SUSPENDED after an ambiguity was surfaced is a *recovered* run, not a stuck one."""
    status = await adapter.status(handle)
    return status in ("COMPLETED", "FAILED", "CANCELLED", "SUSPENDED")


def _class_under_test(workload: Workload, variant: str) -> str:
    for decl in workload.tools_for(variant):
        if decl.effect_class != "PURE":
            return decl.effect_class
    return "PURE"


def _receipt(r: Any) -> dict[str, Any]:
    return {
        "endpoint": r.endpoint,
        "effect_key": r.effect_key,
        "logical_identity": r.logical_identity,
        "ts": r.ts,
    }


def _journal(export: Path | None) -> list[dict[str, Any]] | None:
    if export is None or not export.exists():
        return None
    import json

    return json.loads(export.read_text(encoding="utf8")).get("events")


def _write_spec(path: Path, spec: FaultSpec) -> None:
    """The spec as submitted, in the form it was written in — a trial directory a human can read
    is a trial directory a human will check."""
    import yaml

    path.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False), encoding="utf8")


def _dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, default=str)
