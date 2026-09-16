"""One Pydantic AI agent for every engine arm (§13.5).

"Different agent code" is only removed as a confound if every engine arm's agent answers the same
request with the same response. Every arm builds it from `crashproof.adapters.pydantic_ai_agent`; this
pins that they still do — same parts, same args, same `tool_call_id`s as the bare shared agent — at a
W1 node and at W5-pre's node that fires `notify` ahead of the gated deploy, so a copy that drifts back
into an adapter fails here. Each arm is checked where its extra is installed (Temporal and DBOS on
Windows and Linux, Restate on Linux only); CI installs all three.
"""

from __future__ import annotations

import importlib.util

import pytest

pytest.importorskip("pydantic_ai")

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart  # noqa: E402
from pydantic_ai.models import ModelRequestParameters  # noqa: E402
from pydantic_ai.models.wrapper import WrapperModel  # noqa: E402

from crashproof.adapters import pydantic_ai_agent  # noqa: E402
from crashproof.workloads.spec import load_named  # noqa: E402


def _history(task: str, answered: list[tuple[str, dict]]) -> list:
    """A request that has already had these tools called and answered, in order."""
    messages: list = [ModelRequest(parts=[UserPromptPart(task)])]
    for i, (name, result) in enumerate(answered):
        messages.append(ModelResponse(parts=[ToolCallPart(name, {}, tool_call_id=f"t{i}")]))
        messages.append(ModelRequest(parts=[ToolReturnPart(name, result, tool_call_id=f"t{i}")]))
    return messages


def _installed() -> list[str]:
    arms = {"temporal": ("temporalio",), "dbos": ("dbos",), "restate": ("restate", "hypercorn")}
    return [arm for arm, mods in arms.items() if all(importlib.util.find_spec(m) for m in mods)]


def _engine_agent(arm: str, workload, variant: str):
    module = importlib.import_module(f"crashproof.adapters.{arm}")
    return module.build_agent(workload, variant, None, None)


CASES = [
    ("tool_chain_1_effect", "IDEMPOTENT", []),
    ("tool_chain_1_effect", "IDEMPOTENT", [("search", {"hits": ["a"]})]),
    ("tool_chain_1_effect", "IDEMPOTENT", [("search", {"hits": ["a"]}), ("create_issue", {"id": "x1"})]),
    ("approval_gated_deploy_pre", "GATED", [("search", {"hits": ["a"]})]),
    ("approval_gated_deploy_pre", "GATED", [("search", {}), ("notify", {"id": "n"}), ("deploy_service", {"id": "d"})]),
]


@pytest.mark.parametrize("name,variant,answered", CASES)
async def test_every_engine_arm_answers_a_history_as_the_shared_agent_does(name, variant, answered) -> None:
    arms = _installed()
    if not arms:
        pytest.skip("no engine arm's extra is installed")
    workload = load_named(name)
    messages = _history(workload.input["task"], answered)
    bare = pydantic_ai_agent.build_agent(workload, variant, world=None, shim=None, key=str, durability=None)
    expected = await bare.model.request(messages, None, ModelRequestParameters())
    assert expected.parts, "a node with no answer is not a comparison"
    if name == "approval_gated_deploy_pre" and len(answered) == 1:
        assert [p.tool_name for p in expected.parts] == ["notify", "deploy_service"]

    destroy = None
    if "dbos" in arms:
        from dbos import DBOS

        destroy = lambda: DBOS.destroy(destroy_registry=True)  # noqa: E731
        destroy()
    try:
        for arm in arms:
            model = _engine_agent(arm, workload, variant).model
            # A wrapper integration (RestateAgent) puts its durable-step wrapper around the same model; the
            # wrapper records what the model answers, so the model is what is compared.
            if isinstance(model, WrapperModel):
                model = model.wrapped
            response = await model.request(messages, None, ModelRequestParameters())
            assert response.parts == expected.parts, arm
    finally:
        if destroy:
            destroy()
