"""The Temporal adapter, `agent_code = pydantic_ai` (§13.4, §13.5).

The canonical ReAct workload is written once as a Pydantic AI `Agent` with the `TemporalDurability`
capability — the current form in pydantic-ai-slim 2.43; `TemporalAgent` is the deprecated wrapper —
and Temporal runs it. Nothing here is Temporal-specific agent code: the model request and every tool
call become Activities because that is what the capability does, and the workflow body is
`agent.run()` plus the approval wait. A native Temporal adapter is §13.5's V2 item and is not built,
so `pydantic_ai` is the only config and the cell ids read `temporal.pydantic_ai.<variant>.<trigger>`,
the same `runtime.config` shape as `langgraph.sync`.

**`recovery_mechanism = engine`.** The dev server — one per trial, `--db-filename` in the trial
directory, never killed — is the successor. It does not see the worker die (fact sheet: "The Temporal
Server doesn't detect failures when a Worker loses communication with the Server or crashes"); the
activity's heartbeat or start-to-close timeout expires, the RetryPolicy schedules the next attempt,
and whichever worker polls the task queue runs it. The restarted worker is started with the same argv
and is told nothing: it polls a task queue whose name is a constant, and `on_worker_restart` is a
no-op.

**The workflow is started once, by the adapter, at `submit`.** In Temporal a client starts a
workflow and a worker polls for its tasks, and those are different programs; putting the start in the
first incarnation would make the worker do something only on its first life, which is exactly the
kind of process memory §13.3 rule 3 forbids. So the worker never starts, signals or queries anything,
and its argv is `python -m crashproof.adapters.temporal` on every spawn.

**F1.** `f"{workflow_run_id}:{activity_id}"` from `activity.info()`, read inside the tool body, which
runs inside the tool-call activity. Fact sheet: "You can use a combination of the Workflow Run ID and
the Activity ID as an idempotency key since this is guaranteed to be consistent across retry attempts
but unique among Workflow Executions." Sent only when the variant asks for `framework`.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import AgentPlugin, PydanticAIPlugin, TemporalDurability
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

from crashproof.adapters import pydantic_ai_agent
from crashproof.adapters.base import CanonicalResult, ConfigPin, Dependency, SutHandle
from crashproof.faults import process
from crashproof.faults.injectors.shim import ToolShim
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import Schedule
from crashproof.workloads.spec import Workload, load_named
from crashproof.world.client import DEFAULT_TIMEOUT_S, WorldClient

ENV_WORLD = "CRASHPROOF_WORLD_URL"
ENV_TEMPORAL = "CRASHPROOF_TEMPORAL_ADDRESS"
ENV_WORKLOAD = "CRASHPROOF_WORKLOAD"
ENV_VARIANT = "CRASHPROOF_VARIANT"
ENV_BIN = "CRASHPROOF_TEMPORAL_BIN"
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # a banner in every worker log is noise

# --- pins from §13.4: detection is the pinned timeout, so the timeouts are seconds ------------------
START_TO_CLOSE_S = 5.0
HEARTBEAT_S = 2.0
#: Temporal's documented default policy, spelled out so the row prints it rather than implying it:
#: 1 s initial interval, ×2 backoff, 100 s cap, unlimited attempts. `TemporalDurability` appends
#: its own non-retryable error types (UserError & co.), which the pin records too.
RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=100),
    maximum_attempts=0,
)
TASK_QUEUE = "crashproof"

#: The agent the workflow runs. A worker builds it once at start (with its shim); the harness builds
#: it without one for the Replayer. Module state because the workflow class must be importable at
#: module level (the sandbox imports it by name) and `crashproof` is passed through the sandbox, so
#: the workflow and the worker see this same object.
_AGENT: Agent[None, Any] | None = None


# =============================================================================
# The workload: the shared Pydantic AI agent, with Temporal's engine-specific parts
# =============================================================================
def build_agent(workload: Workload, variant: str, world: WorldClient | None, shim: ToolShim | None) -> Agent:
    """`pydantic_ai_agent.build_agent` with Temporal's key, no tool wrapping (the capability makes every
    tool call an activity), and `TemporalDurability` pinned to §13.4's timeouts. Sets `_AGENT`."""
    global _AGENT
    _AGENT = pydantic_ai_agent.build_agent(
        workload,
        variant,
        world=world,
        shim=shim,
        key=_activity_key,
        durability=TemporalDurability(
            activity_config=ActivityConfig(
                start_to_close_timeout=timedelta(seconds=START_TO_CLOSE_S),
                heartbeat_timeout=timedelta(seconds=HEARTBEAT_S),
                retry_policy=RETRY_POLICY,
            ),
        ),
    )
    return _AGENT


