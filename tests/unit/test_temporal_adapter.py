"""The Temporal arm's agent, without Temporal (§13.5).

`TemporalDurability` is transparent outside a workflow, so every workload the adapter declares can be
run end to end in-process against a recording World: the script picks each node from the tool
returns already in the request, the gated call ends the run asking for approval, and the documented
continuation (`message_history` + `deferred_tool_results`) finishes it. What a real server does to
that program under a kill is the bench's question; this is the check that the program is the
workload.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("temporalio")
pytest.importorskip("pydantic_ai")

from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults  # noqa: E402

from crashproof.adapters.temporal import TemporalAdapter, build_agent  # noqa: E402
from crashproof.workloads.spec import load_named  # noqa: E402


class RecordingWorld:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str | None]] = []

    async def acall(self, endpoint: str, args: dict, *, effect_key: str | None = None) -> dict:
        self.calls.append((endpoint, dict(args), effect_key))
        return {"id": f"id-{endpoint}", "external_ref": f"{endpoint}#1"}


@pytest.mark.parametrize("name", sorted(TemporalAdapter.workloads))
async def test_every_declared_workload_runs_as_its_script(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from temporalio import activity

    # The F1 key is read from `activity.info()` inside the tool body; in-process there is no activity,
    # so the documented fields are supplied and the formula is what is checked.
    monkeypatch.setattr(activity, "info", lambda: SimpleNamespace(workflow_run_id="run-1", activity_id="4"))
    workload = load_named(name)
    for variant in workload.variants:
        world = RecordingWorld()
        agent = build_agent(workload, variant, world, None)
        run = await agent.run(workload.input["task"])
        asked = 0
        if isinstance(run.output, DeferredToolRequests):
            asked = len(run.output.approvals)
            assert [c.tool_name for c in run.output.approvals] == list(workload.gated_tools())
            run = await agent.run(
                message_history=run.all_messages(),
                deferred_tool_results=DeferredToolResults(approvals={c.tool_call_id: True for c in run.output.approvals}),
            )
        endpoints = {t.name: t.endpoint for t in workload.tools_for(variant)}
        scripted = [endpoints[c["name"]] for node in workload.script for c in node.all_tool_calls()]
        # Each scripted call exactly once, in script order — `before_approval` included, and not
        # re-run by the continuation (the documented deferred-tools behaviour W5-pre measures).
        assert [c[0] for c in world.calls] == scripted
        assert asked == len(workload.gated_tools())
        assert re.fullmatch(workload.expected.result["matches"], run.output)
        framework = workload.variant(variant).key_source == "framework"
        classes = {t.endpoint: t.effect_class for t in workload.tools_for(variant)}
        assert [key for *_, key in world.calls] == [
            "run-1:4" if framework and classes[endpoint] == "IDEMPOTENT" else None for endpoint, *_ in world.calls
        ]


def test_the_worker_is_restarted_with_nothing_that_names_a_run(tmp_path) -> None:
    from crashproof.adapters.base import SutHandle

    adapter = TemporalAdapter(load_named("tool_chain_1_effect"), "EXTERNAL")
    handle = SutHandle(trial_dir=tmp_path, dependency=None, world_url="http://127.0.0.1:1")  # type: ignore[arg-type]
    assert adapter.worker_argv(handle) == adapter.worker_argv(handle)
    assert adapter.worker_argv(handle)[1:] == ["-m", "crashproof.adapters.temporal"]
    assert adapter.recovery_mechanism == "engine" and adapter.worker_count(None) == 1
    with pytest.raises(ValueError, match="V2"):
        TemporalAdapter(load_named("tool_chain_1_effect"), "EXTERNAL", agent_code="native")
