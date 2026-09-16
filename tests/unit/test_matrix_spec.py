"""matrix v0's arithmetic, which is a published claim (§28.3).

40 cells x 30 seeds = 1200 trials. A typo in the YAML would change that silently, and the report
would still look fine — so the shape is asserted rather than counted by hand.
"""

from __future__ import annotations

import pytest

from crashproof.runner.bench import Matrix

MATRIX = "bench/specs/matrix_v0.yaml"


def test_the_matrix_is_the_arithmetic_it_claims() -> None:
    m = Matrix.load(MATRIX)
    cells = m.cells()
    assert len(cells) == 40, "4 configs x 2 bands x (4 (location, fault) pairs + 1 baseline)"
    assert m.seeds == 30 and len(cells) * m.seeds == 1200
    assert m.seed_range()[0] == 7 and m.seed_range()[-1] == 36


def test_every_trigger_becomes_one_spec_aimed_at_a_landmark() -> None:
    """Landmarks, never ordinals: the same spec has to land on the same logical point in an arm
    that issues three requests and one that issues six."""
    by_trigger = {c.trigger: c for c in Matrix.load(MATRIX).cells() if c.adapter == "keel"}
    assert set(by_trigger) == {
        "baseline", "before:tool_call", "after:tool_effect", "after:tool_return",
        "pause_past_ttl@before:tool_call",
    }
    assert by_trigger["baseline"].spec.is_baseline
    for trigger, cell in by_trigger.items():
        if cell.is_baseline:
            continue
        [fault] = cell.spec.faults
        assert fault.trigger.landmark == "tool:create_issue"
        assert fault.type == ("pause_past_ttl" if "pause" in trigger else "kill")
        assert fault.trigger.boundary == trigger.rpartition("@")[2]


def test_the_two_arms_declare_different_key_sources() -> None:
    """Keel presents `effect_key`; LangGraph has no documented key primitive, so its headline
    cells run without one and its IDEMPOTENT band is measured by the receiver's natural dedup."""
    cells = {(c.adapter, c.key_source) for c in Matrix.load(MATRIX).cells()}
    assert ("keel", "framework") in cells
    assert ("langgraph", "none") in cells


def test_a_baseline_exists_for_every_band_and_config() -> None:
    """Without a paired no-fault trial the delta metrics are undefined, not merely imprecise."""
    baselines = {c.id for c in Matrix.load(MATRIX).cells() if c.is_baseline}
    assert len(baselines) == 8, "4 configs x 2 bands"


# --- the key source a row records, and the arms that can run -------------------------
def test_a_row_records_the_key_the_arm_presents_not_the_one_the_variant_asks_for() -> None:
    """The IDEMPOTENT variant asks for `framework`. LangGraph has none to give, so its rows say
    `none` — its IDEMPOTENT band is the receiver's natural dedup at F0, never F1 (§14.2)."""
    from crashproof.adapters.keel import KeelAdapter
    from crashproof.adapters.langgraph import LangGraphAdapter
    from crashproof.runner.trial import key_source_in_effect

    assert key_source_in_effect(LangGraphAdapter, "framework") == "none"
    assert key_source_in_effect(KeelAdapter, "framework") == "framework"
    assert key_source_in_effect(KeelAdapter, "none") == "none"


def test_a_matrix_declaring_an_arm_at_a_key_source_it_cannot_present_is_refused() -> None:
    from crashproof.adapters.keel import KeelAdapter
    from crashproof.adapters.langgraph import LangGraphAdapter
    from crashproof.runner.bench import refuse_conflicting_key_sources

    m = Matrix.load(MATRIX)
    adapters = {"keel": KeelAdapter, "langgraph": LangGraphAdapter}
    refuse_conflicting_key_sources(m, adapters)  # the published matrix is consistent
    next(a for a in m.adapters if a["name"] == "langgraph")["key_source"] = "framework"
    with pytest.raises(ValueError, match="langgraph at key_source=framework"):
        refuse_conflicting_key_sources(m, adapters)


async def test_a_missing_arm_is_reported_before_any_trial_starts(tmp_path) -> None:
    from crashproof.adapters.keel import KeelAdapter
    from crashproof.runner.bench import run_matrix

    notes: list[str] = []

    class Started(KeelAdapter):
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("a trial started")

    with pytest.raises(RuntimeError, match="a trial started"):
        await run_matrix(Matrix.load(MATRIX), out_dir=tmp_path, adapters={"keel": Started},
                         on_row=lambda row, cell, note: notes.append(f"{cell.adapter}: {note}"))
    assert len(notes) == 30 and all(n.startswith("langgraph: adapter not built") for n in notes)


def test_an_arm_whose_extra_is_not_installed_is_not_registered(monkeypatch) -> None:
    """The adapter modules import their framework lazily, so an `except ImportError` around the
    import never fired and the arm failed inside its first trial instead."""
    import importlib.util

    from crashproof.cli import main

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: None if name in ("langgraph", "dbos", "temporalio", "restate") else real(name, *a)
    )
    monkeypatch.setattr(main, "ADAPTERS", {})
    assert set(main._adapters()) == {"keel"}


def test_the_langgraph_adapter_builds_every_workload_it_declares() -> None:
    """The one test that imports the LangGraph arm. CI installs the extra, so a change to the shared
    harness that breaks this adapter fails on the commit rather than in an overnight bench."""
    pytest.importorskip("langgraph")
    from langgraph.checkpoint.memory import InMemorySaver

    from crashproof.adapters.langgraph import LangGraphAdapter, build_graph
    from crashproof.workloads.spec import load_named
    from crashproof.world.client import WorldClient

    for name in sorted(LangGraphAdapter.workloads):
        workload = load_named(name)
        for variant in workload.variants:
            graph = build_graph(workload, variant, WorldClient("http://127.0.0.1:9"), None, InMemorySaver())
            assert {"agent", "tools"} <= set(graph.get_graph().nodes)
            pin = LangGraphAdapter(workload, variant, durability="async").config_pin().as_dict()
            assert pin["durability"] == "async" and pin["framework_versions"]["langgraph"]


def test_the_dbos_adapter_builds_every_workload_it_declares() -> None:
    """Both `agent_code` rows, every workload, every variant: built and registered with DBOS, never
    launched, so no database is needed. CI installs the extra for the same reason as LangGraph's."""
    pytest.importorskip("dbos")
    from dbos import DBOS

    from crashproof.adapters.dbos import BUILDERS, DBOSAdapter
    from crashproof.runner.trial import key_source_in_effect
    from crashproof.workloads.spec import load_named
    from crashproof.world.client import WorldClient

    assert key_source_in_effect(DBOSAdapter, "framework") == "framework"
    try:
        for agent_code, build in BUILDERS.items():
            for name in sorted(DBOSAdapter.workloads):
                workload = load_named(name)
                for variant in workload.variants:
                    DBOS.destroy(destroy_registry=True)
                    assert callable(build(workload, variant, WorldClient("http://127.0.0.1:9"), None))
                    pin = DBOSAdapter(workload, variant, agent_code=agent_code).config_pin().as_dict()
                    assert pin["extra"]["agent_code"] == agent_code and pin["framework_versions"]["dbos"]
                    assert ("pydantic-ai-slim" in pin["framework_versions"]) == (agent_code == "pydantic_ai")
    finally:
        DBOS.destroy(destroy_registry=True)
