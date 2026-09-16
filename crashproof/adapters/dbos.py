"""The DBOS adapter (§13.4, §13.5).

The same workload, World, shim and spec, expressed in DBOS's documented primitives. Two configs, one
axis — `agent_code` — because DBOS is the one runtime with two rows (§13.5):

    native       the agent loop is a `@DBOS.workflow`; every model call and every tool call is its
                 own `@DBOS.step`
    pydantic_ai  the same loop as a Pydantic AI `Agent` with `DBOSDurability`, run inside a
                 `@DBOS.workflow`: the capability makes each model request a DBOS step, and each
                 function tool is a `@DBOS.step` because the integration documents that it does not
                 wrap them ("Decorate with `@DBOS.step` if the function involves non-determinism
                 or I/O")

A difference between the two rows is a finding about the integration layer, not about DBOS.

**`recovery_mechanism = self`.** The first incarnation starts the workflow under an id that is a pure
function of the trial directory; every later incarnation only calls `DBOS.launch()`, whose PENDING
scan resumes the run ("each time you restart your application's process, DBOS recovers all workflows
that were executing before the restart"). Nothing re-starts, nudges or names the run on a restart.

**F1 is `f"{DBOS.workflow_id}:{DBOS.step_id}"`,** read inside the step that sends the effect: both are
persisted by DBOS and restored by its own recovery (step ids are assigned in program order, and the
workflow must be deterministic), so a re-executed step presents the same key.

**W5** waits in `DBOS.recv_async` with the run input's `expires_in` as the timeout ("returning `None`
if the wait times out"); the harness plays the human with `DBOSClient.send` from outside. The
Pydantic AI row reaches the same wait through deferred tools: a `requires_approval` tool ends the
run with `DeferredToolRequests`, the workflow `recv`s, and a second `agent.run` resumes with
`DeferredToolResults`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from crashproof.adapters.base import CanonicalResult, ConfigPin, Dependency, SutHandle
from crashproof.adapters.langgraph import _resolve, _resolve_text
from crashproof.faults.injectors.shim import ToolShim
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import Schedule
from crashproof.workloads.spec import Workload, load_named
from crashproof.world.client import DEFAULT_TIMEOUT_S, WorldClient

ENV_WORLD = "CRASHPROOF_WORLD_URL"
ENV_DSN = "CRASHPROOF_DBOS_DSN"
ENV_WORKLOAD = "CRASHPROOF_WORKLOAD"
ENV_VARIANT = "CRASHPROOF_VARIANT"
ENV_AGENT_CODE = "CRASHPROOF_DBOS_AGENT_CODE"

MAX_TURNS = 6
APPROVAL_TOPIC = "approval"
#: DBOS's own default, passed explicitly so it is printed. It only has to be ≥ the spec's
#: `max_recoveries` (§22.3), or DBOS would dead-letter a run the supervisor is still restarting.
MAX_RECOVERY_ATTEMPTS = 100

#: DBOS workflow status → the neutral status of §13.3. PENDING and ENQUEUED are not terminal; whether
#: a pending run is parked on its `recv` is the worker's `sut/status` marker.
_TERMINAL = {
    "SUCCESS": "COMPLETED",
    "ERROR": "FAILED",
    "CANCELLED": "CANCELLED",
    # A dead letter: "its status is set to MAX_RECOVERY_ATTEMPTS_EXCEEDED and it may no longer be
    # executed". Unreachable while MAX_RECOVERY_ATTEMPTS ≥ max_recoveries; FAILED if it ever is.
    "MAX_RECOVERY_ATTEMPTS_EXCEEDED": "FAILED",
}


def workflow_id_for(trial_dir: Path) -> str:
    """A pure function of the trial directory — the same string in the harness and in every
    incarnation of the worker, so nothing ever has to be handed to either."""
    return f"crashproof-{trial_dir.name}"


def _sends_key(effect_class: str, key_source: str) -> bool:
    return key_source == "framework" and effect_class in ("IDEMPOTENT", "TRANSACTIONAL")


def _node_id(key: tuple[tuple[str, int], ...]) -> str:
    return "-".join(f"{n}{i}" for n, i in key) or "start"


def _step_key() -> str:
    """F1 (§13.6): documented, persisted and restored by DBOS itself."""
    from dbos import DBOS

    return f"{DBOS.workflow_id}:{DBOS.step_id}"


# =============================================================================
# The workload, as native DBOS
# =============================================================================
def build_native(
    workload: Workload, variant: str, world: WorldClient, shim: ToolShim | None,
    park: Callable[[str], None] | None = None,
) -> Any:
    """Returns the `@DBOS.workflow`. One model call = one step, one tool call = one step, and the
    loop between them is deterministic workflow code that recovery re-executes."""
    from dbos import DBOS

    decls = {t.name: t for t in workload.tools_for(variant)}
    key_source = workload.variant(variant).key_source

    @DBOS.step(name="crashproof.model", retries_allowed=False)
    async def model(task: dict[str, Any], answered: list[str], results: dict[str, Any]) -> dict[str, Any]:
        key = Workload.node_key(answered)
        node = workload.node_for(key)

        def decide() -> dict[str, Any]:
            decision = Workload.decision_of(node, alternate=shim is not None and shim.alternate_armed)
            calls = decision.get("tool_calls") or []
            if not calls:
                return {"answer": _resolve_text(str(decision.get("final", "")), results)}
            return {
                "pending": {"name": calls[0]["name"], "args": _resolve(calls[0].get("args", {}), results)},
                "approval": decision.get("approval"),
                "before_approval": [
                    {"name": c["name"], "args": _resolve(c.get("args", {}), results)}
                    for c in decision.get("before_approval") or []
                ],
            }

        if shim is None:
            return decide()
        prompt = {"task": task, "answered": answered, "results": results}
        return await shim.model_call(_node_id(key), decide, prompt=prompt)

    @DBOS.step(name="crashproof.tool", retries_allowed=False)
    async def tool(name: str, args: dict[str, Any]) -> Any:
        decl = decls[name]
        key = _step_key() if _sends_key(decl.effect_class, key_source) else None
        if shim is None:
            return await world.acall(decl.endpoint, args, effect_key=key)
        return await shim.tool_call(name, decl.endpoint, args, effect_key=key)

    @DBOS.workflow(name="crashproof.native", max_recovery_attempts=MAX_RECOVERY_ATTEMPTS)
    async def agent(task: dict[str, Any]) -> dict[str, Any]:
        answered: list[str] = []
        results: dict[str, Any] = {}
        for _ in range(MAX_TURNS):
            decided = await model(task, answered, results)
            if "answer" in decided:
                return {"answer": decided["answer"]}
            # W5-pre: the calls a node makes before it asks, each its own step, ahead of the wait.
            for pre in decided["before_approval"]:
                results[pre["name"]] = await tool(pre["name"], pre["args"])
                answered.append(pre["name"])
            if decided.get("approval"):
                verdict = await _wait_for_human(task, park)
                if verdict != "granted":
                    return {"answer": f"not done: approval {verdict}"}
            pending = decided["pending"]
            results[pending["name"]] = await tool(pending["name"], pending["args"])
            answered.append(pending["name"])
        return {"answer": "(turns exhausted)"}

    return agent


async def _wait_for_human(task: dict[str, Any], park: Callable[[str], None] | None) -> str:
    """DBOS's documented durable wait, and nothing else: `recv` "waits for and consumes the next
    message to arrive in the queue for the specified topic, returning `None` if the wait times out".
    The deadline is the run input's `expires_in`, as it is for every arm.

    `park` is the harness's window onto the wait (`status()` reports WAITING). It is a file write in
    workflow code, so recovery repeats it — harmless, and it adds no durable operation to the run."""
    from dbos import DBOS

    if park:
        park("WAITING")
    message = await DBOS.recv_async(APPROVAL_TOPIC, timeout_seconds=float(task.get("expires_in", 60)))
    if park:
        park("RUNNING")
    return "expired" if message is None else str(message.get("decision"))


# =============================================================================
# The workload, as a Pydantic AI agent under DBOSDurability
# =============================================================================
def build_agent(workload: Workload, variant: str, world: WorldClient | None, shim: ToolShim | None) -> Any:
    """The shared Pydantic AI agent (`pydantic_ai_agent`) with DBOS's three engine-specific parts: the
    `{workflow_id}:{step_id}` key, each function tool as a `@DBOS.step` — the integration documents that
    it does not wrap them ("Decorate with `@DBOS.step` if the function involves non-determinism or
    I/O") — and `DBOSDurability`, which makes each model request a step."""
    from dbos import DBOS
    from pydantic_ai.durable_exec.dbos import DBOSDurability

    from crashproof.adapters import pydantic_ai_agent

    return pydantic_ai_agent.build_agent(
        workload,
        variant,
        world=world,
        shim=shim,
        key=_step_key,
        wrap=lambda fn, decl: DBOS.step(name=f"crashproof.tool.{decl.name}", retries_allowed=False)(fn),
        durability=DBOSDurability(),
    )


def build_pydantic_ai(
    workload: Workload, variant: str, world: WorldClient, shim: ToolShim | None,
    park: Callable[[str], None] | None = None,
) -> Any:
    """Returns the `@DBOS.workflow` that runs the shared agent. A gated tool is `requires_approval`, so
    the run ends in `DeferredToolRequests` where every other arm parks, and the wait is DBOS's `recv`."""
    from dbos import DBOS

    from crashproof.adapters import pydantic_ai_agent

    agent = build_agent(workload, variant, world, shim)

    @DBOS.workflow(name="crashproof.pydantic_ai", max_recovery_attempts=MAX_RECOVERY_ATTEMPTS)
    async def run(task: dict[str, Any]) -> dict[str, Any]:
        return await pydantic_ai_agent.run_agent(agent, task, lambda: _wait_for_human(task, park))

    return run


BUILDERS = {"native": build_native, "pydantic_ai": build_pydantic_ai}


# =============================================================================
# The adapter
# =============================================================================
class DBOSAdapter:
    _template_ready = False

    name = "dbos"
    recovery_mechanism = "self"
    key_sources = frozenset({"none", "framework"})
    workloads = frozenset({"tool_chain_1_effect", "approval_gated_deploy", "approval_gated_deploy_pre"})
    workload_evidence = {
        "tool_chain_1_effect": (
            "native: @DBOS.workflow loop, one @DBOS.step per model and per tool call; pydantic_ai: "
            "Agent + DBOSDurability (model requests are DBOS steps) with @DBOS.step function tools "
            "(docs.dbos.dev/python/tutorials/workflow-tutorial; pydantic.dev/docs/ai/integrations/"
            "durable_execution/dbos)"
        ),
        "approval_gated_deploy": (
            "DBOS.recv(topic, timeout_seconds) in the workflow before the gated step, DBOSClient.send "
            "from outside (docs.dbos.dev/python/tutorials/workflow-communication); pydantic_ai: "
            "requires_approval tool -> DeferredToolRequests -> recv -> DeferredToolResults"
        ),
        "approval_gated_deploy_pre": (
            "as approval_gated_deploy, with the `before_approval` calls as their own steps ahead of "
            "the recv (pydantic_ai: in the same model response as the deferred call)"
        ),
    }
    claims: dict[str, str] = {
        # "Steps are tried at least once but are never re-executed after they complete."
        "PURE": "at_least_once",
        "EXTERNAL": "at_least_once",
        # F1: a key DBOS persists and restores, presented to a receiver that dedups on it (§13.6).
        "IDEMPOTENT": "effectively_once",
    }

    def __init__(
        self, workload: Workload, variant: str, *, agent_code: str = "native",
        template_db: str = "dbos_template",
    ) -> None:
        if agent_code not in BUILDERS:
            raise ValueError(f"agent_code must be one of {sorted(BUILDERS)}, not {agent_code!r}")
        self.workload = workload
        self.variant = variant
        self.agent_code = agent_code
        self.template_db = template_db
        self._admin_dsn: str | None = None
        self._db_name: str | None = None
        self._dbos_client: Any = None

    def config_pin(self, *, worker_count: int = 1, **extra: Any) -> ConfigPin:
        import importlib.metadata as md

        versions = {"dbos": md.version("dbos"), "python": sys.version.split()[0]}
        if self.agent_code == "pydantic_ai":
            versions["pydantic-ai-slim"] = md.version("pydantic-ai-slim")
        return ConfigPin(
            framework_versions=versions,
            backend="postgres (DBOS system database, one per trial)",
            durability="step checkpoint",
            # The adapter adds none (§13.3 rule 1), and DBOS's own is off: `retries_allowed=False`.
            retry="none: @DBOS.step(retries_allowed=False)",
            worker_count=worker_count,
            extra={
                "agent_code": self.agent_code,
                "max_recovery_attempts": MAX_RECOVERY_ATTEMPTS,
                "executor_id": "local (no Conductor)",
                "application_version": "DBOS default: hash of workflow source",
                "recv_timeout": "run input expires_in",
                "step_timeout": "none",
                "world_client_timeout_s": DEFAULT_TIMEOUT_S,
                **(
                    {"parallel_execution_mode": "parallel_ordered_events (default)",
                     "model_step_config": "default (retries_allowed=False)"}
                    if self.agent_code == "pydantic_ai" else {}
                ),
                **extra,
            },
        )

    def worker_count(self, spec: Any) -> int:
        """One. DBOS without Conductor has no successor: recovery is the restarted process (§13.4)."""
        if getattr(spec, "max_recoveries", 0) > MAX_RECOVERY_ATTEMPTS:
            raise ValueError(f"max_recoveries > max_recovery_attempts={MAX_RECOVERY_ATTEMPTS}: DBOS would dead-letter")
        return 1

    # --- dependency ----------------------------------------------------------
    async def start_dependency(self, handle: SutHandle) -> Dependency:
        from crashproof.runner import database

        self._admin_dsn = os.environ.get("KEEL_DSN", "postgresql://keel:keel@localhost:5432/keel")
        await self._ensure_template(self._admin_dsn)
        self._db_name = _db_name_for(handle.trial_dir)
        dsn = await database.create_from_template(self._admin_dsn, self._db_name, template=self.template_db)
        return Dependency(name="postgres", dsn=dsn, env={ENV_DSN: dsn})

    async def _ensure_template(self, admin_dsn: str) -> None:
        """The DBOS system schema, migrated once into a template: what `dbos migrate` runs."""
        if DBOSAdapter._template_ready:
            return
        from dbos.cli.migration import run_dbos_database_migrations

        from crashproof.runner import database

        template_dsn = await database.ensure_template(admin_dsn, self.template_db)
        await asyncio.to_thread(run_dbos_database_migrations, template_dsn)
        DBOSAdapter._template_ready = True

    async def stop_dependency(self, handle: SutHandle) -> None:
        from crashproof.runner import database

        if self._dbos_client is not None:
            self._dbos_client.destroy()
            self._dbos_client = None
        if self._admin_dsn and self._db_name:
            await database.drop(self._admin_dsn, self._db_name)

    def _client(self, handle: SutHandle) -> Any:
        from dbos import DBOSClient

        if self._dbos_client is None:
            self._dbos_client = DBOSClient(system_database_url=handle.dependency.dsn or "")
        return self._dbos_client

    # --- lifecycle -----------------------------------------------------------
    def worker_argv(self, handle: SutHandle) -> list[str]:
        return [sys.executable, "-m", "crashproof.adapters.dbos"]

    def worker_env(self, handle: SutHandle) -> dict[str, str]:
        return {
            TrialDir.ENV: str(handle.trial_dir),
            ENV_WORLD: handle.world_url,
            ENV_DSN: handle.dependency.dsn or "",
            ENV_WORKLOAD: self.workload.workload,
            ENV_VARIANT: self.variant,
            ENV_AGENT_CODE: self.agent_code,
        }

    async def submit(self, handle: SutHandle) -> None:
        """Nothing to hand over: the workflow id is a function of the trial directory, and the first
        incarnation starts the run itself."""
        handle.run_ref = workflow_id_for(handle.trial_dir)

    async def on_worker_restart(self, handle: SutHandle) -> None:
        """A no-op, and that is the finding: `DBOS.launch()` in the restarted process recovers it."""
        return None

    async def status(self, handle: SutHandle) -> str:
        rows = await asyncio.to_thread(
            self._client(handle).list_workflows,
            workflow_ids=[workflow_id_for(handle.trial_dir)], load_input=False, load_output=False,
        )
        if rows and rows[0].status in _TERMINAL:
            return _TERMINAL[rows[0].status]
        marker = handle.trial_dir / "sut" / "status"
        return "WAITING" if marker.exists() and marker.read_text(encoding="utf8").strip() == "WAITING" else "RUNNING"

    async def approve(self, handle: SutHandle, *, by: str = "harness", decision: str = "approve") -> bool:
        """The harness plays the human with DBOS's documented outside-the-app send (`DBOSClient.send`).

        No idempotency key, ever: §11.4 C's second click is this same call again, so DBOS persists a
        second message on the topic. The workflow `recv`s once; what becomes of the other message
        is DBOS's to decide and the trial's to show."""
        verdict = "granted" if decision == "approve" else "rejected"
        await asyncio.to_thread(
            self._client(handle).send,
            workflow_id_for(handle.trial_dir), {"decision": verdict, "by": by}, APPROVAL_TOPIC,
        )
        return True

    async def collect(self, handle: SutHandle) -> CanonicalResult:
        client = self._client(handle)
        wid = workflow_id_for(handle.trial_dir)
        rows = await asyncio.to_thread(client.list_workflows, workflow_ids=[wid], load_input=False)
        steps = await asyncio.to_thread(client.list_workflow_steps, wid) if rows else []
        wf = rows[0] if rows else None
        status = await self.status(handle) if wf else "UNKNOWN"
        if status == "RUNNING":  # a PENDING run at collection is not an outcome (§13.3)
            status = "UNKNOWN"
        export = handle.trial_dir / "sut" / "steps.json"
        export.write_text(
            json.dumps(
                {
                    "workflow_id": wid,
                    "status": wf.status if wf else None,
                    "recovery_attempts": getattr(wf, "recovery_attempts", None),
                    "steps": [
                        {k: s.get(k) for k in ("function_id", "function_name", "started_at_epoch_ms", "completed_at_epoch_ms")}
                        | {"error": None if s.get("error") is None else repr(s["error"])}
                        for s in steps
                    ],
                },
                indent=2,
            ),
            encoding="utf8",
        )
        return CanonicalResult(
            status=status,  # type: ignore[arg-type]
            result=wf.output if wf else None,
            # A completed step's recorded output is the World's own response, which names its label
            # (`external_ref`). Read, not counted: only steps DBOS checkpointed as complete are here.
            committed_effects={
                s["output"]["external_ref"]
                for s in steps
                if isinstance(s.get("output"), dict) and s["output"].get("external_ref")
            },
            export=export,
            steps=len(steps),
        )


def _db_name_for(trial_dir: Path) -> str:
    tag = hashlib.sha256(str(trial_dir.resolve()).encode()).hexdigest()[:8]
    return "dbos_" + re.sub(r"[^a-z0-9_]", "_", trial_dir.name.lower())[:40] + "_" + tag


# =============================================================================
# The worker process — restarted verbatim, told nothing
# =============================================================================
def main() -> None:  # pragma: no cover - a subprocess in every trial
    from crashproof.runner import aio

    aio.run(_worker())


async def _worker() -> None:  # pragma: no cover - subprocess
    from dbos import DBOS, SetWorkflowID

    trial = TrialDir.from_env()
    cursor = trial.read_cursor()
    workload = load_named(os.environ[ENV_WORKLOAD])
    world = WorldClient(os.environ[ENV_WORLD])
    trial.announce_pid(cursor.recovery_index)

    shim = ToolShim(
        trial,
        Schedule.read(trial.schedule_path),
        trial_id=cursor.trial_id,
        recovery_index=cursor.recovery_index,
        world=world,
        observe_only=os.environ.get("CRASHPROOF_MODE") == "proxy",
        sut_ref=lambda: {"workflow_id": DBOS.workflow_id, "step_id": DBOS.step_id},
    )
    marker = trial.path / "sut" / "status"

    DBOS(config={"name": "crashproof", "system_database_url": os.environ[ENV_DSN], "run_admin_server": False})
    workflow = BUILDERS[os.environ[ENV_AGENT_CODE]](
        workload, os.environ[ENV_VARIANT], world, shim, lambda s: marker.write_text(s, encoding="utf8")
    )
    DBOS.launch()  # recovers every PENDING workflow of this executor — the whole of `self`
    if cursor.recovery_index == 0:
        with SetWorkflowID(workflow_id_for(trial.path)):
            await DBOS.start_workflow_async(workflow, workload.input)
    await asyncio.Event().wait()  # the supervisor ends the process; exiting would read as a crash


if __name__ == "__main__":  # pragma: no cover
    main()