def _activity_key() -> str:
    """F1: the tool body runs inside its tool-call activity, whose info carries both ids."""
    info = activity.info()
    return f"{info.workflow_run_id}:{info.activity_id}"


@workflow.defn(name="crashproof_react")
class ReActWorkflow:
    """The shared agent run, and — when it ends asking for approval — Temporal's documented wait: a
    signal and `workflow.wait_condition` with the run input's `expires_in` as a durable timer."""

    def __init__(self) -> None:
        self.decisions: list[dict[str, Any]] = []

    @workflow.signal(name="approve")
    def approve(self, decision: dict[str, Any]) -> None:
        # Every click is kept in the order delivered. The first one decides; whether a second one
        # reaches anything is Temporal's finding (§11.4 C).
        self.decisions.append(decision)

    @workflow.run
    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        assert _AGENT is not None
        return await pydantic_ai_agent.run_agent(_AGENT, task, lambda: self._wait(task))

    async def _wait(self, task: dict[str, Any]) -> str:
        # Memo, so `status()` reads the park from `describe()` without a worker — the worker may be the
        # thing that was killed while parked.
        workflow.upsert_memo({"waiting": True})
        try:
            await workflow.wait_condition(
                lambda: bool(self.decisions), timeout=timedelta(seconds=float(task.get("expires_in", 5)))
            )
            verdict = str(self.decisions[0].get("decision"))
        except TimeoutError:
            verdict = "expired"
        workflow.upsert_memo({"waiting": False})
        return verdict


def _workflow_runner() -> Any:
    """The default sandbox, with `crashproof` passed through so the workflow sees the worker's agent
    rather than a re-import of this module. The plugin adds its own passthroughs on top."""
    from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

    return SandboxedWorkflowRunner(restrictions=SandboxRestrictions.default.with_passthrough_modules("crashproof", "annotated_types"))


