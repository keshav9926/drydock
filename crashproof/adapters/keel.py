"""The Keel adapter, and the worker process the supervisor restarts (§13.4).

This is one of the two modules in the harness allowed to import `keel` — the other is the hook
injector — and it is where the neutral workload becomes a real program with real effect classes.

The rules it is held to are the ones every adapter is held to, and Keel gets no exemption:

- no counter, no pre-send lookup, no retry, no dedup. If the runtime re-fires, the World sees it.
- `worker_argv` is a pure function of the trial directory, restarted verbatim, carrying no run id.
  Keel is `recovery_mechanism = self`: the restarted process finds its own work through the reaper
  and the claim, and `on_worker_restart` is a no-op.
- `probe` is declared by the *workload's* tool spec, not by the adapter. It runs only after the
  runtime has itself classified an attempt as ambiguous. That no other framework in the fact sheet
  exposes an equivalent post-crash hook is the finding, not a privilege granted here.

Two `keel worker` processes run in a `pause_past_ttl` cell, and only there. A frozen process cannot
reap itself: nobody would mark the run ORPHANED, nobody would acquire, and on thaw the zombie's
heartbeat would re-extend its own unchanged epoch — the cell would exercise no fence and report a
trivial pass. The second worker is the reaper's whole point, and `worker_count` is in `config_pin`
so the matrix says which arms had one.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from crashproof.adapters.base import CanonicalResult, ConfigPin, Dependency, SutHandle
from crashproof.faults.injectors.shim import ToolShim
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import Schedule
from crashproof.workloads.spec import ToolDecl, Workload, load_named
from crashproof.world.client import WorldClient

# --- pins from §13.4, small enough that a trial's detection window is seconds ------------------
LEASE_TTL_S = 2.0
TOOL_TIMEOUT_S = 1.0
HEARTBEAT_S = LEASE_TTL_S / 3
PAUSE_MS = 3000.0  # pinned, not drawn: "past the TTL" must mean one thing in the Keel arm

ENV_WORLD = "CRASHPROOF_WORLD_URL"
ENV_DSN = "CRASHPROOF_KEEL_DSN"
ENV_WORKLOAD = "CRASHPROOF_WORKLOAD"
ENV_VARIANT = "CRASHPROOF_VARIANT"
ENV_ROLE = "CRASHPROOF_KEEL_ROLE"  # "worker" | "successor": the second observer, in pause cells only
# The successor waits before it starts claiming, so the *shimmed* worker is the one that picks up
# the run and therefore the one the fault lands in. It is a bias, not a guarantee — a trial whose
# schedule fired nothing is marked invalid rather than scored (§11.7).
SUCCESSOR_START_DELAY_S = 1.5


# =============================================================================
# The workload, expressed in Keel
# =============================================================================
def build_app(workload: Workload, variant: str, world: WorldClient, shim: ToolShim | None, dsn: str):
    """A `Keel` whose tools are the workload's tools and whose program is the reference ReAct loop.

    Imported lazily so that merely importing this module — which the supervisor does — does not
    drag Keel into the harness process.
    """
    from keel.agents.demo import tool_chain
    from keel.client import Keel
    from keel.core.protocols import EffectClass, Idempotency, ProbeResult
    from keel.effects.registry import ToolCtx, tool

    key_source = workload.variant(variant).key_source
    tools = []

    for decl in workload.tools_for(variant):
        tools.append(_build_tool(decl, key_source, world, shim, tool, ToolCtx, EffectClass, Idempotency, ProbeResult))

    return Keel(
        dsn,
        provider=WorkloadProvider(workload, shim),
        tools=tools,
        programs=[tool_chain],
    )


def _build_tool(
    decl: ToolDecl, key_source: str, world: WorldClient, shim: ToolShim | None,
    tool: Any, ToolCtx: Any, EffectClass: Any, Idempotency: Any, ProbeResult: Any,
) -> Any:
    """One workload tool. The class is the workload's, the endpoint is the workload's, and whether
    a key is presented is the *variant's* — synthesising one here would be the adapter cheating."""
    sends_key = key_source == "framework" and decl.effect_class in ("IDEMPOTENT", "TRANSACTIONAL")
    endpoint = decl.endpoint

    @tool(
        effect=EffectClass[decl.effect_class],
        resolution=decl.resolution or "escalate",
        timeout=TOOL_TIMEOUT_S,
        idempotency=Idempotency.KEY if sends_key else Idempotency.NONE,
        name=decl.name,
    )
    async def run(args: dict[str, Any], tctx: ToolCtx) -> Any:
        key = tctx.effect_key if sends_key else None
        if shim is not None:
            return await shim.tool_call(decl.name, endpoint, args, effect_key=key)
        return await world.acall(endpoint, args, effect_key=key)

    if decl.resolution == "probe":

        @run.probe_hook
        async def _probe(effect_key: str, args: dict[str, Any], tctx: Any) -> Any:
            answer = await world.aprobe(endpoint, dict(args), effect_key=effect_key)
            if answer["verdict"] == "COMMITTED":
                return ProbeResult(
                    "COMMITTED",
                    evidence=answer["evidence"],
                    result=answer["result"],
                    external_ref=answer.get("external_ref"),
                )
            return ProbeResult(answer["verdict"], evidence=answer["evidence"])

    return run


