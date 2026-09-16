"""The ReAct workload as one Pydantic AI `Agent`, for every engine that runs Pydantic AI (§13.5).

§13.5's point is that "different agent code" stops being a confound between engine cells, and that is
only true if the agent is literally the same code. So it lives here, once, and an engine arm supplies
exactly the three things that differ between engines and nothing else:

    key()       the F1 key, read from inside the durable unit a tool body runs in
                (Temporal: `{workflow_run_id}:{activity_id}`; DBOS: `{workflow_id}:{step_id}`)
    wrap(fn, d) whatever the engine documents a function tool needs to be durable — DBOS's
                `@DBOS.step`; identity for Temporal, whose capability makes tool calls activities
    durability  the engine's capability (`TemporalDurability`, `DBOSDurability`, ...)

The model is the workload script as a `FunctionModel`: a node is selected by the ordered tool returns
already in the request (§13.2) — never a counter, never result content — and `tool_call_id` is a
function of that key. A gated tool is `requires_approval`, so the run ends in `DeferredToolRequests`
where every other arm parks, and `run_agent` resumes it with Pydantic AI's documented continuation
once the engine's own wait says so.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, FunctionToolset, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from crashproof.adapters.langgraph import _resolve, _resolve_text
from crashproof.faults.injectors.shim import ToolShim
from crashproof.workloads.spec import Workload
from crashproof.world.client import WorldClient

#: Durable names derive from these (Temporal activity names, DBOS step names): stable by rule.
AGENT_NAME = "crashproof"
TOOLSET_ID = "world"


def build_agent(
    workload: Workload,
    variant: str,
    *,
    world: WorldClient | None,
    shim: ToolShim | None,
    key: Callable[[], str],
    durability: Any,
    wrap: Callable[[Callable[..., Any], Any], Callable[..., Any]] = lambda fn, decl: fn,
) -> Agent:
    key_source = workload.variant(variant).key_source
    gated = set(workload.gated_tools())

    def make_tool(decl: Any) -> Tool:
        sends_key = key_source == "framework" and decl.effect_class in ("IDEMPOTENT", "TRANSACTIONAL")

        async def call(**args: Any) -> Any:
            effect_key = key() if sends_key else None
            if shim is not None:
                return await shim.tool_call(decl.name, decl.endpoint, args, effect_key=effect_key)
            assert world is not None, "an agent built without a World (a Replayer's) never executes a tool"
            return await world.acall(decl.endpoint, args, effect_key=effect_key)

        tool = Tool.from_schema(
            wrap(call, decl),
            name=decl.name,
            description=decl.name,
            json_schema={"type": "object", "additionalProperties": True},
        )
        # Documented human-in-the-loop: a tool that "requires human-in-the-loop approval" ends the run
        # with `DeferredToolRequests`. Which tools are gated is the workload's, not the arm's.
        tool.requires_approval = decl.name in gated
        return tool

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = [p for m in messages if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, ToolReturnPart)]
        results = {p.tool_name: p.content for p in returns}
        node_key = Workload.node_key([p.tool_name for p in returns])
        node = workload.node_for(node_key)
        node_id = "-".join(f"{n}{i}" for n, i in node_key) or "start"

        def decide() -> ModelResponse:
            decision = Workload.decision_of(node, alternate=shim is not None and shim.alternate_armed)
            # The pre-approval calls and the gated call travel in one response, as one model turn: the
            # framework runs the ungated ones and defers the gated one (W5-pre).
            calls = [*(decision.get("before_approval") or []), *(decision.get("tool_calls") or [])]
            if not calls:
                return ModelResponse(parts=[TextPart(_resolve_text(str(decision.get("final", "")), results))])
            return ModelResponse(
                parts=[
                    ToolCallPart(c["name"], _resolve(c.get("args", {}), results), tool_call_id=f"{node_id}:{i}")
                    for i, c in enumerate(calls)
                ]
            )

        if shim is None:
            return decide()
        prompt = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
        return await shim.model_call(node_id, decide, prompt=prompt)

    return Agent(
        FunctionModel(respond, model_name="scripted"),
        name=AGENT_NAME,
        output_type=[str, DeferredToolRequests],
        toolsets=[FunctionToolset([make_tool(d) for d in workload.tools_for(variant)], id=TOOLSET_ID)],
        capabilities=[durability],
    )


async def run_agent(agent: Agent, task: dict[str, Any], wait: Callable[[], Awaitable[str]]) -> dict[str, Any]:
    """The workflow body every engine runs: `agent.run()`, and while it ends asking for approval, the
    engine's `wait()` for a verdict, then `message_history` + `deferred_tool_results` — Pydantic AI's
    documented continuation, which does not re-run a call that already has a return in the history."""
    result = await agent.run(str(task.get("task", "")))
    while isinstance(result.output, DeferredToolRequests):
        verdict = await wait()
        if verdict != "granted":
            return {"answer": f"not done: approval {verdict}"}
        result = await agent.run(
            message_history=result.all_messages(),
            deferred_tool_results=DeferredToolResults(approvals={c.tool_call_id: True for c in result.output.approvals}),
        )
    return {"answer": result.output}
