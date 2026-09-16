"""Placing a fault on each side of the wire, on each side's own terms (§19.5, K3).

Keel's side is its journal, joined through the attempt the fault row's `sut_ref` names — which is
only worth anything if the adapter really puts it there, so that is tested against a real tool
call. LangGraph's side is its checkpoints, whose timestamps its own process writes — which is only
worth anything if they come back from the documented read, so that is tested against a real graph.
And the page over a results directory must compute K3 only where every fault was placed.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from crashproof.faults.injectors.shim import ToolShim
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import expand
from crashproof.faults.spec import from_doc
from crashproof.report.placement import placements, render
from crashproof.runner.store import ResultStore, slug
from crashproof.verifier import invariants
from crashproof.workloads.spec import load_named
from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.client import WorldClient
from crashproof.world.server import WorldServer

WORKLOAD = load_named("tool_chain_1_effect")
ISSUE = {"title": "CI flake: test_retry", "body": "see search hits"}
BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def test_a_keel_tool_call_names_its_attempt_in_the_fault_row(tmp_path) -> None:
    from crashproof.adapters import keel as adapter
    from keel.core.errors import UnknownOutcome
    from keel.core.protocols import EffectClass, Idempotency, ProbeResult
    from keel.effects.registry import ToolCtx, tool

    world = build_world()
    server = WorldServer(world, port=0)
    await server.start()
    try:
        spec = from_doc({"name": "s", "workload": WORKLOAD.workload, "mode": "shim", "faults": [
            {"id": "f1", "type": "tool_500",
             "trigger": {"boundary": "after:tool_effect", "landmark": "tool:create_issue"}}]})
        trial = TrialDir(tmp_path / "t-7", fresh=True)
        schedule = expand(spec, 7, WORKLOAD)
        schedule.write(trial.schedule_path)
        client = WorldClient(server.base_url)
        shim = ToolShim(trial, schedule, trial_id="t-7", world=client, sut_ref=adapter.sut_ref)
        decl = next(t for t in WORKLOAD.tools_for("EXTERNAL") if t.name == "create_issue")
        run = adapter._build_tool(decl, "none", client, shim, tool, ToolCtx, EffectClass, Idempotency, ProbeResult)
        with pytest.raises(UnknownOutcome):
            await run.run(ISSUE, ToolCtx(run_id="r-1", run_root_id="r-1", step_index=3, attempt_no=2, effect_key="k"))
    finally:
        await server.stop()
    [row] = trial.faults()
    assert row.sut_ref == {"run_id": "r-1", "step_index": 3, "attempt_no": 2}
    assert adapter.sut_ref() == {}, "outside a tool call there is no attempt to name"


async def test_langgraph_checkpoints_come_back_with_their_own_timestamps() -> None:
    pytest.importorskip("langgraph")
    from langgraph.checkpoint.memory import InMemorySaver

    from crashproof.adapters.langgraph import build_graph, checkpoint_rows

    world = build_world()
    server = WorldServer(world, port=0)
    await server.start()
    saver = InMemorySaver()
    try:
        graph = build_graph(WORKLOAD, "EXTERNAL", WorldClient(server.base_url), None, saver)
        started = time.time()
        await graph.ainvoke(dict(WORKLOAD.input), config={"configurable": {"thread_id": "t"}}, durability="sync")
        rows = await checkpoint_rows(saver, "t")
    finally:
        await server.stop()
    assert len(rows) >= 3 and world.applied_counts() == {"issues.create#1": 1}
    stamps = [invariants.iso(r["ts"]) for r in rows]
    assert stamps == sorted(stamps) and started <= stamps[0] <= stamps[-1] <= time.time()
    assert [r["step"] for r in rows] == sorted(r["step"] for r in rows)


# --- the page ---------------------------------------------------------------------
def _ts(offset: float) -> str:
    return (BASE + timedelta(seconds=offset)).isoformat()


def _facts(arm: str, fault_at: float, *, sut_ref: dict | None, checkpoint_at: float | None) -> invariants.TrialFacts:
    base = BASE.timestamp()
    journal = None
    if arm == "keel":
        journal = [
            {"seq": 1, "type": "STEP_INTENDED", "ts": _ts(1), "step_index": 3, "attempt_no": None,
             "body": {"name": "create_issue"}},
            {"seq": 2, "type": "STEP_ATTEMPT_STARTED", "ts": _ts(2), "step_index": 3, "attempt_no": 1, "body": {}},
            {"seq": 3, "type": "RECOVERY_STARTED", "ts": _ts(9), "step_index": None, "attempt_no": None, "body": {}},
        ]
    return invariants.TrialFacts(
        world_receipts=[{"endpoint": "issues.create", "logical_identity": "issues.create#1", "ts": base + 3.0}],
        world_applied={"issues.create#1": 1},
        journal=journal,
        faults=[{"fault_id": "f1", "type": "kill", "boundary": "after:tool_return", "landmark": "tool:create_issue",
                 "occurrence": 1, "recovery_index": 0, "executed": True,
                 "trigger_observed_at": base + fault_at, "sut_ref": sut_ref or {}}],
        sut_checkpoints=None if checkpoint_at is None else [
            {"checkpoint_id": "c", "ts": _ts(checkpoint_at), "step": 2, "source": "loop"}
        ],
    )


def _results(tmp_path, trials: dict[str, list[invariants.TrialFacts | None]]):
    store = ResultStore(tmp_path)
    for cell, facts_list in trials.items():
        for seed, facts in enumerate(facts_list, start=7):
            store.append({"cell_id": cell, "seed": seed, "trial_id": f"t-{seed}", "valid": True,
                          "workload": WORKLOAD.workload, "workload_variant": "EXTERNAL",
                          "faults": [{"type": "kill"}], "ended_at": 0.0})
            if facts is not None:
                trial = tmp_path / slug(cell) / f"t-{seed}"
                trial.mkdir(parents=True)
                (trial / "facts.json").write_text(json.dumps(invariants.dump(facts), default=str), encoding="utf8")
    return tmp_path


KEEL = "keel.default.EXTERNAL.kill@after:tool_return"
LG = "langgraph.sync.EXTERNAL.kill@after:tool_return"
REF = {"run_id": "r", "step_index": 3, "attempt_no": 1}


def test_k3_is_computed_per_cell_and_between_arms_only_where_every_fault_was_placed(tmp_path) -> None:
    """T3 is the cell §28.3 singles out: a kill that lands after LangGraph's checkpoint write in one
    arm and before Keel's outcome commit in the other makes the column measure the shim."""
    results = _results(tmp_path, {
        KEEL: [_facts("keel", 3.5, sut_ref=REF, checkpoint_at=None)] * 3,
        # the checkpoint was written at 3.2 s, between the receipt (3.0) and the kill (3.5): out
        LG: [_facts("lg", 3.5, sut_ref=None, checkpoint_at=4.0)] + [_facts("lg", 3.5, sut_ref=None, checkpoint_at=3.2)] * 2,
    })
    cells = placements(results)
    assert cells[KEEL].fraction == 1.0 and not cells[KEEL].mis_aimed
    assert cells[LG].in_window == 1 and cells[LG].out_of_window == 2 and cells[LG].mis_aimed
    page = render(cells)
    assert "| PASS (100%) |" in page and "| **FAIL** (33%) |" in page
    assert "| EXTERNAL · kill@after:tool_return |" in page and "**FAIL** (67 points)" in page


def test_a_fault_the_artefacts_cannot_place_yields_no_k3_verdict(tmp_path) -> None:
    results = _results(tmp_path, {
        KEEL: [_facts("keel", 3.5, sut_ref=None, checkpoint_at=None), None],
        LG: [_facts("lg", 3.5, sut_ref=None, checkpoint_at=None)],
    })
    cells = placements(results)
    assert cells[KEEL].fraction is None and cells[LG].fraction is None
    page = render(cells)
    assert "not computable: 2 of 2 unobservable" in page and "no facts.json in the trial directory ×1" in page
    assert "runtime side not observable: no journal and no checkpoints exported ×1" in page
    assert "not computable: an arm has unobservable faults" in page
    assert "PASS" not in page and "FAIL" not in page
