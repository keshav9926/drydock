"""Paired comparison (§15.5).

The two rules worth testing are the two that stop a comparison overclaiming: pairing is on the
same spec and the same seed, so a difference is between runtimes rather than between the schedules
they drew; and "too noisy to claim" is a real verdict rather than a fallback nobody reaches.
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
    verdict = next(x for x in compare(a, b).binary if x.metric == "recovery_rate")
    assert verdict.a_only == 30 and verdict.b_only == 0
    assert verdict.p_value is not None and verdict.p_value < 0.001 and "A better" in verdict.verdict

    tied = compare(a, [row("lg.sync.EXTERNAL.kill", s) for s in range(30)])
    assert "too noisy" in next(x for x in tied.binary if x.metric == "recovery_rate").verdict


def test_too_few_events_is_an_answer_about_the_sample() -> None:
    a = [row("keel.d.EXTERNAL.kill", s) for s in range(3)]
    b = [row("lg.sync.EXTERNAL.kill", s, recovery_rate=0) for s in range(3)]
    v = next(x for x in compare(a, b).binary if x.metric == "recovery_rate")
    assert v.p_value is None and "discordant pairs" in v.verdict


def test_an_interval_containing_zero_claims_nothing() -> None:
    import random

    rng = random.Random(1)
    a = [row("keel.d.EXTERNAL.kill", s, recovery_latency_ms=2000 + rng.gauss(0, 50)) for s in range(30)]
    b = [row("lg.sync.EXTERNAL.kill", s, recovery_latency_ms=2000 + rng.gauss(0, 50)) for s in range(30)]
    noisy = next(x for x in compare(a, b).continuous if x.metric == "recovery_latency_ms")
    assert noisy.verdict == "too noisy to claim"

    slower = [row("lg.sync.EXTERNAL.kill", s, recovery_latency_ms=500.0) for s in range(30)]
    clear = next(x for x in compare(a, slower).continuous if x.metric == "recovery_latency_ms")
    assert clear.verdict == "A higher" and clear.ci[0] > 0
