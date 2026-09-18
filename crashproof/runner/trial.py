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
from crashproof.faults.injectors.proxy import ProxyInjector
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import Schedule, expand
from crashproof.faults.spec import FaultSpec
from crashproof.faults.supervisor import Supervisor
from crashproof.proxy import Proxy
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
) -> TrialRow:
    # The code that ran is the code at the start of *this* trial. Read once per bench, a commit made
    # mid-run stamped rows it never ran; read without `--dirty`, rows from an edited tree named a
    # commit that did not contain what ran.
    keel_commit = current_commit()
    trial_id = f"t-{seed}"
    trial = TrialDir(out_dir / trial_id, fresh=True)
    schedule = expand(spec, seed, workload)
    schedule.write(trial.schedule_path)
    _write_spec(trial.path / "spec.yaml", spec)

    # 1. the witness, first and per trial: fresh state, its own receipt log
    world = world_from_endpoints(workload.endpoint_decls(), log_path=trial.receipts_path)
    server = WorldServer(world, port=0)
    await server.start()
    # In `proxy` mode the SUT is pointed at the proxy, which is pointed at the World. The proxy is
    # the firing site; the SUT's shim rides along observe-only, so model calls are still counted
    # at the wire (§11.2).
    proxy = None
    world_url = server.base_url
    if spec.mode == "proxy":
        proxy = Proxy(
            server.base_url,
            ProxyInjector(trial, schedule, trial_id=trial_id),
            tool_names={t.endpoint: t.name for t in workload.tools_for(variant)},
        )
        await proxy.start()
        world_url = proxy.base_url

    handle = SutHandle(trial_dir=trial.path, dependency=None, world_url=world_url)  # type: ignore[arg-type]
    started = time.time()
    try:
        # 2. the SUT's own store, owned by the adapter that knows what belongs in it
        handle.dependency = await adapter.start_dependency(handle)
        worker_count = adapter.worker_count(spec)
        pin = adapter.config_pin(worker_count=worker_count)

        supervisor = Supervisor(
            trial,
            schedule,
            trial_id=trial_id,
            argv=adapter.worker_argv(handle),
            # The mode travels with the env so the SUT's shim knows whether it may fire: in
            # `proxy` mode it observes only, and the proxy is the one firing site (§11.2).
            env={**adapter.worker_env(handle), "CRASHPROOF_MODE": spec.mode},
            is_terminal=lambda: _terminal(adapter, handle, workload),
            worker_count=worker_count,
            secondary_env={"CRASHPROOF_KEEL_ROLE": "successor"},
            # W5: the harness is the human. An adapter without `approve` cannot run a gated
            # workload, and the trial then times out with WAITING in the row rather than
            # pretending — `on_waiting` is None and the supervisor never grants.
            status=lambda: adapter.status(handle),
            on_waiting=(lambda: adapter.approve(handle)) if hasattr(adapter, "approve") else None,
            pinned_pause_ms=pin.pause_ms,
            detection_timeout_s=pin.detection_timeout_s,
        )
        sup = await supervisor.run(lambda: adapter.submit(handle))

        # 3. collection: canonical result, the SUT's export, the World's word, the fault log
        result = await adapter.collect(handle)
        # C1 runs here, not in the verifier: the verifier is a pure function from facts to
        # verdicts, and replaying a journal is I/O. An adapter with no replay mode returns None,
        # which the verifier reads as N/A — never as a pass for having nothing to check.
        replay = None
        if hasattr(adapter, "replay_check"):
            try:
                replay = await adapter.replay_check(handle, result)
            except Exception as exc:  # noqa: BLE001 - a harness failure, not the runtime's
                replay = {"ok": False, "error": f"replay_check: {type(exc).__name__}: {exc}"}
        executed = supervisor.executed_flags()
        # A freeze prints the pause it actually applied: §13.4's draw, once per trial.
        paused = {t["fault_id"]: t["pause_ms"] for t in supervisor.result.thawed}
        fault_rows = [
            {
                **row.model_dump(),
                "executed": executed.get(row.fault_id, True),
                **({"pause_ms": paused[row.fault_id]} if row.fault_id in paused else {}),
            }
            for row in trial.faults()
        ]
        # A trial is scored only if it tested what it claimed to. Two ways it might not have: a
        # fault row recorded for a fault that did not happen, or a schedule that never fired at
        # all — which would otherwise read as a clean recovery from a crash that never occurred.
        valid = all(row["executed"] for row in fault_rows) and bool(fault_rows or spec.is_baseline)
        # A third way: the store's clock moved against the host's during the trial, so every
        # journal-vs-receipt comparison is on a clock that was not one clock. Void, and re-taken.
        valid = valid and store_clock_steady(_export(result.export, "store_clock"))

        facts = invariants.TrialFacts(
            world_receipts=[_receipt(r) for r in world.receipts],
            world_applied=world.applied_counts(),
            sut_committed=result.committed_effects,
            journal=_journal(result.export),
            status=result.status,
            expected_status=workload.expected.status,
            # The spec may say what "correct" looks like under *this* fault (`approval_expiry`:
            # nothing deployed); otherwise the workload's variant does.
            required_effects=(
                tuple(spec.expected_effects)
                if spec.expected_effects is not None
                else workload.variant(variant).required_effects
            ),
            claims=adapter.claims,
            effect_class=_class_under_test(workload, variant),
            faults=fault_rows,
            restarts=sup.restarts,
            max_recoveries=spec.max_recoveries,
            timed_out=sup.timed_out,
            reached_terminal=sup.terminal,
            replay=replay,
            sut_effects=_effects(result.export),
            gated_tools=_gated(workload, variant),
            sut_checkpoints=_export(result.export, "checkpoints"),
            sut_commits=_commits(result.export),
        )
        verdicts = invariants.verify(facts)
        # The verifier's inputs, in the trial directory, before the verdict computed from them.
        # `crashproof verify <trial_dir>` is only possible if the directory holds the facts and not
        # the live objects they were read from, and `--recheck` is only meaningful if a second run
        # reads exactly what the first one did.
        (trial.path / "facts.json").write_text(_dumps(invariants.dump(facts)), encoding="utf8")
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
            expected_world_state=(
                dict(spec.expected_world_state)
                if spec.expected_world_state is not None
                else workload.variant(variant).world_state
            ),
            faults=fault_rows,
            t_restarts=sup.t_restarts,
            wall_ms=sup.wall_ms,
            model_calls=model_calls,
            tokens=billed,
            storage_bytes=result.storage_bytes,
            detect_ms=result.detect_ms,
            verdicts=verdicts.as_dict(),
            world_probes=list(world.probes),
            applied_identities=world.applied_identities(),
            valid=valid,
            baseline=baseline,
            journal=facts.journal,
            approval_binding_violations=invariants.approval_binding_violations(facts),
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
            key_source=key_source_in_effect(adapter, workload.variant(variant).key_source),
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
        if proxy is not None:
            await proxy.stop()
        await server.stop()


