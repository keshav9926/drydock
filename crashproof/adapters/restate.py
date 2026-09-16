"""The Restate adapter, `agent_code = pydantic_ai` (§13.4, §13.5, §22.3).

The canonical ReAct workload is the one Pydantic AI agent every engine arm runs
(`pydantic_ai_agent`), wrapped in `RestateAgent` — which is **a wrapper in Restate's SDK
(`restate.ext.pydantic`), not a pydantic-ai capability** (§13.5), so every Restate cell carries that
caveat. `RestateAgent` makes each model request a `ctx.run` ("every LLM response is saved in the
Restate Server and replayed during recovery"); each function tool does its work inside
`restate_context().run_typed(...)`, the documented form ("Use `restate_context()` actions inside tools
to make their execution durable"). The workflow body is `agent.run()` and the approval wait.

**`recovery_mechanism = engine`.** One `restate-server` per trial — a single binary with a fresh
`RESTATE_BASE_DIR` in the trial directory, never killed, wiped at teardown — pushes the invocation to
the SUT: an ASGI app served by hypercorn on a port fixed for the trial, registered once. The worker
is the ASGI process and nothing else; the harness kills it and restarts it with the same argv and
env. Restate sees a kill as connection loss and re-invokes with the journal attached; it sees a
freeze only when the inactivity timeout (2 s) and then the abort timeout (5 s) expire. The restarted
worker is told nothing: `on_worker_restart` is a no-op.

**The invocation is started once, by the adapter, at `submit`** — `POST /deployments` then
`POST /crashproof/<key>/run/send` on the ingress — so the worker never starts, names or nudges
anything, and its argv is `python -m crashproof.adapters.restate` on every spawn.

**F1.** `str(ctx.uuid())`, drawn in handler code immediately before the tool's `run_typed` and handed
into the run. Restate docs: "To generate stable UUIDs for things like idempotency keys: `my_uuid =
ctx.uuid()`" — helpers "seeded by the invocation ID — so they return the same result on retries".
SDK 1.0.5: `UUID(int=self.random_instance.getrandbits(128), version=4)` over `Random(invocation.random_seed)`,
so it is a function of the invocation and of how many draws the handler made before this one — which
is why it is drawn outside the run ("inside `ctx.run`, you cannot use the Restate context"), where
replay repeats every draw. Sent only when the variant's `key_source` is `framework`.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from typing import Any

import restate
from restate.ext.pydantic import RestateAgent, restate_context

from crashproof.adapters import pydantic_ai_agent
from crashproof.adapters.base import CanonicalResult, ConfigPin, Dependency, SutHandle
from crashproof.faults import process
from crashproof.faults.injectors.shim import ToolShim
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import Schedule
from crashproof.workloads.spec import Workload, load_named
from crashproof.world.client import DEFAULT_TIMEOUT_S, WorldClient

ENV_WORLD = "CRASHPROOF_WORLD_URL"
ENV_WORKLOAD = "CRASHPROOF_WORKLOAD"
ENV_VARIANT = "CRASHPROOF_VARIANT"
ENV_SDK_PORT = "CRASHPROOF_RESTATE_SDK_PORT"
ENV_BIN = "CRASHPROOF_RESTATE_BIN"
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# --- pins from §13.4 ---------------------------------------------------------------------------------
#: "The maximum time Restate waits for new journal entries from a service before Restate considers it
#: stalled. After this timeout, Restate will ask the service to suspend." (services/configuration)
INACTIVITY_S = 2.0
#: "Once the inactivity timeout is reached, Restate will wait for the abort timeout before interrupting
#: the user code." A frozen worker cannot suspend, so it is abandoned only when both have run out:
#: detection of a freeze is inactivity + abort = 7 s, and §13.4's pause is drawn over that.
ABORT_S = 5.0
#: Restate's documented default policy, spelled out so the row prints it rather than implying it
#: (services/configuration, "Default"). 70 attempts at a 60 s cap outlast any 60 s trial many times
#: over, so the invocation cannot pause before `max_recoveries` (§13.4).
RETRY_POLICY = restate.InvocationRetryPolicy(
    initial_interval=timedelta(milliseconds=50),
    exponentiation_factor=2.0,
    max_interval=timedelta(seconds=60),
    max_attempts=70,
    on_max_attempts="pause",
)
#: Collection reads the journal after the run completes; the documented default is 24 h, spelled out.
JOURNAL_RETENTION = timedelta(days=1)
WORKFLOW = "crashproof"
#: Server settings that change no semantics. Partitions and RocksDB memory are the values the SDK's
#: own test harness runs the server with (`restate.harness.RestateContainer`, 1.0.5); TCP only because
#: the harness addresses the server by port, and the default `all` also binds unix sockets in the data dir.
SERVER_ENV = {
    "RESTATE_LISTEN_MODE": "tcp",
    "RESTATE_DISABLE_TELEMETRY": "true",
    "RESTATE_BOOTSTRAP_NUM_PARTITIONS": "1",
    "RESTATE_DEFAULT_NUM_PARTITIONS": "1",
    "RESTATE_ROCKSDB_TOTAL_MEMORY_SIZE": "32 MB",
}
APPROVAL_RUN = "request approval"


# =============================================================================
# The workload: the shared Pydantic AI agent, wrapped the way Restate documents
# =============================================================================
#: The key a tool's run was entered with. Set inside the run from the value drawn outside it.
_EFFECT_KEY: contextvars.ContextVar[str] = contextvars.ContextVar("crashproof_restate_effect_key")


def _durable_tool(fn: Any, decl: Any) -> Any:
    """A function tool as Restate's Pydantic AI docs write one: the work inside
    `restate_context().run_typed(name, action)`, the idempotency key drawn with `ctx.uuid()` in handler
    code before it."""

    async def tool(**args: Any) -> Any:
        ctx = restate_context()
        key = str(ctx.uuid())

        async def action() -> Any:
            _EFFECT_KEY.set(key)
            return await fn(**args)

        return await ctx.run_typed(decl.name, action)

    return tool


def build_agent(workload: Workload, variant: str, world: WorldClient | None, shim: ToolShim | None) -> RestateAgent:
    """`pydantic_ai_agent.build_agent` with Restate's key and tool wrapping and no capability, wrapped in
    `RestateAgent`, which makes every model request a `ctx.run`."""
    agent = pydantic_ai_agent.build_agent(
        workload, variant, world=world, shim=shim, key=_EFFECT_KEY.get, wrap=_durable_tool, durability=None
    )
    return RestateAgent(agent)


def build_workflow(workload: Workload, variant: str, world: WorldClient, shim: ToolShim | None, sut_dir: Path) -> restate.Workflow:
    agent = build_agent(workload, variant, world, shim)
    workflow = restate.Workflow(
        WORKFLOW,
        inactivity_timeout=timedelta(seconds=INACTIVITY_S),
        abort_timeout=timedelta(seconds=ABORT_S),
        journal_retention=JOURNAL_RETENTION,
        invocation_retry_policy=RETRY_POLICY,
    )

    @workflow.main()
    async def run(ctx: restate.WorkflowContext, task: dict) -> dict:
        return await pydantic_ai_agent.run_agent(agent, task, lambda: _wait_for_human(ctx, task, sut_dir))

    return workflow


async def _wait_for_human(ctx: restate.WorkflowContext, task: dict[str, Any], sut_dir: Path) -> str:
    """Restate's documented human-in-the-loop, and nothing else: an awakeable, its id handed to the
    reviewer inside a `run` (docs: `id, promise = ctx.awakeable(...)`, `await ctx.run_typed("trigger
    task", request_human_review, ...)`), raced against a durable timer for the run input's `expires_in`
    ("combine the primitive with a durable timer to implement a timeout")."""
    awakeable_id, decision = ctx.awakeable(type_hint=dict)
    await ctx.run_typed(APPROVAL_RUN, _hand_to_reviewer, sut_dir=str(sut_dir), awakeable_id=awakeable_id)
    expiry = ctx.sleep(timedelta(seconds=float(task.get("expires_in", 5))), name="approval expires_in")
    match await restate.select(decision=decision, expired=expiry):
        case ["decision", value]:
            return str((value or {}).get("decision"))
        case _:
            return "expired"


def _hand_to_reviewer(sut_dir: str, awakeable_id: str) -> None:
    """Where the human finds the id: a file the harness reads (§11.4). Journaled as a run, so a replay
    does not repeat it and a re-execution writes the same id."""
    Path(sut_dir, "awakeable").write_text(awakeable_id, encoding="utf8")


# =============================================================================
# The adapter
# =============================================================================
class RestateAdapter:
    name = "restate"
    recovery_mechanism = "engine"
    key_sources = frozenset({"none", "framework"})
    workloads = frozenset({"tool_chain_1_effect", "approval_gated_deploy", "approval_gated_deploy_pre"})
    workload_evidence = {
        "tool_chain_1_effect": (
            "Pydantic AI + RestateAgent (restate.ext.pydantic, restate-sdk 1.0.5): 'Wrap your agent with "
            "RestateAgent so every LLM response is saved in the Restate Server'; tools: 'Use "
            "restate_context().run_typed() inside tools to make steps durable' (docs.restate.dev/ai/patterns/"
            "durable-agents; pydantic.dev/docs/ai/integrations/durable_execution/restate)"
        ),
        "approval_gated_deploy": (
            "deferred tools: requires_approval=True ends the run with DeferredToolRequests; continued with "
            "message_history + deferred_tool_results. The wait is ctx.awakeable + run_typed handing the id to "
            "the reviewer + restate.select against ctx.sleep(expires_in); resolved with POST "
            "/restate/awakeables/{id}/resolve (docs.restate.dev/develop/python/external-events, durable-timers)"
        ),
        "approval_gated_deploy_pre": (
            "as approval_gated_deploy, with the `before_approval` call in the same model response as the gated "
            "one: it runs as its own ctx.run before the run ends asking for approval"
        ),
    }
    #: What the documentation says, judged as written (§7, §13.3 Jepsen rule): "Tool side effects are not
    #: duplicated (no double bookings, no duplicate emails)" (docs.restate.dev/ai/patterns/durable-agents,
    #: "How durable execution works"); "Use restate_context() actions inside tools to make their execution
    #: durable. The result is persisted and retried until it succeeds. Side effects won't be duplicated on
    #: recovery." (pydantic.dev/docs/ai/integrations/durable_execution/restate). No class is exempted.
    claims: dict[str, str] = {
        "PURE": "exactly_once",
        "IDEMPOTENT": "exactly_once",
        "EXTERNAL": "exactly_once",
    }
    _versions: dict[str, str] | None = None

    def __init__(self, workload: Workload, variant: str, *, agent_code: str = "pydantic_ai") -> None:
        if agent_code != "pydantic_ai":
            raise ValueError("Restate is staged through RestateAgent only (§13.5, §22.3); agent_code must be pydantic_ai")
        self.workload = workload
        self.variant = variant
        self._server: subprocess.Popen | None = None
        self._ingress: str | None = None
        self._admin: str | None = None
        self._sdk_port: int | None = None

    # --- declarations --------------------------------------------------------
    def config_pin(self, *, worker_count: int = 1, **extra: Any) -> ConfigPin:
        return ConfigPin(
            framework_versions=self.versions(),
            backend="restate-server single binary, fresh RESTATE_BASE_DIR per trial, wiped at teardown",
            durability="invocation journal; agent_code=pydantic_ai (RestateAgent wrapper, not a capability)",
            # Detection of a frozen worker is inactivity + abort (§13.4), so the pause is drawn over it.
            detection_timeout_s=INACTIVITY_S + ABORT_S,
            retry=(
                "InvocationRetryPolicy(initial_interval=50ms, exponentiation_factor=2.0, max_interval=60s, "
                "max_attempts=70, on_max_attempts=pause); ctx.run with default RunOptions (the invocation policy)"
            ),
            worker_count=worker_count,
            extra={
                # Every other arm's rows come from Windows; this one's cannot (no Windows wheel).
                "platform": platform_label(),
                "inactivity_timeout_s": INACTIVITY_S,
                "abort_timeout_s": ABORT_S,
                "journal_retention": "1d",
                "server_env": dict(SERVER_ENV),
                "asgi": "hypercorn.asyncio.serve in the worker process, 127.0.0.1:<port fixed per trial>",
                "tools": "restate_context().run_typed per call (RestateAgent auto_wrap_tools=False)",
                "approval_wait": "ctx.awakeable + restate.select(ctx.sleep(expires_in))",
                "client_retries": "none (FunctionModel has no provider client; the World client does not retry)",
                "world_client_timeout_s": DEFAULT_TIMEOUT_S,
                **extra,
            },
        )

    @classmethod
    def versions(cls) -> dict[str, str]:
        if cls._versions is None:
            import importlib.metadata as md

            server = subprocess.run([restate_bin(), "--version"], capture_output=True, text=True, check=False)
            cls._versions = {
                "restate-sdk": md.version("restate-sdk"),
                "pydantic-ai-slim": md.version("pydantic-ai-slim"),
                "hypercorn": md.version("hypercorn"),
                "restate-server": server.stdout.strip(),
                "python": sys.version.split()[0],
            }
        return cls._versions

    def worker_count(self, spec: Any) -> int:
        """One: the server is the successor (§13.4)."""
        return 1

    # --- dependency ----------------------------------------------------------
    async def start_dependency(self, handle: SutHandle) -> Dependency:
        """`restate-server` with its data dir in the trial directory, on free ports (§22.3). Never killed
        during the trial; only the worker is."""
        sut = handle.trial_dir / "sut"
        fabric, ingress, admin, self._sdk_port = _free_ports(4)
        env = {
            **os.environ,
            **SERVER_ENV,
            "RESTATE_BASE_DIR": str(sut / "restate-data"),
            "RESTATE_BIND_ADDRESS": f"127.0.0.1:{fabric}",
            "RESTATE_ADVERTISED_ADDRESS": f"http://127.0.0.1:{fabric}",
            "RESTATE_INGRESS__BIND_ADDRESS": f"127.0.0.1:{ingress}",
            "RESTATE_ADMIN__BIND_ADDRESS": f"127.0.0.1:{admin}",
        }
        log = (sut / "restate-server.log").open("w", encoding="utf8", errors="replace")
        self._server = subprocess.Popen([restate_bin(), "--no-logo"], env=env, stdout=log, stderr=subprocess.STDOUT)
        log.close()
        self._ingress, self._admin = f"http://127.0.0.1:{ingress}", f"http://127.0.0.1:{admin}"
        deadline = time.monotonic() + 60
        while not (await _healthy(f"{self._admin}/health") and await _healthy(f"{self._ingress}/restate/health")):
            if self._server.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"restate-server did not come up; see {sut / 'restate-server.log'}")
            await asyncio.sleep(0.1)
        return Dependency(name="restate", dsn=self._ingress, env={ENV_SDK_PORT: str(self._sdk_port)}, teardown=self._server)

    async def stop_dependency(self, handle: SutHandle) -> None:
        if self._server is not None and self._server.poll() is None:
            process.kill(self._server.pid)
            self._server.wait(timeout=30)
        self._server = None
        shutil.rmtree(handle.trial_dir / "sut" / "restate-data", ignore_errors=True)  # §22.3: wipe data dir

    # --- lifecycle -----------------------------------------------------------
    def worker_argv(self, handle: SutHandle) -> list[str]:
        return [sys.executable, "-m", "crashproof.adapters.restate"]

    def worker_env(self, handle: SutHandle) -> dict[str, str]:
        return {
            TrialDir.ENV: str(handle.trial_dir),
            ENV_WORLD: handle.world_url,
            ENV_SDK_PORT: str(self._sdk_port),
            ENV_WORKLOAD: self.workload.workload,
            ENV_VARIANT: self.variant,
        }

    async def submit(self, handle: SutHandle) -> None:
        """Register the worker's endpoint once, then start the workflow once. The workflow key is the
        trial directory's name (each trial has its own server); the invocation id Restate answers with is
        kept by the harness and never given to a worker."""
        uri = f"http://127.0.0.1:{self._sdk_port}"
        deadline = time.monotonic() + 60
        while True:  # the worker was spawned an instant ago; registration needs it listening
            if await asyncio.to_thread(_listening, self._sdk_port):
                code, body = await _http("POST", f"{self._admin}/deployments", {"uri": uri})
                if 200 <= code < 300:
                    break
            if time.monotonic() > deadline:
                raise RuntimeError(f"could not register {uri} with restate-server")
            await asyncio.sleep(0.2)
        key = f"crashproof-{handle.trial_dir.name}"
        code, body = await _http("POST", f"{self._ingress}/{WORKFLOW}/{key}/run/send", self.workload.input)
        if not (200 <= code < 300 and isinstance(body, dict) and body.get("invocationId")):
            raise RuntimeError(f"starting the workflow: HTTP {code} {body}")
        handle.run_ref = body["invocationId"]
        (handle.trial_dir / "sut" / "invocation_id").write_text(handle.run_ref, encoding="utf8")

    async def on_worker_restart(self, handle: SutHandle) -> None:
        """A no-op, and that is the finding: the server re-invokes the endpoint it registered."""
        return None

    async def status(self, handle: SutHandle) -> str:
        """`sys_invocation.status` through the admin SQL API — no worker involved. `suspended` is
        "waiting on some external input (e.g. request-response call, awakeable, sleep, ...)", and the only
        thing this workflow ever waits on is the approval. Over a bidirectional stream the idle handler is
        asked to suspend when the inactivity timeout runs out, so WAITING shows 2 s after the park."""
        if handle.run_ref is None or self._admin is None:
            return "UNKNOWN"
        rows = await self._query(f"select status, completion_result from sys_invocation where id = '{handle.run_ref}'")
        return invocation_status(rows[0] if rows else None)

    async def approve(self, handle: SutHandle, *, by: str = "harness", decision: str = "approve") -> bool:
        """The harness plays the human: `POST /restate/awakeables/{id}/resolve`, the documented external
        resolution. §11.4 C's second click is the same request again. Every response is kept in
        `sut/clicks.jsonl`, because what Restate answers to the second one is the finding."""
        marker = handle.trial_dir / "sut" / "awakeable"
        if not marker.exists():
            return False
        awakeable_id = marker.read_text(encoding="utf8").strip()
        verdict = "granted" if decision == "approve" else "rejected"
        code, body = await _http("POST", f"{self._ingress}/restate/awakeables/{awakeable_id}/resolve", {"decision": verdict, "by": by})
        with (handle.trial_dir / "sut" / "clicks.jsonl").open("a", encoding="utf8") as f:
            f.write(json.dumps({"at": time.time(), "awakeable": awakeable_id, "http": code, "body": body}) + "\n")
        return 200 <= code < 300

    async def collect(self, handle: SutHandle) -> CanonicalResult:
        status = await self.status(handle)
        inv = handle.run_ref
        answer = None
        if status == "COMPLETED":
            _, answer = await _http("GET", f"{self._ingress}/restate/output/{inv}")
        journal = await self._query(
            "select index, entry_type, name, completed, entry_json, appended_at "
            f"from sys_journal where id = '{inv}' order by index"
        )
        events = await self._query(
            "select after_journal_entry_index, appended_at, event_type, event_json "
            f"from sys_journal_events where id = '{inv}' order by appended_at"
        )
        invocation = await self._query(f"select * from sys_invocation where id = '{inv}'")
        committed, recoveries = read_journal(journal, events, self.workload, self.variant)
        clicks = handle.trial_dir / "sut" / "clicks.jsonl"
        export = handle.trial_dir / "sut" / "journal.json"
        export.write_text(
            json.dumps(
                {
                    "invocation_id": inv,
                    "committed": sorted(committed),
                    "invocation": invocation[0] if invocation else None,
                    "journal": journal,
                    "journal_events": events,
                    "clicks": [json.loads(line) for line in clicks.read_text(encoding="utf8").splitlines()] if clicks.exists() else [],
                },
                indent=1,
                default=str,
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

    async def _query(self, sql: str) -> list[dict[str, Any]]:
        code, body = await _http("POST", f"{self._admin}/query", {"query": sql})
        if code != 200 or not isinstance(body, dict):
            raise RuntimeError(f"admin /query: HTTP {code} {body}")
        return body.get("rows", [])


def invocation_status(row: dict[str, Any] | None) -> str:
    """`sys_invocation` → the neutral status of §13.3. `paused` is what the documented retry policy does
    when its attempts are exhausted ("requiring the user to manually resume it"): nothing in the trial
    will, so it reads as FAILED — unreachable while the policy outlasts the trial."""
    if row is None:
        return "UNKNOWN"
    status = row.get("status")
    if status == "completed":
        return "COMPLETED" if row.get("completion_result") == "success" else "FAILED"
    if status == "paused":
        return "FAILED"
    if status == "suspended":
        return "WAITING"
    return "RUNNING"


def read_journal(
    journal: list[dict[str, Any]], events: list[dict[str, Any]], workload: Workload, variant: str
) -> tuple[set[str], list[dict[str, Any]]]:
    """What Restate durably recorded, read from its own journal and nothing else.

    `committed`: the World label (`external_ref`) in the result of every `Notification: Run` whose
    `Command: Run` (joined on `completion_id`) is named after a non-PURE tool — the completion is the
    engine's record that the run's result was journaled. `recoveries`: the journal events, verbatim."""
    classes = {t.name: t.effect_class for t in workload.tools_for(variant)}
    names: dict[int, str] = {}
    committed: set[str] = set()
    for row in journal:
        entry = json.loads(row.get("entry_json") or "{}")
        run = entry.get("Command", {}).get("Run")
        if run is not None:
            names[run["completion_id"]] = run.get("name", "")
            continue
        done = entry.get("Notification", {}).get("Completion", {}).get("Run")
        if done is None or classes.get(names.get(done["completion_id"], ""), "PURE") == "PURE":
            continue
        value = _decode(done.get("result", {}).get("Success"))
        if isinstance(value, dict) and value.get("external_ref"):
            committed.add(value["external_ref"])
    recoveries = [
        {"type": e.get("event_type"), "after_entry": e.get("after_journal_entry_index"), "at": e.get("appended_at"),
         "event": _decode_json(e.get("event_json"))}
        for e in events
    ]
    return committed, recoveries


def _decode(payload: list[int] | None) -> Any:
    """A journaled value is the serde's bytes, which the SQL API prints as a list of ints."""
    return None if payload is None else _decode_json(bytes(payload).decode("utf8", errors="replace"))


