"""The statistics module (§15.6–§15.7).

Four properties, each of which a bug would make the report overclaim rather than fail loudly:
the exact test agrees with the hand-computable cases, Holm is monotone and never makes a claim
easier, the MDD refuses to answer where no difference is detectable at all, and the verbatim
tables agree with the formulas beside them to the digit they print.
"""

from __future__ import annotations

import random

from crashproof.stats.ci import (
    exact_binomial,
    holm,
    mdd_paired_binary,
    mdd_paired_continuous,
    paired_bootstrap,
    wilson,
)


def test_the_exact_test_on_the_cases_that_can_be_checked_by_hand() -> None:
    assert exact_binomial(0, 0) == 1.0, "no discordant pairs is no evidence, not a tie"
    assert exact_binomial(5, 5) == 1.0
    # 6-0: 2 * (1/64) = 0.03125 — the smallest split that can reach 0.05, which is why the floor
    # in §15.8 rule 3 is six rather than five.
    assert abs(exact_binomial(6, 0) - 0.03125) < 1e-12
    assert abs(exact_binomial(5, 0) - 0.0625) < 1e-12
    assert exact_binomial(30, 0) < 1e-8, "the strongest result the harness can produce"
    assert exact_binomial(3, 7) == exact_binomial(7, 3), "two-sided, so direction does not matter"


def test_holm_is_monotone_and_never_makes_a_claim_easier() -> None:
    raw = [0.001, 0.04, 0.03, 0.5]
    adjusted = holm(raw)
    assert all(a >= r for a, r in zip(adjusted, raw, strict=True))
    assert sorted(adjusted) == [a for _, a in sorted(zip(raw, adjusted, strict=True))], "monotone"
    assert adjusted[0] == 0.004  # 0.001 * 4
    assert adjusted[2] == 0.09  # 0.03 * 3
    assert adjusted[1] == 0.09, "running maximum: it cannot be adjusted below the rank before it"
    assert holm([0.02]) == [0.02], "a family of one is not adjusted"
    assert all(a <= 1.0 for a in holm([0.9, 0.8, 0.7])), "clamped, never a p-value above one"


def test_the_mdd_refuses_where_nothing_is_detectable() -> None:
    assert mdd_paired_binary(0.0, 30) is None, "arms that never disagree cannot be separated"
    assert mdd_paired_binary(0.05, 30) is None, "1.5 expected discordant pairs, below the floor"
    assert mdd_paired_binary(0.05, 100) is None, "5 expected, still below the six-pair floor"
    # §15.7's paired-binary table, within its own rounding. The table is printed verbatim and the
    # formula is used per cell, so the two have to agree to the digit the page shows.
    for published, psi, n in (("0.036", 0.05, 300), ("0.088", 0.10, 100), ("0.051", 0.10, 300),
                              ("0.07", 0.20, 300), ("0.18", 0.40, 100), ("0.10", 0.40, 300)):
        # Within one unit of the last place the table prints — §15.7 truncates in places and
        # rounds in others, and the claim being tested is that the two never disagree on the page.
        tolerance = 10 ** -len(published.split(".")[1])
        assert abs(mdd_paired_binary(psi, n) - float(published)) < tolerance, (published, psi, n)
    # The standardised continuous row: 0.51 / 0.28 / 0.16 at n = 30 / 100 / 300.
    assert [round(mdd_paired_continuous(n), 2) for n in (30, 100, 300)] == [0.51, 0.28, 0.16]
    assert mdd_paired_continuous(30, sigma_d=200.0) == mdd_paired_continuous(30) * 200.0


def test_wilson_widens_as_n_falls_and_never_leaves_the_unit_interval() -> None:
    lo30, hi30 = wilson(30, 30)
    lo5, hi5 = wilson(5, 5)
    assert hi30 == 1.0 and lo30 > lo5, "unanimity at 30 excludes more than unanimity at 5"
    assert wilson(0, 0) == (0.0, 0.0)
    assert 0.0 <= wilson(1, 100)[0] and wilson(99, 100)[1] <= 1.0


def test_the_bootstrap_resamples_differences_and_is_seeded() -> None:
    deltas = [float(x) for x in range(-5, 26)]
    first = paired_bootstrap(deltas, random.Random(7), resamples=500)
    assert paired_bootstrap(deltas, random.Random(7), resamples=500) == first, "same seed, same CI"
    point, lo, hi = first
    assert point == 10.0 and lo < point < hi
    # A constant difference has no spread to resample: the interval collapses onto the estimate,
    # which is the honest answer rather than a manufactured margin.
    assert paired_bootstrap([3.0] * 20, random.Random(1), resamples=200) == (3.0, 3.0, 3.0)
