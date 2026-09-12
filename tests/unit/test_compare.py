"""Paired comparison (§15.5–§15.8).

The rules worth testing are the ones that stop a comparison overclaiming: pairing is on the same
spec and the same seed, so a difference is between runtimes rather than between the schedules they
drew; a comparison is made per `(location, fault)` cell and never pooled across triggers; and
"too noisy to claim" is a real verdict with a named rule rather than a fallback nobody reaches.
"""

from __future__ import annotations

from crashproof.report.compare import compare, pair


def row(cell: str, seed: int, **metrics):
    base = dict(recovery_rate=1, logical_correctness=1, duplicate_effects=0, duplicate_receipts=0,
                missing_required=0, recovery_latency_ms=2000.0, extra_model_calls=0,
                wall_clock_overhead_ms=0.0)
    return {
        "workload": "w", "workload_variant": "EXTERNAL", "cell_id": cell, "spec_hash": "h",
        "seed": seed, "metrics": {**base, **metrics},
    }


def only(c, metric: str, cell: str = "EXTERNAL·kill"):
    return next(r for r in c.rows if r.metric == metric and r.cell == cell)


def test_pairs_need_the_same_spec_and_the_same_seed() -> None:
    a = [row("keel.default.EXTERNAL.kill", s) for s in (1, 2, 3)]
    b = [row("lg.sync.EXTERNAL.kill", s) for s in (2, 3, 4)]
    pairs, unpaired_a, unpaired_b = pair(a, b)
    assert [p.key[-1] for p in pairs] == [2, 3]
    assert (unpaired_a, unpaired_b) == (1, 1), "reported as unpaired, never quietly averaged in"

    mismatched = [{**row("lg.sync.EXTERNAL.kill", 2), "spec_hash": "other"}]
    assert pair(a, mismatched)[0] == [], "a different spec is not a pair"


def test_a_safety_observation_is_counted_not_tested() -> None:
    """Whether a runtime filed the issue twice is an observation, not a sample."""
    a = [row("keel.d.EXTERNAL.kill", s) for s in range(30)]
    b = [row("lg.sync.EXTERNAL.kill", s, duplicate_effects=1) for s in range(30)]
    c = compare(a, b)
    assert c.safety["duplicate_effects"] == (0, 30)
    assert not hasattr(c.safety["duplicate_effects"], "p_value")


def test_a_clean_split_is_significant_and_a_tie_is_not() -> None:
    a = [row("keel.d.EXTERNAL.kill", s) for s in range(30)]
    b = [row("lg.sync.EXTERNAL.kill", s, recovery_rate=0) for s in range(30)]
    verdict = only(compare(a, b), "recovery_rate")
    assert verdict.a_only == 30 and verdict.b_only == 0
    assert verdict.p_value is not None and verdict.p_value < 0.001 and "A better" in verdict.verdict

    tied = only(compare(a, [row("lg.sync.EXTERNAL.kill", s) for s in range(30)]), "recovery_rate")
    assert "too noisy" in tied.verdict


def test_too_few_discordant_pairs_is_a_property_of_the_test_not_the_sample() -> None:
    """§15.8 rule 3: below six discordant pairs the exact two-sided p cannot reach 0.05 at any n,
    so the floor is named as the test's, not as "not enough trials"."""
    a = [row("keel.d.EXTERNAL.kill", s) for s in range(30)]
    b = [row("lg.sync.EXTERNAL.kill", s, recovery_rate=0 if s < 3 else 1) for s in range(30)]
    v = only(compare(a, b), "recovery_rate")
    assert v.p_value is None and "3 discordant pairs" in v.verdict
    assert v.rule.startswith("3 ·")


def test_an_interval_containing_zero_claims_nothing() -> None:
    import random

    rng = random.Random(1)
    a = [row("keel.d.EXTERNAL.kill", s, recovery_latency_ms=2000 + rng.gauss(0, 50)) for s in range(30)]
    b = [row("lg.sync.EXTERNAL.kill", s, recovery_latency_ms=2000 + rng.gauss(0, 50)) for s in range(30)]
    noisy = only(compare(a, b), "recovery_latency_ms")
    assert noisy.verdict == "too noisy to claim" and noisy.rule == "1 · CI contains 0"

    slower = [row("lg.sync.EXTERNAL.kill", s, recovery_latency_ms=500.0) for s in range(30)]
    clear = only(compare(a, slower), "recovery_latency_ms")
    assert clear.verdict == "A higher" and clear.ci[0] > 0


def test_cells_are_compared_separately_and_never_pooled() -> None:
    """A kill at `after:tool_effect` and a `pause_past_ttl` are different questions. An average
    over them is an answer to neither, so each is its own row in the family."""
    a = [row(f"keel.d.EXTERNAL.{t}", s) for t in ("kill", "pause") for s in range(30)]
    b = [
        row(f"lg.sync.EXTERNAL.{t}", s, recovery_rate=0 if t == "kill" else 1)
        for t in ("kill", "pause")
        for s in range(30)
    ]
    c = compare(a, b)
    family = next(f for f in c.families if f.metric == "recovery_rate")
    assert {r.cell for r in family.rows} == {"EXTERNAL·kill", "EXTERNAL·pause"}
    assert "A better" in only(c, "recovery_rate", "EXTERNAL·kill").verdict
    assert "too noisy" in only(c, "recovery_rate", "EXTERNAL·pause").verdict


def test_holm_runs_within_a_metric_family_and_skips_rows_no_rule_left_standing() -> None:
    """A row already disqualified by rules 1–4 is not a hypothesis test, so it does not inflate
    `m` — the same reason §15.6 excludes N/A cells from the family."""
    triggers = ("t1", "t2", "t3")
    a = [row(f"keel.d.EXTERNAL.{t}", s) for t in triggers for s in range(30)]
    b = [row(f"lg.sync.EXTERNAL.{t}", s, recovery_rate=0) for t in triggers for s in range(30)]
    family = next(f for f in compare(a, b).families if f.metric == "recovery_rate")
    live = [r for r in family.rows if r.p_holm is not None]
    assert len(live) == 3, "three live comparisons in the family"
    for r in live:
        assert r.p_holm >= r.p_value, "adjustment never makes a claim easier"
        assert "A better" in r.verdict, "30-0 survives a family of three"

    # One live row beside two disqualified ones is adjusted as a family of one, not of three.
    b_mixed = [
        row(f"lg.sync.EXTERNAL.{t}", s, recovery_rate=0 if t == "t1" else 1)
        for t in triggers
        for s in range(30)
    ]
    mixed = next(f for f in compare(a, b_mixed).families if f.metric == "recovery_rate")
    adjusted = [r for r in mixed.rows if r.p_holm is not None]
    assert len(adjusted) == 1
    assert adjusted[0].p_holm == adjusted[0].p_value
