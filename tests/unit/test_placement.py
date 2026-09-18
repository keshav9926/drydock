"""Placing a fault on each side of the wire, on each side's own terms (§19.5, K3).

Keel's side is its journal, joined through the attempt the fault row's `sut_ref` names — which is
only worth anything if the adapter really puts it there, so that is tested against a real tool
call. LangGraph's side is its checkpoints, whose timestamps its own process writes — which is only
worth anything if they come back from the documented read, so that is tested against a real graph.
And the page over a results directory must compute K3 only where every fault was placed.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crashproof.faults.injectors.shim import ToolShim
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import expand
from crashproof.faults.spec import from_doc
from crashproof.report.placement import NO_COMMIT_RECORD, placements, render, render_windows, windows
from crashproof.runner.store import ResultStore, slug
from crashproof.verifier import invariants, views
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
    assert f"runtime side not observable: {NO_COMMIT_RECORD} ×1" in page
    assert "not computable: an arm has unobservable faults" in page
    assert "PASS" not in page and "FAIL" not in page


# --- the engines: their own commit records, read out of the export beside the facts ---------------
RESTATE_JOURNAL = Path(__file__).parents[1] / "journals" / "restate_kill_after_tool_effect.json"


def _dbos_steps(*completed: tuple[str, float]) -> dict:
    base = BASE.timestamp()
    return {"workflow_id": "w", "status": "SUCCESS", "steps": [
        {"function_id": i + 1, "function_name": name, "started_at_epoch_ms": round((base + at - 0.02) * 1000),
         "completed_at_epoch_ms": round((base + at) * 1000), "error": None}
        for i, (name, at) in enumerate(completed)
    ]}


def _temporal_history(tool: str, completed_at: float) -> dict:
    payload = base64.b64encode(json.dumps({"name": tool, "tool_args": {}}).encode()).decode()
    return {"workflow_id": "w", "committed": [], "history": {"events": [
        {"eventId": "5", "eventTime": _ts(0.5), "eventType": "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED",
         "activityTaskScheduledEventAttributes": {
             "activityId": "2", "activityType": {"name": "agent__crashproof__toolset__world__call_tool"},
             "input": {"payloads": [{"metadata": {"encoding": "anNvbi9wbGFpbg=="}, "data": payload}]}}},
        {"eventId": "7", "eventTime": _ts(completed_at), "eventType": "EVENT_TYPE_ACTIVITY_TASK_COMPLETED",
         "activityTaskCompletedEventAttributes": {"scheduledEventId": "5", "startedEventId": "6"}},
    ]}}


def test_each_engine_export_yields_its_own_commit_records() -> None:
    dbos = views.commits_from_export(_dbos_steps(("crashproof.model", 1.0), ("crashproof.tool.create_issue", 3.2)))
    assert [(c["tool"], c["source"]) for c in dbos] == [(None, "dbos"), ("create_issue", "dbos")]
    assert dbos[1]["ts"] == BASE.timestamp() + 3.2
    native = views.commits_from_export(_dbos_steps(("crashproof.tool", 3.2)))
    assert native[0]["tool"] is None, "the native loop's one tool step names no tool"
    [activity] = views.commits_from_export(_temporal_history("create_issue", 3.3))
    assert (activity["tool"], activity["ts"], activity["source"]) == ("create_issue", BASE.timestamp() + 3.3, "temporal")
    runs = views.commits_from_export(json.loads(RESTATE_JOURNAL.read_text(encoding="utf8")))
    assert [r["tool"] for r in runs] == ["Model call", "search", "Model call", "create_issue", "Model call"]
    assert runs[3]["ts"] == invariants.iso("2026-09-16T16:42:29.814Z")
    assert views.commits_from_export({"events": [], "store_clock": {}}) is None, "Keel's export is a journal"


def _engine_results(tmp_path, trials: dict[str, list[tuple[invariants.TrialFacts, str | None, dict | None]]]):
    store = ResultStore(tmp_path)
    for cell, entries in trials.items():
        for seed, (facts, export_name, export) in enumerate(entries, start=7):
            store.append({"cell_id": cell, "seed": seed, "trial_id": f"t-{seed}", "valid": True,
                          "workload": WORKLOAD.workload, "workload_variant": "EXTERNAL",
                          "faults": [{"type": "kill"}], "ended_at": 0.0})
            trial = tmp_path / slug(cell) / f"t-{seed}"
            (trial / "sut").mkdir(parents=True)
            (trial / "facts.json").write_text(json.dumps(invariants.dump(facts), default=str), encoding="utf8")
            if export is not None:
                (trial / "sut" / export_name).write_text(json.dumps(export), encoding="utf8")
    return tmp_path


def test_an_engine_is_placed_on_the_commit_records_its_export_carries(tmp_path) -> None:
    """The published trials' facts predate `sut_commits`, so the join reads the export beside them;
    a directory with facts only stays unobservable, and two placed arms already apart fail."""
    dbos, temporal, restate = (f"{a}.EXTERNAL.kill@after:tool_return"
                               for a in ("dbos.native", "temporal.pydantic_ai", "restate.pydantic_ai"))
    fact = _facts("engine", 3.5, sut_ref=None, checkpoint_at=None)
    results = _engine_results(tmp_path, {
        # the step committed at 3.2, between the receipt (3.0) and the kill (3.5): out; at 4.0: in
        dbos: [(fact, "steps.json", _dbos_steps(("crashproof.tool", 3.2))),
               (fact, "steps.json", _dbos_steps(("crashproof.tool", 4.0)))],
        temporal: [(fact, "history.json", _temporal_history("create_issue", 4.0))] * 2,
        restate: [(fact, None, None)] * 2,
    })
    cells = placements(results)
    assert (cells[dbos].in_window, cells[dbos].out_of_window) == (1, 1)
    assert cells[temporal].fraction == 1.0 and cells[restate].fraction is None
    page = render(cells)
    assert "after:tool_return · after commit step 1 ✗ ×1" in page
    assert f"runtime side not observable: {NO_COMMIT_RECORD} ×2" in page
    assert "**FAIL** (50 points among the 2 placed arms)" in page

    with_field = invariants.load({**invariants.dump(fact), "sut_commits": views.commits_from_export(
        _dbos_steps(("crashproof.tool", 4.0)))})
    [placed] = views.placement(with_field, {"create_issue": "issues.create"})
    assert placed["in_window"] is True, "a trial written with `sut_commits` needs no export"


def test_ambiguity_window_width_is_measured_on_baselines_per_runtime(tmp_path) -> None:
    base = BASE.timestamp()

    def baseline(**kw) -> invariants.TrialFacts:
        return invariants.TrialFacts(
            world_receipts=[{"endpoint": "kv.search", "logical_identity": "kv.search#1", "ts": base + 1.0},
                            {"endpoint": "issues.create", "logical_identity": "issues.create#1", "ts": base + 3.0}],
            **kw,
        )

    keel_journal = [
        {"seq": 1, "type": "STEP_INTENDED", "ts": _ts(2.9), "step_index": 3, "body": {"name": "create_issue"}},
        {"seq": 2, "type": "STEP_ATTEMPT_STARTED", "ts": _ts(2.9), "step_index": 3, "attempt_no": 1, "body": {}},
        {"seq": 3, "type": "STEP_COMPLETED", "ts": _ts(3.009), "step_index": 3, "attempt_no": 1, "body": {}},
        {"seq": 4, "type": "STEP_INTENDED", "ts": _ts(3.02), "step_index": 4, "body": {"name": "decide"}},
        {"seq": 5, "type": "STEP_COMPLETED", "ts": _ts(3.04), "step_index": 4, "attempt_no": 1, "body": {}},
    ]
    results = _engine_results(tmp_path, {
        "keel.default.EXTERNAL.baseline": [(baseline(journal=keel_journal), None, None)],
        "langgraph.sync.EXTERNAL.baseline": [
            (baseline(sut_checkpoints=[{"ts": _ts(2.0), "step": 1}, {"ts": _ts(3.012), "step": 2}]), None, None)],
        "dbos.pydantic_ai.EXTERNAL.baseline": [(baseline(), "steps.json", _dbos_steps(
            ("crashproof.tool.search", 1.01), ("crashproof__model.request", 2.5), ("crashproof.tool.create_issue", 3.008)))],
        "restate.pydantic_ai.EXTERNAL.baseline": [(baseline(), None, None)],
    })
    found = windows(results)
    assert set(found) == {(a, "create_issue") for a in ("keel.default", "langgraph.sync", "dbos.pydantic_ai",
                                                        "restate.pydantic_ai")}, "PURE tools have no window"
    widths = {arm: [round(w * 1000, 3) for w in found[(arm, "create_issue")].widths] for arm, _ in found}
    assert widths == {"keel.default": [9.0], "langgraph.sync": [12.0], "dbos.pydantic_ai": [8.0], "restate.pydantic_ai": []}
    page = render_windows(found)
    assert "| `keel.default` | `create_issue` | 9.0 | [9.0, 9.0] | 1 | 0 |" in page
    assert f"| `restate.pydantic_ai` | `create_issue` | not computable | — | 0 | {NO_COMMIT_RECORD} ×1 |" in page
    assert views.COMMIT_SOURCES["dbos"][1] in page


def test_a_named_record_is_the_tools_own_so_a_clock_that_disagrees_shows() -> None:
    base = BASE.timestamp()
    facts = invariants.TrialFacts(
        world_receipts=[{"endpoint": "issues.create", "ts": base + 3.0}],
        sut_commits=[{"ts": base + 2.998, "tool": "create_issue", "source": "temporal"},
                     {"ts": base + 3.05, "tool": None, "source": "temporal"}],
    )
    width, source = views.window_width(facts, "create_issue", "issues.create")
    assert source == "temporal" and round(width * 1000, 3) == -2.0, "not the model call's commit after it"
