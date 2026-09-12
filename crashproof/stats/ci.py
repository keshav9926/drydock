"""Wilson, the exact paired test, the bootstrap, Holm and the MDD tables (§15.5–§15.8).

Five functions and one constant, all pure, all over plain numbers. They live apart from the report
because the question "what can be claimed from this many trials" has to be answerable without
rendering anything, and because a reader who disagrees with the family definition has to be able to
recompute the adjustment from the raw p-values the page prints beside it.

The division the whole module exists to keep:

**Safety is counted, not estimated.** Nothing here applies to S1–S5. A duplicate effect is an
observation, not a sample from a population, and an interval around it would suggest a tolerance
that does not exist. There is no function below that takes a safety count.

**Liveness and economy are estimated, and most of the time the estimate is "too noisy to claim".**
At thirty seeds that is the honest answer, and §15.8's five rules are what make it a verdict rather
than a shrug. Four of them are computable here — the CI contains zero, the event floor, the
six-pair floor, the MDD at this `n` — and the fifth is Holm within the family, which only the
report knows how to group.
"""

from __future__ import annotations

import math
import random
import statistics

#: 1.96 and 0.84: two-sided α = 0.05, power = 0.80. Both appear in §15.7's formulas.
Z_ALPHA = 1.96
Z_POWER = 0.84

#: §15.8 rule 3. Below six discordant pairs the exact two-sided test cannot reach 0.05 whatever `n`
#: is — 6–0 gives p = 0.031 and 5–0 gives 0.0625 — so the floor is a property of the test, not of
#: the sample. Rule 2's five-event floor does *not* apply to the exact branch (§15.8 says so
#: explicitly); it would nullify a 30–0 split whose p is about 2⁻²⁹, which is the strongest result
#: this harness can produce.
DISCORDANT_FLOOR = 6

BOOTSTRAP_RESAMPLES = 10_000


def wilson(successes: int, n: int, z: float = Z_ALPHA) -> tuple[float, float]:
    """A 95% interval for a proportion. Printed for liveness, never for safety: a safety cell is
    PASS or FAIL with counterexamples, and an interval around it would suggest a tolerance that
    does not exist (§15.4)."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def exact_binomial(b: int, c: int) -> float:
    """McNemar's exact test: two-sided p over the discordant pairs alone.

    Only discordant pairs carry information. A trial both arms passed says nothing about which is
    better, and counting it would dilute the very thing being measured — which is also why the
    denominator here is `b + c` and not `n`. Under the null each discordant pair is a fair coin, so
    the p-value is the binomial tail doubled, computed exactly rather than through the χ²
    approximation that the small counts here would invalidate.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def paired_bootstrap(
    deltas: list[float], rng: random.Random, resamples: int = BOOTSTRAP_RESAMPLES
) -> tuple[float, float, float]:
    """`(median difference, lo, hi)` at 95%, resampling the per-seed differences.

    On the *differences*, not on the two arms separately: the pairing is the design, and resampling
    the arms independently would throw away the shared schedule that makes a difference a
    difference between runtimes rather than between the timings they happened to draw.
    """
    point = statistics.median(deltas)
    medians = sorted(
        statistics.median([deltas[rng.randrange(len(deltas))] for _ in deltas])
        for _ in range(resamples)
    )
    lo = medians[int(0.025 * len(medians))]
    hi = medians[min(len(medians) - 1, int(0.975 * len(medians)))]
    return point, lo, hi


