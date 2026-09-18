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


def test_a_defect_metric_does_not_award_the_win_to_the_arm_with_more_of_it() -> None:
    """`recovery_rate` counts good outcomes; `replay_divergence` counts a run that took a path its
    own journal does not describe. Reading the polarity off the count alone reports the arm that
    diverged in every trial as the better one — the opposite claim, on a published page."""
    a = [row("keel.d.EXTERNAL.kill", s, replay_divergence=0) for s in range(30)]
    b = [row("lg.async.EXTERNAL.kill", s, replay_divergence=1) for s in range(30)]
    c = compare(a, b)
    diverged = only(c, "replay_divergence")
    assert (diverged.a_only, diverged.b_only) == (0, 30), "B diverged in every paired trial"
    assert "A better" in diverged.verdict, diverged.verdict

    # The same shape on a metric where 1 is a success still favours the arm that has more of it.
    recovered = only(compare(a, [row("lg.async.EXTERNAL.kill", s, recovery_rate=0) for s in range(30)]),
                     "recovery_rate")
    assert "A better" in recovered.verdict


def test_too_few_discordant_pairs_is_a_property_of_the_test_not_the_sample() -> None:
    """§15.8 rule 3: below six discordant pairs the exact two-sided p cannot reach 0.05 at any n,
    so the floor is named as the test's, not as "not enough trials"."""
    a = [row("keel.d.EXTERNAL.kill", s) for s in range(30)]
    b = [row("lg.sync.EXTERNAL.kill", s, recovery_rate=0 if s < 3 else 1) for s in range(30)]
    v = only(compare(a, b), "recovery_rate")
    assert "3 discordant pairs" in v.verdict and v.rule.startswith("3 ·")
    assert v.p_value == 0.25, "disqualified, and still a member of its family with its p printed"


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


def test_holm_runs_within_a_metric_family_over_every_row_with_a_p_value() -> None:
    triggers = ("t1", "t2", "t3")
    a = [row(f"keel.d.EXTERNAL.{t}", s) for t in triggers for s in range(30)]
    b = [row(f"lg.sync.EXTERNAL.{t}", s, recovery_rate=0) for t in triggers for s in range(30)]
    family = next(f for f in compare(a, b).families if f.metric == "recovery_rate")
    assert all(r.p_holm is not None for r in family.rows), "three comparisons in the family"
    for r in family.rows:
        assert r.p_holm >= r.p_value, "adjustment never makes a claim easier"
        assert "A better" in r.verdict, "30-0 survives a family of three"


def test_rows_that_did_not_reject_still_count_toward_m() -> None:
    """§15.6: every printed comparison is a member. Dropping the six null rows from `m` let a lone
    p = 0.0078 be adjusted as a family of one and claimed; as a family of seven it is 0.055."""
    triggers = [f"t{i}" for i in range(7)]
    a = [row(f"keel.d.EXTERNAL.{t}", s) for t in triggers for s in range(30)]
    b = [
        row(f"lg.sync.EXTERNAL.{t}", s, recovery_rate=0 if t == "t0" and s < 8 else 1)
        for t in triggers
        for s in range(30)
    ]
    family = next(f for f in compare(a, b).families if f.metric == "recovery_rate")
    assert len([r for r in family.rows if r.p_holm is not None]) == 7
    lone = only(compare(a, b), "recovery_rate", "EXTERNAL·t0")
    assert round(lone.p_value, 4) == 0.0078 and round(lone.p_holm, 4) == 0.0547
    assert "too noisy" in lone.verdict and lone.rule == "5 · Holm"


def test_a_confirmed_cell_is_compared_at_the_confirmation_n_and_screening_moves_to_the_appendix() -> None:
    """§15.3: one tier per cell, Holm over the family with mixed n (§15.6), screening kept."""
    from crashproof.report.compare import render

    def arm(cell: str, seeds, **metrics):
        return [row(cell.format(t=t), s, **metrics) for t in ("t0", "t1") for s in seeds
                if t == "t0" or s < 100_000]

    screening, confirmation = range(7, 37), range(100_000, 100_300)
    a = arm("keel.d.EXTERNAL.{t}", screening) + arm("keel.d.EXTERNAL.{t}", confirmation)
    b = arm("lg.sync.EXTERNAL.{t}", screening, recovery_rate=0) + arm("lg.sync.EXTERNAL.{t}", confirmation, recovery_rate=0)
    c = compare(a, b)
    family = next(f for f in c.families if f.metric == "recovery_rate")
    assert {r.cell: r.n for r in family.rows} == {"EXTERNAL·t0": 300, "EXTERNAL·t1": 30}
    assert all(r.p_holm is not None for r in family.rows), "one family, mixed n"
    [appendix] = [f for f in c.screening if f.metric == "recovery_rate"]
    assert [(r.cell, r.n) for r in appendix.rows] == [("EXTERNAL·t0", 30)]
    page = render(c)
    assert "1 cell(s) ran at the confirmation tier" in page
    assert "### recovery_rate · w · EXTERNAL · screening" in page.split("## Appendix")[1]
    screening_only = compare([r for r in a if r["seed"] < 100_000], [r for r in b if r["seed"] < 100_000])
    assert "## Appendix" not in render(screening_only)