def current_commit() -> str:
    """`git describe --always --dirty --abbrev=7` of the repository this harness runs from — a short
    sha, `-dirty` when tracked files differ from it. Tags are excluded so the form never varies."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7", "--exclude=*"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, check=False,
        )
    except OSError:  # pragma: no cover - no git on the machine
        return ""
    return out.stdout.strip()


def key_source_in_effect(adapter: Any, declared: str) -> str:
    """The key the arm actually presents, not the one the variant asks for. A variant says
    `framework`; an adapter whose framework has no key to give sends none, and a row that said
    otherwise would put a natural-idempotency result under F1 (§13.6, §14.2)."""
    return declared if declared in adapter.key_sources else "none"


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


def _gated(workload: Workload, variant: str) -> dict[str, str]:
    endpoints = {t.name: t.endpoint for t in workload.tools_for(variant)}
    return {name: endpoints[name] for name in workload.gated_tools()}


def _receipt(r: Any) -> dict[str, Any]:
    return {
        "endpoint": r.endpoint,
        "effect_key": r.effect_key,
        "logical_identity": r.logical_identity,
        "ts": r.ts,
    }


#: How far the store's clock may move against the host's within one trial. A healthy Docker VM
#: stays within a few ms over a minute; WSL's time sync fighting systemd-timesyncd moved it by
#: 100 ms a second, with 0.8 s steps.
STORE_CLOCK_TOLERANCE_S = 0.05


def store_clock_steady(clock: dict[str, Any] | None) -> bool:
    if not clock or not clock.get("start") or not clock.get("end"):
        return True  # a runtime with no store clock, or rows from before it was measured
    return abs(clock["end"]["offset_s"] - clock["start"]["offset_s"]) <= STORE_CLOCK_TOLERANCE_S


def _journal(export: Path | None) -> list[dict[str, Any]] | None:
    """The runtime's journal on the host's clock. An export that measured its store's offset
    (`store_clock.offset_s`) has every event `ts` shifted by it here, once, so S4, the placement
    views and `cancel_latency` compare a journal event with a World receipt on one clock."""
    events = _export(export, "events")
    offset = (_export(export, "store_clock") or {}).get("offset_s")
    if not events or not offset:
        return events
    from datetime import UTC, datetime

    from crashproof.verifier.invariants import iso

    return [{**e, "ts": datetime.fromtimestamp(iso(e["ts"]) - offset, UTC).isoformat()} for e in events]


def _effects(export: Path | None) -> list[dict[str, Any]] | None:
    """The runtime's own effect ledger, where it keeps one. A runtime with no such table has none
    to export, and §19.5's journal columns print empty for it rather than being invented."""
    return _export(export, "effects")


def _commits(export: Path | None) -> list[dict[str, Any]] | None:
    """An engine's commit records (DBOS steps, Temporal activity outcomes, Restate run completions)
    in the facts, so K3 and `ambiguity_window_width` read them from `facts.json` rather than from an
    export a copied trial directory may not carry. `None` for Keel and LangGraph, whose committed
    records are the journal and the checkpoints."""
    if export is None or not export.exists():
        return None
    import json

    from crashproof.verifier.views import commits_from_export

    return commits_from_export(json.loads(export.read_text(encoding="utf8")))


def _export(export: Path | None, key: str) -> list[dict[str, Any]] | None:
    """One section of the adapter's export — journal events, effect rows, checkpoints — or `None`
    where this runtime keeps no such thing."""
    if export is None or not export.exists():
        return None
    import json

    return json.loads(export.read_text(encoding="utf8")).get(key)


def _write_spec(path: Path, spec: FaultSpec) -> None:
    """The spec as submitted, in the form it was written in — a trial directory a human can read
    is a trial directory a human will check."""
    import yaml

    path.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False), encoding="utf8")


def _dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, default=str)
