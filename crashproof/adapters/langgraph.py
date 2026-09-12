"""The LangGraph adapter (§13.4).

The same workload, the same World, the same shim, the same spec — expressed in LangGraph's
documented primitives and nothing else. The graph shape is fixed for every cell:

    agent node = one model call        one superstep, one checkpoint
    tool node  = one `@task` tool call  documented guidance: "wrap side effects in @task so their
                                        results are persisted and not re-run on resume"

Three configs, one axis: `durability ∈ {sync, async, exit}`. That is a documented LangGraph setting
and the only thing that differs between the three columns.

**`recovery_mechanism = harness`, and that is the finding, not a slight.** Nothing in LangGraph
notices that a worker died. The `thread_id` is persisted by the checkpointer but *restored by the
harness* reading it back out of the trial directory, which is the same fact said twice. So the
adapter is honest about it in the column header rather than quietly looking like an engine.

**No F1 row.** An F1 key must be a pure function of identifiers the framework itself persists and
restores across a restart. `thread_id` fails the second half, and a loop counter in graph state
would be a counter the adapter added. So LangGraph runs `key_source=none` — and against the
`natural: true` endpoint its IDEMPOTENT band is still measured honestly, because natural
idempotency is a property of the receiver, not of the caller.

**`exit` has no checkpoint at all**, so `ainvoke(None, …)` has nothing to resume: the adapter
re-submits the original input on the same thread. That is re-submission, not resumption, and the
asymmetry is itself the `exit` finding.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Annotated, Any, TypedDict

from crashproof.adapters.base import CanonicalResult, ConfigPin, Dependency, SutHandle
from crashproof.faults.injectors.shim import ToolShim
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import Schedule
from crashproof.workloads.spec import Workload, load_named
from crashproof.world.client import DEFAULT_TIMEOUT_S, WorldClient

ENV_WORLD = "CRASHPROOF_WORLD_URL"
ENV_DSN = "CRASHPROOF_LG_DSN"
ENV_WORKLOAD = "CRASHPROOF_WORKLOAD"
ENV_VARIANT = "CRASHPROOF_VARIANT"
ENV_DURABILITY = "CRASHPROOF_LG_DURABILITY"

MAX_TURNS = 6


class State(TypedDict, total=False):
    task: str
    tools_answered: list[str]
    results: dict[str, Any]
    answer: str
    pending: dict[str, Any] | None


# =============================================================================
# The workload, expressed as a graph
# =============================================================================
def build_graph(workload: Workload, variant: str, world: WorldClient, shim: ToolShim | None, saver: Any):
    from langgraph.func import task
    from langgraph.graph import END, START, StateGraph

    endpoints = {t.name: t.endpoint for t in workload.tools_for(variant)}

    @task
    async def call_tool(name: str, args: dict[str, Any]) -> Any:
        """Documented guidance: a side effect wrapped in `@task` has its result persisted and is
        not re-run on resume. No key is presented — LangGraph has none to give (§13.6)."""
        if shim is not None:
            return await shim.tool_call(name, endpoints[name], args)
        return await world.acall(endpoints[name], args)

    async def agent(state: State) -> dict[str, Any]:
        answered = list(state.get("tools_answered") or [])
        key = Workload.node_key(answered)
        node = workload.node_for(key)
        node_id = "-".join(f"{n}{i}" for n, i in key) or "start"

        def decide() -> dict[str, Any]:
            decision = Workload.decision_of(
                node, alternate=shim is not None and shim.alternate_armed
            )
            results = state.get("results") or {}
            calls = decision.get("tool_calls") or []
            if not calls:
                return {"answer": _resolve_text(str(decision.get("final", "")), results), "pending": None}
            call = calls[0]
            return {"pending": {"name": call["name"], "args": _resolve(call.get("args", {}), results)}}

        return (
            await shim.model_call(node_id, decide, prompt=dict(state))
            if shim is not None
            else decide()
        )

    async def tools(state: State) -> dict[str, Any]:
        pending = state["pending"]
        result = await call_tool(pending["name"], pending["args"])
        return {
            "tools_answered": [*(state.get("tools_answered") or []), pending["name"]],
            "results": {**(state.get("results") or {}), pending["name"]: result},
            "pending": None,
        }

    def route(state: State) -> str:
        if state.get("pending"):
            return "tools"
        return END

    graph = StateGraph(State)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=saver)


_INLINE = re.compile(r"@(\w+)\.result(?:\.(\w+))?")


def _resolve(args: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    return {k: _resolve_text(v, results) if isinstance(v, str) else v for k, v in args.items()}


def _resolve_text(text: str, results: dict[str, Any]) -> str:
    def swap(m: re.Match[str]) -> str:
        result = results.get(m.group(1)) or {}
        return str(result.get(m.group(2), "")) if m.group(2) else json.dumps(result, sort_keys=True)

    return _INLINE.sub(swap, text)


# =============================================================================
# The adapter
# =============================================================================
class LangGraphAdapter:
    _template_ready = False

    name = "langgraph"
    recovery_mechanism = "harness"
    key_sources = frozenset({"none"})
    workloads = frozenset({"tool_chain_1_effect"})
    workload_evidence = {
        "tool_chain_1_effect": (
            "graph API: agent node = one model call, tool node = one @task-wrapped tool call, one "
            "superstep each (docs: wrap side effects in @task so their results are persisted and "
            "not re-run on resume)"
        )
    }
    #: No documented exactly-once or key primitive anywhere in the fact sheet, so at-least-once is
    #: the honest declaration for every class. The raw duplicate counts say the rest.
    claims: dict[str, str] = {
        "PURE": "at_least_once",
        "IDEMPOTENT": "at_least_once",
        "EXTERNAL": "at_least_once",
    }

    def __init__(
        self, workload: Workload, variant: str, *, durability: str = "sync",
        template_db: str = "langgraph_template",
    ) -> None:
        self.workload = workload
        self.variant = variant
        self.durability = durability
        self.template_db = template_db
        self._admin_dsn: str | None = None
        self._db_name: str | None = None

    def config_pin(self, *, worker_count: int = 1, **extra: Any) -> ConfigPin:
        import importlib.metadata as md

        return ConfigPin(
            framework_versions={
                "langgraph": md.version("langgraph"),
                "langgraph-checkpoint-postgres": md.version("langgraph-checkpoint-postgres"),
                "python": sys.version.split()[0],
            },
            backend="AsyncPostgresSaver",
            durability=self.durability,
            retry="framework default",
            worker_count=worker_count,
            # LangGraph has no documented per-step timeout: a tool is a function, and what ends a
            # hung call is the client's socket timeout. That is a harness parameter, so it is
            # pinned and printed rather than left to be discovered in a latency column.
            extra={"world_client_timeout_s": DEFAULT_TIMEOUT_S, "step_timeout": "none documented", **extra},
        )

    def worker_count(self, spec: Any) -> int:
        """Always one. LangGraph has no successor by design: nothing but the supervisor re-invokes
        it, so a second process would have nothing to claim (§13.4)."""
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
        if LangGraphAdapter._template_ready:
            return
        from crashproof.runner import database
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        template_dsn = await database.ensure_template(admin_dsn, self.template_db)
        async with AsyncPostgresSaver.from_conn_string(template_dsn) as saver:
            await saver.setup()
        LangGraphAdapter._template_ready = True

    async def stop_dependency(self, handle: SutHandle) -> None:
        from crashproof.runner import database

        if self._admin_dsn and self._db_name:
            await database.drop(self._admin_dsn, self._db_name)

    # --- lifecycle -----------------------------------------------------------
    def worker_argv(self, handle: SutHandle) -> list[str]:
        return [sys.executable, "-m", "crashproof.adapters.langgraph"]

    def worker_env(self, handle: SutHandle) -> dict[str, str]:
        return {
            TrialDir.ENV: str(handle.trial_dir),
            ENV_WORLD: handle.world_url,
            ENV_DSN: handle.dependency.dsn or "",
            ENV_WORKLOAD: self.workload.workload,
            ENV_VARIANT: self.variant,
            ENV_DURABILITY: self.durability,
        }

    async def submit(self, handle: SutHandle) -> None:
        """Choose a thread id and write it where the harness can find it again. That write is
        `recovery_mechanism = harness` in one line: nothing in LangGraph will restore it."""
        thread_id = f"thread-{handle.trial_dir.name}"
        handle.run_ref = thread_id
        (handle.trial_dir / "sut" / "thread_id").write_text(thread_id, encoding="utf8")
        (handle.trial_dir / "sut" / "input.json").write_text(
            json.dumps({"task": "file an issue"}), encoding="utf8"
        )

    async def on_worker_restart(self, handle: SutHandle) -> None:
        """The re-invoke happens inside the restarted worker, which reads the thread id from the
        trial directory. Either way the id comes from the harness, never from the framework."""
        return None

    async def status(self, handle: SutHandle) -> str:
        done = handle.trial_dir / "sut" / "status"
        return done.read_text(encoding="utf8").strip() if done.exists() else "RUNNING"

    async def collect(self, handle: SutHandle) -> CanonicalResult:
        status_file = handle.trial_dir / "sut" / "status"
        answer_file = handle.trial_dir / "sut" / "answer.json"
        status = status_file.read_text(encoding="utf8").strip() if status_file.exists() else "UNKNOWN"
        answer = json.loads(answer_file.read_text(encoding="utf8")) if answer_file.exists() else None
        return CanonicalResult(
            status=status,  # type: ignore[arg-type]
            result=answer,
            # LangGraph's checkpoint store records channel values, not per-effect completion, and
            # reading one out would be the adapter inventing a committed set the framework does not
            # keep. So S2 and C3 are N/A here — named individually, and never a PASS for having
            # nothing to check.
            committed_effects=None,
            export=None,
            model_calls=None,
            tokens=None,
        )


def _db_name_for(trial_dir: Path) -> str:
    import hashlib

    tag = hashlib.sha256(str(trial_dir.resolve()).encode()).hexdigest()[:8]
    return "lg_" + re.sub(r"[^a-z0-9_]", "_", trial_dir.name.lower())[:40] + "_" + tag


# =============================================================================
# The worker process
# =============================================================================
def main() -> None:  # pragma: no cover - a subprocess in every trial
    from crashproof.runner import aio

    aio.run(_worker())


async def _worker() -> None:  # pragma: no cover - subprocess
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    trial = TrialDir.from_env()
    cursor = trial.read_cursor()
    workload = load_named(os.environ[ENV_WORKLOAD])
    variant = os.environ[ENV_VARIANT]
    durability = os.environ.get(ENV_DURABILITY, "sync")
    world = WorldClient(os.environ[ENV_WORLD])
    thread_id = (trial.path / "sut" / "thread_id").read_text(encoding="utf8").strip()

    shim = ToolShim(
        trial,
        Schedule.read(trial.schedule_path),
        trial_id=cursor.trial_id,
        recovery_index=cursor.recovery_index,
        world=world,
    )

    async with AsyncPostgresSaver.from_conn_string(os.environ[ENV_DSN]) as saver:
        graph = build_graph(workload, variant, world, shim, saver)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": MAX_TURNS * 3}

        # A restart resumes from the checkpoint — except under `exit`, where there is no checkpoint
        # to resume from and the only thing left is to run the workload again from the top. That is
        # re-submission, not resumption, and it is the `exit` finding rather than a workaround.
        resuming = cursor.recovery_index > 0 and durability != "exit"
        payload = None if resuming else json.loads(
            (trial.path / "sut" / "input.json").read_text(encoding="utf8")
        )
        state = await graph.ainvoke(payload, config=config, durability=durability)

    (trial.path / "sut" / "answer.json").write_text(
        json.dumps({"answer": state.get("answer")}), encoding="utf8"
    )
    (trial.path / "sut" / "status").write_text("COMPLETED", encoding="utf8")


if __name__ == "__main__":  # pragma: no cover
    main()