class WorkloadProvider:
    """The scripted provider, driven by the workload's decision script.

    A node is selected by the ordered `(tool, occurrence)` pairs already answered in the request —
    a pure function of request content, with no per-trial counter anywhere. If the provider counted
    calls, a restart would re-ask the same question and get a different answer, and every "the
    runtime memoized correctly" result would be an artefact of the fake model.
    """

    name = "scripted"

    def __init__(self, workload: Workload, shim: ToolShim | None = None) -> None:
        self.workload = workload
        self.shim = shim
        self.calls = 0
        self.tokens = 0

    async def complete(self, req: Any) -> Any:
        key = node_key(req)
        node = self.workload.node_for(key)
        node_id = "-".join(f"{n}{i}" for n, i in key) or "start"
        if self.shim is not None:
            return self.shim.model_call(node_id, lambda: self._respond(req, node, node_id))
        return self._respond(req, node, node_id)

    def _respond(self, req: Any, node: Any, node_id: str = "") -> Any:
        from keel.providers.protocol import Message, ModelResponse, ToolCall, Usage

        self.calls += 1
        decision = dict(node.decision) if node is not None else {"final": "(script exhausted)"}
        results = _results_by_tool(req)
        calls = [
            ToolCall(id=f"tu_{i}", name=c["name"], args=_resolve(c.get("args", {}), results))
            for i, c in enumerate(decision.get("tool_calls", []))
        ]
        text = _resolve_text(str(decision.get("final", "")), results) if not calls else str(decision.get("text", ""))
        prompt = len(json.dumps(req.model_dump(mode="json"), sort_keys=True)) // 4
        self.tokens += prompt
        return ModelResponse(
            text=text,
            tool_calls=calls,
            stop_reason="tool_use" if calls else "end_turn",
            usage=Usage(input_tokens=prompt, output_tokens=len(text) // 4),
            message=Message(role="assistant", content=text),
            provider_meta={"provider": self.name, "model": "scripted-1", "node": node_id},
        )

    async def stream(self, req: Any):  # pragma: no cover - STREAMS is week 3
        yield await self.complete(req)

    async def count_tokens(self, req: Any) -> int:
        return len(json.dumps(req.model_dump(mode="json"), sort_keys=True)) // 4


def node_key(req: Any) -> tuple[tuple[str, int], ...]:
    """The ordered (tool_name, occurrence) pairs answered in this request. Stable across a restart,
    which is the whole reason it is the key."""
    seen: dict[str, int] = {}
    key: list[tuple[str, int]] = []
    for message in req.messages:
        if message.role != "tool_result":
            continue
        name = message.content.get("tool") if isinstance(message.content, dict) else None
        if not name:
            continue
        seen[name] = seen.get(name, 0) + 1
        key.append((name, seen[name]))
    return tuple(key)


def _results_by_tool(req: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for message in req.messages:
        if message.role == "tool_result" and isinstance(message.content, dict):
            out[message.content.get("tool", "")] = message.content.get("result")
    return out


_TEMPLATE = re.compile(r"^@(\w+)\.result(?:\.(\w+))?$")
_INLINE = re.compile(r"@(\w+)\.result(?:\.(\w+))?")


def _resolve(args: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """`@search.result` in the script becomes the recorded result of that tool. Deterministic, so
    the arguments — and therefore the effect key derived from them — are stable across a restart."""
    out = {}
    for name, value in args.items():
        match = _TEMPLATE.match(value) if isinstance(value, str) else None
        if match is None:
            out[name] = value
            continue
        result = results.get(match.group(1))
        out[name] = json.dumps(result, sort_keys=True) if match.group(2) is None else str(
            (result or {}).get(match.group(2), "")
        )
    return out


def _resolve_text(text: str, results: dict[str, Any]) -> str:
    """The same substitution inside a sentence, so the canonical result names the object that was
    actually created rather than the placeholder that asked for it."""

    def swap(m: re.Match[str]) -> str:
        result = results.get(m.group(1)) or {}
        return str(result.get(m.group(2), "")) if m.group(2) else json.dumps(result, sort_keys=True)

    return _INLINE.sub(swap, text)


# =============================================================================
# The adapter
# =============================================================================
class KeelAdapter:
    _template_ready = False

    name = "keel"
    recovery_mechanism = "self"
    key_sources = frozenset({"none", "framework"})
    workloads = frozenset({"tool_chain_1_effect"})
    workload_evidence = {"tool_chain_1_effect": "keel/agents/demo.py: ctx.model -> ctx.tool -> ctx.model"}
    claims: dict[str, str] = {
        # A fence protects the journal; it cannot reach a third party. So the only classes that can
        # claim more than at-least-once are the ones where the *receiver* is doing the work.
        "PURE": "effectively_once",
        "IDEMPOTENT": "effectively_once",
        "EXTERNAL": "at_least_once",
    }

    def __init__(self, workload: Workload, variant: str, *, template_db: str = "keel_template") -> None:
        self.workload = workload
        self.variant = variant
        self.template_db = template_db
        self._admin_dsn: str | None = None
        self._db_name: str | None = None
        self._app: Any = None  # one connection pool per trial, shared by submit/status/collect

    # --- declarations --------------------------------------------------------
    def config_pin(self, *, worker_count: int = 1, **extra: Any) -> ConfigPin:
        import keel

        return ConfigPin(
            framework_versions={"keel": getattr(keel, "__version__", "0.1.0"), "python": sys.version.split()[0]},
            backend="postgres",
            durability="journal",
            lease_ttl_s=LEASE_TTL_S,
            tool_timeout_s=TOOL_TIMEOUT_S,
            heartbeat_s=HEARTBEAT_S,
            successor_start_delay_s=SUCCESSOR_START_DELAY_S if worker_count > 1 else None,
            retry="max_attempts=1",
            worker_count=worker_count,
            pause_ms=PAUSE_MS,
            extra=extra,
        )

    def worker_count(self, spec: Any) -> int:
        """Two only where a successor is part of the design (§11.2)."""
        return 2 if any(f.type == "pause_past_ttl" for f in getattr(spec, "faults", ())) else 1

    # --- dependency ----------------------------------------------------------
    async def start_dependency(self, handle: SutHandle) -> Dependency:
        from crashproof.runner import database
        from keel.journal.postgres import PostgresJournal

        self._admin_dsn = os.environ.get("KEEL_DSN", "postgresql://keel:keel@localhost:5432/keel")
        await self._ensure_template(self._admin_dsn)
        self._db_name = _db_name_for(handle.trial_dir.name)
        dsn = await database.create_from_template(self._admin_dsn, self._db_name, template=self.template_db)

        journal = PostgresJournal(dsn)
        try:
            await journal.migrate()
        finally:
            await journal.close()
        return Dependency(name="postgres", dsn=dsn, env={ENV_DSN: dsn})

    def _client(self, handle: SutHandle) -> Any:
        from keel.client import Keel
        from keel.journal.postgres import PostgresJournal

        if self._app is None:
            self._app = Keel(journal=PostgresJournal(handle.dependency.dsn or ""))
        return self._app

    async def _ensure_template(self, admin_dsn: str) -> None:
        """Migrate the template once per process, then let go of it: `CREATE DATABASE ... TEMPLATE`
        refuses while anything is connected to the source."""
        if KeelAdapter._template_ready:
            return
        from crashproof.runner import database
        from keel.journal.postgres import PostgresJournal

        template_dsn = await database.ensure_template(admin_dsn, self.template_db)
        journal = PostgresJournal(template_dsn)
        try:
            await journal.migrate()
        finally:
            await journal.close()
        KeelAdapter._template_ready = True

    async def stop_dependency(self, handle: SutHandle) -> None:
        from crashproof.runner import database

        if self._app is not None:
            await self._app.close()
            self._app = None
        if self._admin_dsn and self._db_name:
            await database.drop(self._admin_dsn, self._db_name)

    # --- the worker the supervisor restarts ----------------------------------
    def worker_argv(self, handle: SutHandle) -> list[str]:
        return [sys.executable, "-m", "crashproof.adapters.keel"]

    def worker_env(self, handle: SutHandle) -> dict[str, str]:
        return {
            TrialDir.ENV: str(handle.trial_dir),
            ENV_WORLD: handle.world_url,
            ENV_DSN: handle.dependency.dsn or "",
            ENV_WORKLOAD: self.workload.workload,
            ENV_VARIANT: self.variant,
        }

    # --- lifecycle -----------------------------------------------------------
    async def submit(self, handle: SutHandle) -> None:
        """Create the run. The only moment an id is handed to the SUT — and it is handed to the
        *store*, not to a command line, which is what `recovery_mechanism = self` means."""
        world = WorldClient(handle.world_url)
        app = build_app(self.workload, self.variant, world, None, handle.dependency.dsn or "")
        try:
            run = await app.start("tool_chain", {"task": "file an issue"})
            handle.run_ref = str(run.run_id)
            (handle.trial_dir / "sut" / "run_id").write_text(handle.run_ref, encoding="utf8")
        finally:
            await app.close()

    async def status(self, handle: SutHandle) -> str:
        """What the supervisor polls. Deliberately one row read: a status check that walked the
        journal would make the harness's own cost part of what it measures."""
        run_ref = handle.run_ref
        if not run_ref:
            return "UNKNOWN"
        row = await self._client(handle).journal.run_row(uuid.UUID(run_ref))
        if row is None:
            return "UNKNOWN"
        if row.terminal_at is not None:
            return _status_of(row.phase)
        return _status_of(row.phase) if row.phase == "SUSPENDED" else "RUNNING"

    async def on_worker_restart(self, handle: SutHandle) -> None:
        """A no-op, and that is the finding: the restarted process finds its own work."""
        return None

    async def collect(self, handle: SutHandle) -> CanonicalResult:
        run_ref = handle.run_ref or (handle.trial_dir / "sut" / "run_id").read_text(encoding="utf8").strip()
        app = self._client(handle)
        journal = app.journal
        run_id = uuid.UUID(run_ref)
        view = await app.get(run_id)
        events = await app.events(run_id)
        recoveries = await journal.recoveries(run_id)
        export = handle.trial_dir / "sut" / "journal.json"
        export.write_text(
            json.dumps(
                {
                    "run_id": run_ref,
                    "phase": view.phase,
                    "events": [
                        {
                            "seq": e.seq,
                            "type": e.type,
                            "ts": e.ts.isoformat(),
                            "lease_epoch": e.lease_epoch,
                            "step_index": e.step_index,
                            "attempt_no": e.attempt_no,
                            "body": e.body.model_dump(mode="json"),
                        }
                        for e in events
                    ],
                    "effects": [
                        {
                            "effect_key": r.effect_key,
                            "step_index": r.step_index,
                            "tool": r.tool,
                            "class": r.effect_class,
                            "status": r.status,
                            "external_ref": r.external_ref,
                            "resolution": r.resolution,
                        }
                        for r in view.effects
                    ],
                },
                indent=2,
            ),
            encoding="utf8",
        )
        committed = {
            r.external_ref
            for r in view.effects
            if r.status in ("COMMITTED", "RESOLVED_COMMITTED") and r.external_ref
        }
        return CanonicalResult(
            status=_status_of(view.phase),
            result=view.result,
            committed_effects=committed,
            export=export,
            steps=len(view.steps),
            model_calls=sum(1 for s in view.steps if s.kind == "MODEL" and s.state == "COMPLETED"),
            tokens=_tokens(events),
            recoveries=[
                {
                    "recovery_index": r.lease_epoch,
                    "lease_epoch": r.lease_epoch,
                    "cause": r.cause,
                    "acquired_at": r.acquired_at.isoformat() if r.acquired_at else None,
                    "outcome": r.outcome,
                    "replayed_steps": r.replayed_steps,
                }
                for r in recoveries
            ],
            detect_ms=_detect_ms(events),
            storage_bytes=await _storage_bytes(journal),
        )


def _status_of(phase: str) -> str:
    """The neutral mapping of §13.3: every waiting phase is WAITING, and both are legitimate ends
    of a trial when the workload expects them."""
    if phase in ("COMPLETED", "FAILED", "CANCELLED", "SUSPENDED"):
        return phase
    if phase.startswith("WAITING") or phase in ("SLEEPING", "PAUSED"):
        return "WAITING"
    if phase == "SUPERSEDED":
        return "FAILED"
    return "UNKNOWN"


def _tokens(events: list[Any]) -> int:
    total = 0
    for e in events:
        usage = getattr(e.body, "usage", None)
        if usage:
            total += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
    return total


def _detect_ms(events: list[Any]) -> float | None:
    """Keel's own detection time: the gap between the last event of a dead epoch and the first of
    its successor. Printed as a diagnostic, never used to compare arms — every other runtime is
    measured at the wire (§14.3)."""
    last_by_epoch: dict[int, Any] = {}
    for e in events:
        last_by_epoch[e.lease_epoch] = e
    starts = [e for e in events if e.type == "RECOVERY_STARTED" and e.lease_epoch > 1]
    if not starts:
        return None
    first = starts[0]
    prior = last_by_epoch.get(first.lease_epoch - 1)
    if prior is None:
        return None
    return (first.ts - prior.ts).total_seconds() * 1000


async def _storage_bytes(journal: Any) -> int | None:
    try:
        pool = await journal._ready()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0) FROM pg_class c"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'public' AND c.relname IN ('events','blobs','effects')"
            )
            row = await cur.fetchone()
            return int(row[0]) if row else None
    except Exception:  # noqa: BLE001 - a missing number is N/A, never a failed trial
        return None


def _db_name_for(trial_id: str) -> str:
    return "keel_" + re.sub(r"[^a-z0-9_]", "_", trial_id.lower())[:50]


# =============================================================================
# The worker process — restarted verbatim, told nothing
# =============================================================================
def main() -> None:  # pragma: no cover - exercised as a subprocess by every trial
    from keel.core import aio

    aio.run(_worker())


async def _worker() -> None:  # pragma: no cover - subprocess
    trial = TrialDir.from_env()
    cursor = trial.read_cursor()
    workload = load_named(os.environ[ENV_WORKLOAD])
    variant = os.environ[ENV_VARIANT]
    world = WorldClient(os.environ[ENV_WORLD])
    role = os.environ.get(ENV_ROLE, "worker")

    shim = None
    if role == "worker":
        # Only the process under test carries the shim. The successor in a pause cell must never
        # fire a fault, or the cell would freeze the very process that exists to take over.
        shim = ToolShim(
            trial,
            Schedule.read(trial.schedule_path),
            trial_id=cursor.trial_id,
            recovery_index=cursor.recovery_index,
            world=world,
        )

    app = build_app(workload, variant, world, shim, os.environ[ENV_DSN])
    from keel.runtime.reaper import Reaper

    await app.upsert_programs()
    if role != "worker":
        # A frozen process cannot reap itself, and a reaper that cannot *claim* is no successor:
        # it would mark the run ORPHANED and leave it there. So the second observer is a whole
        # worker — it simply waits long enough that the first one gets the run (§11.2).
        await asyncio.sleep(float(os.environ.get("CRASHPROOF_KEEL_START_DELAY_S", SUCCESSOR_START_DELAY_S)))
    worker = app.worker(worker_id=f"{role}-{os.getpid()}", lease_ttl=LEASE_TTL_S)
    tasks = [
        asyncio.create_task(worker.run_forever()),
        asyncio.create_task(Reaper(app.journal, period=0.2).run_forever()),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        await app.close()


if __name__ == "__main__":  # pragma: no cover
    main()