def _decode_json(text: str | None) -> Any:
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def platform_label() -> str:
    """`linux (WSL2)` under WSL, whose kernel release names Microsoft; the bare `sys.platform` elsewhere."""
    import platform

    return f"{sys.platform} (WSL2)" if "microsoft" in platform.uname().release.lower() else sys.platform


def restate_bin() -> str:
    """`$CRASHPROOF_RESTATE_BIN`, then `restate-server` on PATH, then `~/.restate-bin/restate-server`."""
    found = os.environ.get(ENV_BIN) or shutil.which("restate-server")
    return found or str(Path.home() / ".restate-bin" / "restate-server")


# --- plumbing ------------------------------------------------------------------------------------------
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback only, never a proxy


def _request(method: str, url: str, body: Any = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method=method, headers={"content-type": "application/json", "accept": "application/json"}
    )
    try:
        with _OPENER.open(req, timeout=10) as resp:
            code, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        code, raw = exc.code, exc.read()
    except OSError as exc:
        return 0, str(exc)
    try:
        return code, json.loads(raw) if raw else None
    except ValueError:
        return code, raw.decode(errors="replace")


async def _http(method: str, url: str, body: Any = None) -> tuple[int, Any]:
    return await asyncio.to_thread(_request, method, url, body)


async def _healthy(url: str) -> bool:
    code, _ = await _http("GET", url)
    return code == 200