# =============================================================================
# The adapter
# =============================================================================
class TemporalAdapter:
    name = "temporal"
    recovery_mechanism = "engine"
    key_sources = frozenset({"none", "framework"})
    workloads = frozenset({"tool_chain_1_effect", "approval_gated_deploy", "approval_gated_deploy_pre"})
    workload_evidence = {
        "tool_chain_1_effect": (
            "Pydantic AI + TemporalDurability: 'model requests, tool calls, and MCP server communication "
            "are routed through Temporal activities' (pydantic.dev/docs/ai/capabilities/durable_execution/temporal)"
        ),
        "approval_gated_deploy": (
            "deferred tools: requires_approval=True ends the run with DeferredToolRequests; continued with "
            "message_history + deferred_tool_results. The wait is a signal + workflow.wait_condition(timeout=) "
            "(docs.temporal.io/develop/python/message-passing; fact sheet human_in_loop)"
        ),
        "approval_gated_deploy_pre": (
            "as approval_gated_deploy, with the `before_approval` call in the same model response as the gated "
            "one: it runs as its own activity before the run ends asking for approval"
        ),
    }
    #: Fact sheet: "Activities are at-least-once" and "Temporal recommends that Activities be
    #: idempotent". The one class that may claim more is the one where a receiver honours the
    #: documented key: "guaranteed to be consistent across retry attempts".
    claims: dict[str, str] = {
        "PURE": "at_least_once",
        "IDEMPOTENT": "effectively_once",
        "EXTERNAL": "at_least_once",
    }
    _versions: dict[str, str] | None = None

    def __init__(self, workload: Workload, variant: str, *, agent_code: str = "pydantic_ai") -> None:
        if agent_code != "pydantic_ai":
            raise ValueError("a native Temporal adapter is a V2 item (§13.5); only agent_code=pydantic_ai is built")
        self.workload = workload
        self.variant = variant
        self._client: Any = None
        self._server: subprocess.Popen | None = None

    # --- declarations --------------------------------------------------------
    def config_pin(self, *, worker_count: int = 1, **extra: Any) -> ConfigPin:
        return ConfigPin(
            framework_versions=self.versions(),
            backend="temporal server start-dev --db-filename (SQLite), one per trial",
            durability="event history; agent_code=pydantic_ai (TemporalDurability)",
            tool_timeout_s=START_TO_CLOSE_S,
            heartbeat_s=HEARTBEAT_S,
            # Detection of a frozen worker is the heartbeat timeout (§13.4), so the pause is drawn over it.
            detection_timeout_s=HEARTBEAT_S,
            retry=(
                "RetryPolicy(initial_interval=1s, backoff_coefficient=2.0, maximum_interval=100s, "
                "maximum_attempts=0) + TemporalDurability non_retryable_error_types"
            ),
            worker_count=worker_count,
            extra={
                "start_to_close_s": START_TO_CLOSE_S,
                "heartbeat_timeout_s": HEARTBEAT_S,
                "applies_to": "model-request and tool-call activities alike",
                # Pydantic docs: "turn off your provider API client's own retry logic". The provider is
                # a FunctionModel with no HTTP client, and the World client never retries.
                "client_retries": "none (FunctionModel has no provider client; the World client does not retry)",
                "heartbeat_throttle": "SDK default: 0.8 x heartbeat_timeout",
                "workflow_task_timeout_s": 10.0,
                "sticky_queue_schedule_to_start_timeout_s": 10.0,
                "world_client_timeout_s": DEFAULT_TIMEOUT_S,
                **extra,
            },
        )

    @classmethod
    def versions(cls) -> dict[str, str]:
        if cls._versions is None:
            import importlib.metadata as md

            cli = subprocess.run([temporal_bin(), "--version"], capture_output=True, text=True, check=False)
            cls._versions = {
                "temporalio": md.version("temporalio"),
                "pydantic-ai-slim": md.version("pydantic-ai-slim"),
                "temporal-cli": cli.stdout.strip(),
                "python": sys.version.split()[0],
            }
        return cls._versions

    def worker_count(self, spec: Any) -> int:
        """One: the server is the successor (§13.4)."""
        return 1

    # --- dependency ----------------------------------------------------------
    async def start_dependency(self, handle: SutHandle) -> Dependency:
        """`temporal server start-dev --db-filename <trial>/sut/temporal.db` on a free port (§22.3).
        Never killed during the trial; only the worker is."""
        from temporalio.client import Client

        sut = handle.trial_dir / "sut"
        port = _free_port()
        log = (sut / "temporal-server.log").open("w", encoding="utf8", errors="replace")
        self._server = subprocess.Popen(
            [
                temporal_bin(), "server", "start-dev", "--db-filename", str(sut / "temporal.db"),
                "--ip", "127.0.0.1", "--port", str(port), "--headless", "--log-level", "warn",
            ],
            stdout=log, stderr=subprocess.STDOUT,
        )
        log.close()
        address = f"127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while True:
            try:
                self._client = await Client.connect(address, plugins=[PydanticAIPlugin()])
                await self._client.count_workflows()  # the default namespace is up, not just the port
                break
            except Exception:
                if self._server.poll() is not None or time.monotonic() > deadline:
                    raise
                await asyncio.sleep(0.25)
        return Dependency(name="temporal", dsn=address, env={ENV_TEMPORAL: address}, teardown=self._server)

    async def stop_dependency(self, handle: SutHandle) -> None:
        self._client = None
        if self._server is not None and self._server.poll() is None:
            process.kill(self._server.pid)
            self._server.wait(timeout=30)
        self._server = None

    # --- lifecycle -----------------------------------------------------------
    def worker_argv(self, handle: SutHandle) -> list[str]:
        return [sys.executable, "-m", "crashproof.adapters.temporal"]

    def worker_env(self, handle: SutHandle) -> dict[str, str]:
        return {
            TrialDir.ENV: str(handle.trial_dir),
            ENV_WORLD: handle.world_url,
            ENV_TEMPORAL: handle.dependency.dsn or "",
            ENV_WORKLOAD: self.workload.workload,
            ENV_VARIANT: self.variant,
        }

    async def submit(self, handle: SutHandle) -> None:
        """Start the workflow, once. Its id is the trial directory's name — each trial has its own
        server, so it only has to be unique there — and it is never given to a worker."""
        workflow_id = f"crashproof-{handle.trial_dir.name}"
        await self._client.start_workflow(
            ReActWorkflow.run, self.workload.input, id=workflow_id, task_queue=TASK_QUEUE
        )
        handle.run_ref = workflow_id
        (handle.trial_dir / "sut" / "workflow_id").write_text(workflow_id, encoding="utf8")

    async def on_worker_restart(self, handle: SutHandle) -> None:
        """A no-op, and that is the finding: the server re-dispatches to whoever polls."""
        return None

    def _handle(self, handle: SutHandle) -> Any:
        return self._client.get_workflow_handle(handle.run_ref)

    async def status(self, handle: SutHandle) -> str:
        """`describe()` — no worker involved, so a killed worker cannot make the harness wait."""
        from temporalio.client import WorkflowExecutionStatus as S

        if handle.run_ref is None or self._client is None:
            return "UNKNOWN"
        desc = await self._handle(handle).describe()
        if desc.status == S.RUNNING:
            return "WAITING" if await desc.memo_value("waiting", False) else "RUNNING"
        return {
            S.COMPLETED: "COMPLETED",
            S.CANCELED: "CANCELLED",
            S.FAILED: "FAILED",
            S.TERMINATED: "FAILED",
            S.TIMED_OUT: "FAILED",
        }.get(desc.status, "UNKNOWN")

    async def approve(self, handle: SutHandle, *, by: str = "harness", decision: str = "approve") -> bool:
        """The harness plays the human: one `approve` signal, sent the same way every time. The
        second click of §11.4 C is a second identical signal; Temporal records both, and a signal to
        a workflow that has already closed is refused by the server, which is reported, not raised."""
        from temporalio.service import RPCError

        verdict = "granted" if decision == "approve" else "rejected"
        try:
            await self._handle(handle).signal(ReActWorkflow.approve, {"decision": verdict, "by": by})
        except RPCError:
            return False
        return True

    async def collect(self, handle: SutHandle) -> CanonicalResult:
        wf = self._handle(handle)
        status = await self.status(handle)
        answer = await wf.result() if status == "COMPLETED" else None
        history = await wf.fetch_history()
        committed, recoveries = read_history(history, self.workload, self.variant)
        export = handle.trial_dir / "sut" / "history.json"
        export.write_text(
            json.dumps(
                {"workflow_id": handle.run_ref, "committed": sorted(committed), "history": history.to_json_dict()},
                indent=1,
            ),
            encoding="utf8",
        )
        return CanonicalResult(
            status=status,  # type: ignore[arg-type]
            result=answer,
            committed_effects=committed,
            export=export,
            recoveries=recoveries,
        )

    async def replay_check(self, handle: SutHandle, result: CanonicalResult) -> dict[str, Any] | None:
        """C1 with Temporal's own `Replayer`: the recorded history replayed against the workflow code,
        which fails on any command the code would not issue again (nondeterminism). No activity runs."""
        from temporalio.worker import Replayer

        history = await self._handle(handle).fetch_history()
        agent = build_agent(self.workload, self.variant, None, None)
        replayer = Replayer(
            workflows=[ReActWorkflow],
            plugins=[PydanticAIPlugin(), AgentPlugin(agent)],
            workflow_runner=_workflow_runner(),
        )
        out = await replayer.replay_workflow(history, raise_on_replay_failure=False)
        scheduled = sum(1 for e in history.events if e.HasField("activity_task_scheduled_event_attributes"))
        if out.replay_failure is not None:
            return {"ok": False, "error": f"Replayer: {out.replay_failure}", "replayed_steps": scheduled}
        return {"ok": True, "replayed_steps": scheduled}


