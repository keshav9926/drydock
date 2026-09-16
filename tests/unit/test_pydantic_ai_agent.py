"""One Pydantic AI agent for every engine arm (§13.5).

"Different agent code" is only removed as a confound if every engine arm's agent answers the same
request with the same response. Both arms build it from `crashproof.adapters.pydantic_ai_agent`; this
pins that they still do — same parts, same args, same `tool_call_id`s — at a W1 node and at W5-pre's
node that fires `notify` ahead of the gated deploy, so a copy that drifts back into an adapter fails here.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic_ai")
pytest.importorskip("temporalio")
pytest.importorskip("dbos")

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart  # noqa: E402
from pydantic_ai.models import ModelRequestParameters  # noqa: E402

from crashproof.workloads.spec import load_named  # noqa: E402


def _history(task: str, answered: list[tuple[str, dict]]) -> list:
    """A request that has already had these tools called and answered, in order."""
    messages: list = [ModelRequest(parts=[UserPromptPart(task)])]
    for i, (name, result) in enumerate(answered):
        messages.append(ModelResponse(parts=[ToolCallPart(name, {}, tool_call_id=f"t{i}")]))
        messages.append(ModelRequest(parts=[ToolReturnPart(name, result, tool_call_id=f"t{i}")]))
    return messages


CASES = [
    ("tool_chain_1_effect", "IDEMPOTENT", []),
    ("tool_chain_1_effect", "IDEMPOTENT", [("search", {"hits": ["a"]})]),
    ("tool_chain_1_effect", "IDEMPOTENT", [("search", {"hits": ["a"]}), ("create_issue", {"id": "x1"})]),
    ("approval_gated_deploy_pre", "GATED", [("search", {"hits": ["a"]})]),
    ("approval_gated_deploy_pre", "GATED", [("search", {}), ("notify", {"id": "n"}), ("deploy_service", {"id": "d"})]),
]


@pytest.mark.parametrize("name,variant,answered", CASES)
async def test_the_temporal_and_dbos_agents_answer_a_history_identically(name, variant, answered) -> None:
    from dbos import DBOS

    from crashproof.adapters import dbos as dbos_arm
    from crashproof.adapters import temporal as temporal_arm

    workload = load_named(name)
    messages = _history(workload.input["task"], answered)
    try:
        DBOS.destroy(destroy_registry=True)
        agents = [temporal_arm.build_agent(workload, variant, None, None), dbos_arm.build_agent(workload, variant, None, None)]
        responses = [await a.model.request(messages, None, ModelRequestParameters()) for a in agents]
    finally:
        DBOS.destroy(destroy_registry=True)
    assert responses[0].parts, "a node with no answer is not a comparison"
    assert responses[0].parts == responses[1].parts
    if name == "approval_gated_deploy_pre" and len(answered) == 1:
        assert [p.tool_name for p in responses[0].parts] == ["notify", "deploy_service"]
