"""matrix v0's arithmetic, which is a published claim (§28.3).

40 cells x 30 seeds = 1200 trials. A typo in the YAML would change that silently, and the report
would still look fine — so the shape is asserted rather than counted by hand.
"""

from __future__ import annotations

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