def _listening(port: int | None) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port or 0), timeout=0.5):
            return True
    except OSError:
        return False


def _free_ports(n: int) -> list[int]:
    """Held open together, so the n ports are distinct."""
    socks = [socket.socket() for _ in range(n)]
    try:
        for s in socks:
            s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in socks]
    finally:
        for s in socks:
            s.close()


def _sut_ref() -> dict[str, Any]:
    """§11.7's Restate `sut_ref`, from inside whichever invocation the boundary fired in."""
    from restate.extensions import current_context

    ctx = current_context()
    return {"invocation_id": ctx.request().id} if ctx is not None else {}


# =============================================================================
# The worker process — the ASGI app, restarted verbatim, told nothing
# =============================================================================
def main() -> None:  # pragma: no cover - a subprocess in every trial
    asyncio.run(_worker())


async def _worker() -> None:  # pragma: no cover - subprocess
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

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
    workflow = build_workflow(workload, os.environ[ENV_VARIANT], world, shim, trial.path / "sut")
    config = Config()  # as pydantic.dev's Restate page serves it: a Config with a bind, nothing else
    config.bind = [f"127.0.0.1:{os.environ[ENV_SDK_PORT]}"]
    await serve(restate.app([workflow]), config)


if __name__ == "__main__":  # pragma: no cover
    main()