def read_history(history: Any, workload: Workload, variant: str) -> tuple[set[str], list[dict[str, Any]]]:
    """What Temporal durably recorded, read from its own event history and nothing else.

    `committed`: the World label (`external_ref`) in the result of every *completed* tool-call
    activity of a non-PURE tool — an `ActivityTaskCompleted` event is the engine's record that the
    effect's activity finished. `recoveries`: every `ActivityTaskStarted` with `attempt > 1`, with the
    failure that ended the previous attempt (a heartbeat or start-to-close timeout after a kill)."""
    classes = {t.name: t.effect_class for t in workload.tools_for(variant)}
    scheduled: dict[int, dict[str, Any]] = {}
    committed: set[str] = set()
    recoveries: list[dict[str, Any]] = []
    for event in history.events:
        if event.HasField("activity_task_scheduled_event_attributes"):
            attrs = event.activity_task_scheduled_event_attributes
            params = _payload(attrs.input.payloads[0]) if attrs.input.payloads else {}
            scheduled[event.event_id] = {
                "activity_id": attrs.activity_id,
                "type": attrs.activity_type.name,
                "tool": params.get("name") if attrs.activity_type.name.endswith("__call_tool") else None,
            }
        elif event.HasField("activity_task_started_event_attributes"):
            attrs = event.activity_task_started_event_attributes
            if attrs.attempt > 1:
                act = scheduled.get(attrs.scheduled_event_id, {})
                recoveries.append({
                    "activity_id": act.get("activity_id"),
                    "activity_type": act.get("type"),
                    "attempt": attrs.attempt,
                    "last_failure": attrs.last_failure.message,
                    "ts": event.event_time.ToDatetime().isoformat(),
                })
        elif event.HasField("activity_task_completed_event_attributes"):
            attrs = event.activity_task_completed_event_attributes
            tool = scheduled.get(attrs.scheduled_event_id, {}).get("tool")
            if tool is None or classes.get(tool, "PURE") == "PURE" or not attrs.result.payloads:
                continue
            ref = (_payload(attrs.result.payloads[0]).get("result") or {}).get("external_ref")
            if ref:
                committed.add(ref)
    return committed, recoveries


