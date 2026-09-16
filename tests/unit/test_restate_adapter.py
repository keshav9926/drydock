"""The Restate arm without a server (§13.4, §13.5).

`RestateAgent` needs a Restate context for every model request and every tool run, so the agent is run
in-process against the smallest stand-in for one: `run_typed` executes its action, and `uuid` draws
from a `Random` seeded the way the SDK seeds its own (`Random(invocation.random_seed)`). That checks
the program is the workload, that each tool's work runs inside a run named after the tool, and that the
F1 key is drawn in handler code, outside the run, as Restate documents. What a real server does to that
program under a kill is the bench's question. The journal parser is checked on a journal recorded from
a real `kill@after:tool_effect` trial (restate-server 1.7.10).
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path
from random import Random
from uuid import UUID

import pytest

pytest.importorskip("restate")
pytest.importorskip("pydantic_ai")
pytest.importorskip("hypercorn")

from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults  # noqa: E402
from restate.server_context import _restate_context_var  # noqa: E402

from crashproof.adapters.base import SutHandle  # noqa: E402
from crashproof.adapters.restate import RestateAdapter, build_agent, invocation_status, read_journal  # noqa: E402
from crashproof.workloads.spec import load_named  # noqa: E402

JOURNAL = Path(__file__).parents[1] / "journals" / "restate_kill_after_tool_effect.json"


class RecordingWorld:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str | None]] = []

    async def acall(self, endpoint: str, args: dict, *, effect_key: str | None = None) -> dict:
        self.calls.append((endpoint, dict(args), effect_key))
        return {"id": f"id-{endpoint}", "external_ref": f"{endpoint}#1"}


class Context:
    """`run_typed` and `uuid`, with their documented meaning and no journal behind them."""

    def __init__(self, seed: int) -> None:
        self.random = Random(seed)
        self.runs: list[str] = []
        self.inside_run = False
        self.draws_inside_a_run = 0

    def uuid(self) -> UUID:
        self.draws_inside_a_run += self.inside_run
        return UUID(int=self.random.getrandbits(128), version=4)

    async def run_typed(self, name, action, options=None, /, *args, **kwargs):
        self.runs.append(name)
        self.inside_run = True
        try:
            result = action(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result
        finally:
            self.inside_run = False


@pytest.mark.parametrize("name", sorted(RestateAdapter.workloads))
async def test_every_declared_workload_runs_as_its_script(name: str) -> None:
    workload = load_named(name)
    for variant in workload.variants:
        world, ctx = RecordingWorld(), Context(seed=7)
        token = _restate_context_var.set(ctx)
        try:
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
        finally:
            _restate_context_var.reset(token)
        endpoints = {t.name: t.endpoint for t in workload.tools_for(variant)}
        scripted = [c["name"] for node in workload.script for c in node.all_tool_calls()]
        # Each scripted call exactly once, in order, each inside a run named after its tool; the
        # continuation does not re-run a call that already has a return.
        assert [c[0] for c in world.calls] == [endpoints[n] for n in scripted]
        assert [r for r in ctx.runs if r != "Model call"] == scripted
        assert ctx.runs.count("Model call") == len(workload.script)
        assert asked == len(workload.gated_tools())
        assert re.fullmatch(workload.expected.result["matches"], run.output)
        # F1: one `ctx.uuid()` per tool call, drawn before its run and never inside one.
        assert ctx.draws_inside_a_run == 0
        replay = Random(7)
        draws = [str(UUID(int=replay.getrandbits(128), version=4)) for _ in scripted]
        framework = workload.variant(variant).key_source == "framework"
        classes = {t.name: t.effect_class for t in workload.tools_for(variant)}
        assert [key for *_, key in world.calls] == [
            draw if framework and classes[tool] == "IDEMPOTENT" else None for tool, draw in zip(scripted, draws)
        ]


def test_the_worker_is_restarted_with_nothing_that_names_a_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(RestateAdapter, "_versions", {"restate-server": "restate-server 1.7.10"})
    adapter = RestateAdapter(load_named("tool_chain_1_effect"), "EXTERNAL")
    handle = SutHandle(trial_dir=tmp_path, dependency=None, world_url="http://127.0.0.1:1")  # type: ignore[arg-type]
    assert adapter.worker_argv(handle) == [sys.executable, "-m", "crashproof.adapters.restate"]
    assert "invocation" not in json.dumps(adapter.worker_env(handle))
    assert adapter.recovery_mechanism == "engine" and adapter.worker_count(None) == 1
    assert adapter.workloads == set(adapter.workload_evidence)
    assert set(adapter.claims) == {"PURE", "IDEMPOTENT", "EXTERNAL"}
    pin = adapter.config_pin().as_dict()
    # A freeze is abandoned when inactivity (2 s) and then abort (5 s) have both run out.
    assert pin["detection_timeout_s"] == 7.0
    assert pin["extra"]["inactivity_timeout_s"] == 2.0 and pin["extra"]["abort_timeout_s"] == 5.0
    assert pin["extra"]["platform"].startswith(sys.platform)
    with pytest.raises(ValueError, match="RestateAgent"):
        RestateAdapter(load_named("tool_chain_1_effect"), "EXTERNAL", agent_code="native")


def test_the_journal_is_read_for_what_restate_recorded() -> None:
    """The recorded T2 kill: `create_issue` applied twice at the World, journaled once."""
    recorded = json.loads(JOURNAL.read_text(encoding="utf8"))
    workload = load_named("tool_chain_1_effect")
    committed, recoveries = read_journal(recorded["journal"], recorded["journal_events"], workload, "EXTERNAL")
    assert committed == {"issues.create#1"}  # `search` is PURE and its completed run is not an effect
    assert [r["type"] for r in recoveries] == ["TransientError"] * len(recorded["journal_events"])
    assert "Connection refused" in json.dumps(recoveries)


@pytest.mark.parametrize(
    "row,status",
    [
        (None, "UNKNOWN"),
        ({"status": "running"}, "RUNNING"),
        ({"status": "backing-off"}, "RUNNING"),
        ({"status": "suspended"}, "WAITING"),
        ({"status": "paused"}, "FAILED"),
        ({"status": "completed", "completion_result": "success"}, "COMPLETED"),
        ({"status": "completed", "completion_result": "failure"}, "FAILED"),
    ],
)
def test_sys_invocation_status_maps_to_the_neutral_status(row, status) -> None:
    assert invocation_status(row) == status