def holm(p_values: list[float]) -> list[float]:
    """Holm–Bonferroni adjusted p-values, returned in the order given (§15.6).

    Step-down: sort ascending, multiply `p_(j)` by `m − j + 1`, then take a running maximum so the
    sequence is monotone — without that a later comparison could be adjusted below an earlier one
    and the rejection set would not be nested. Holm over Bonferroni because it is uniformly more
    powerful at the same family-wise error rate; over Benjamini–Hochberg because a matrix that says
    "Keel is faster here" is a set of individual claims, each of which has to be individually
    defensible, and false-discovery control is the wrong contract for that.

    Mixed `n` within a family is expected and legitimate — each p-value is valid at its own `n`,
    and the report prints `n` beside every one of them.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, p_values[i] * (m - rank)))
        adjusted[i] = running
    return adjusted


def mdd_paired_binary(psi: float, n: int) -> float | None:
    """The smallest `δ = (b − c)/n` detectable at this discordance rate and `n` (§15.7).

    `δ = (z_α + z_power) · √(ψ / n)`, and `None` when the expected discordant count `ψ·n` is below
    the six-pair floor — there the answer is not a small number, it is that no difference is
    detectable at any size, which is a different statement and prints differently.

    Pairing helps only when the arms actually disagree on some seeds. Two runtimes that both
    recover 30/30 have `ψ = 0` and no test can separate them, nor should one.
    """
    if n <= 0 or psi <= 0 or psi * n < DISCORDANT_FLOOR:
        return None
    return (Z_ALPHA + Z_POWER) * math.sqrt(psi / n)


def mdd_paired_continuous(n: int, sigma_d: float = 1.0) -> float | None:
    """`(z_α + z_power) / √n`, times the observed SD of the per-seed differences.

    0.51σ at n = 30, 0.28 at n = 100, 0.16 at n = 300: a recovery-latency difference has to exceed
    roughly half a standard deviation of the paired differences to be claimable from screening.
    The bootstrap CI is what the report actually claims from; this is the planning number, and the
    input to §15.8's fourth rule.
    """
    if n <= 0:
        return None
    return (Z_ALPHA + Z_POWER) / math.sqrt(n) * sigma_d


#: §15.7's three tables, printed verbatim in every report so that "you did not run enough trials"
#: is a question the reader can answer from the page rather than from a footnote. Verbatim and not
#: recomputed on purpose: they are planning numbers fixed at publication, and a table that drifted
#: with a rounding change in this module would stop being the thing the prose cites. The per-cell
#: rule-4 test uses the functions above with that cell's *observed* `ψ` or `σ_d`; the two agree to
#: the printed digit everywhere except (ψ = 0.40, n = 30), where §15.7 prints 0.31 and the formula
#: gives 0.32.
MDD_TABLES = """### Minimum detectable difference (§15.7)

Two-sided α = 0.05, power = 0.80, equal `n` per arm.

**Unpaired difference in proportions** — the smallest drop from a baseline `p₀` that is detectable.

| `p₀` | n = 30 | n = 100 | n = 300 |
|---|---|---|---|
| 0.99 | 0.24 | 0.09 | 0.04 |
| 0.95 | 0.28 | 0.12 | 0.06 |
| 0.90 | 0.31 | 0.15 | 0.08 |
| 0.80 | 0.34 | 0.18 | 0.10 |
| 0.50 | 0.33 | 0.19 | 0.11 |

At n = 30 a recovery-rate gap smaller than ~30 percentage points is invisible. That is the honest
size of a screening tier, and it is why screening exists to find unanimity and to triage, not to
rank.

**Paired binary (McNemar / exact)** by discordance rate `ψ = (b+c)/n` — the smallest
`δ = (b−c)/n` detectable.

| `ψ` | n = 30 | n = 100 | n = 300 |
|---|---|---|---|
| 0.05 | — (≈1.5 discordant pairs expected; nothing detectable) | — (5 expected; below the 6-pair floor) | 0.036 |
| 0.10 | — (3 expected) | 0.088 (of 10 discordant, ≥ 9 one way) | 0.051 |
| 0.20 | ≥ `ψ` (6 expected; detectable only if all 6 fall one way, p = 0.031) | 0.12 | 0.07 |
| 0.40 | 0.31 | 0.18 | 0.10 |

Pairing helps only when the arms actually disagree on some seeds: two runtimes that both recover
30/30 have `ψ = 0`, and no test can separate them.

**Paired continuous, standardised** (`δ / σ_d`): `MDD = (1.96 + 0.84) / √n` — **0.51** at n = 30,
**0.28** at n = 100, **0.16** at n = 300. The report multiplies by each cell's observed `σ_d` and
prints the result in ms or tokens.
"""