def _payload(payload: Any) -> dict[str, Any]:
    try:
        value = json.loads(payload.data)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def temporal_bin() -> str:
    """`$CRASHPROOF_TEMPORAL_BIN`, then `temporal` on PATH, then the CLI installer's default place."""
    found = os.environ.get(ENV_BIN) or shutil.which("temporal")
    if found:
        return found
    exe = "temporal.exe" if sys.platform == "win32" else "temporal"
    return str(Path.home() / ".temporalio" / "bin" / exe)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _sut_ref() -> dict[str, Any]:
    """§11.7's Temporal `sut_ref`, from inside whichever activity the boundary fired in."""
    try:
        info = activity.info()
    except RuntimeError:
        return {}
    return {"workflow_run_id": info.workflow_run_id, "activity_id": info.activity_id, "attempt": info.attempt}


# =============================================================================
# The worker process — restarted verbatim, told nothing
# =============================================================================
def main() -> None:  # pragma: no cover - a subprocess in every trial
    asyncio.run(_worker())


async def _worker() -> None:  # pragma: no cover - subprocess
    from temporalio.client import Client
    from temporalio.worker import Worker

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
        sut_ref=_sut_ref,
    )
    agent = build_agent(workload, os.environ[ENV_VARIANT], world, shim)
    client = await Client.connect(os.environ[ENV_TEMPORAL], plugins=[PydanticAIPlugin()])
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ReActWorkflow],
        plugins=[AgentPlugin(agent)],
        workflow_runner=_workflow_runner(),
    )
    await worker.run()


if __name__ == "__main__":  # pragma: no cover
    # Through the package name, not `__main__`: the sandbox imports the workflow class by its module,
    # and a `__main__` copy would be a second module whose `_AGENT` nobody set.
    from crashproof.adapters import temporal

    temporal.main()
