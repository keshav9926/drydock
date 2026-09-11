"""Paired comparison between two arms (§15.5, §24.6).

Pairing is on `(workload, variant, trigger, spec_hash, seed)` — the same spec and the same seed on
both sides — because that is the only way a difference is a difference between *runtimes* rather
than between the schedules they happened to draw. Unpaired rows are reported as unpaired, never
silently averaged in.

Two kinds of statement, computed differently, for the same reason they are typeset differently in
the matrix:

**Safety is counted, not estimated.** Duplicate and lost effects are reported as totals with their
counterexamples. There is no p-value on "did this runtime file the issue twice", because that is an
observation, not a sample from a population.

**Liveness and economy are estimated.** Binary outcomes get McNemar's exact test over the
discordant pairs — the only pairs that carry information — and continuous ones get a paired
bootstrap on the median difference. Both report an interval, and the verdict is "too noisy to
claim" whenever it contains zero, which is a real answer and the most common honest one at n=30.

# ponytail: exact binomial and a 10k-resample bootstrap, both stdlib. Holm-Bonferroni across
# families and the MDD tables are phase 6 with the rest of the statistics module (§27.8).
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any

BOOTSTRAP_RESAMPLES = 10_000
#: A family needs enough discordant pairs to say anything at all; below this the answer is that
#: the trial count was too small, not that the runtimes are the same (§15.8).
MIN_EVENTS = 5

#: Metrics whose value includes the runtime's own detection wait. Comparing them against an arm
#: the harness re-invokes is comparing against zero detection by construction.
DETECTION_BOUND = frozenset({"recovery_latency_ms", "wall_clock_overhead_ms"})


@dataclass(slots=True)
class Pairing:
    key: tuple[Any, ...]
    a: dict[str, Any]
    b: dict[str, Any]


@dataclass(slots=True)
class MetricComparison:
    metric: str
    n: int = 0
    a_median: float | None = None
    b_median: float | None = None
    difference: float | None = None
    ci: tuple[float, float] | None = None
    verdict: str = "too noisy to claim"


@dataclass(slots=True)
class BinaryComparison:
    metric: str
    n: int = 0
    a_only: int = 0  # a succeeded, b did not
    b_only: int = 0
    p_value: float | None = None
    verdict: str = "too noisy to claim"


@dataclass(slots=True)
class Comparison:
    a_name: str = ""
    b_name: str = ""
    paired: int = 0
    unpaired_a: int = 0
    unpaired_b: int = 0
    safety: dict[str, tuple[int, int]] = field(default_factory=dict)
    binary: list[BinaryComparison] = field(default_factory=list)
    continuous: list[MetricComparison] = field(default_factory=list)


def pair(a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]) -> tuple[list[Pairing], int, int]:
    """Same spec, same seed, both sides, both valid. Anything else is not a pair.

    Void trials are dropped here rather than at the call site, because a comparison is the one
    place where an unscored row does the most damage: its metrics are whatever the collector could
    reach before the trial fell over, and a paired test would read that as a difference between
    runtimes. `fold` already voids them in the matrix; pairing has to agree.
    """
    def key(r: dict[str, Any]) -> tuple[Any, ...]:
        return (r["workload"], r["workload_variant"], r["cell_id"].split(".", 3)[3], r["spec_hash"], r["seed"])

    left = {key(r): r for r in a_rows if r.get("valid", True)}
    right = {key(r): r for r in b_rows if r.get("valid", True)}
    shared = sorted(set(left) & set(right))
    return (
        [Pairing(k, left[k], right[k]) for k in shared],
        len(left) - len(shared),
        len(right) - len(shared),
    )


def compare(
    a_rows: list[dict[str, Any]],
    b_rows: list[dict[str, Any]],
    *,
    a_name: str = "A",
    b_name: str = "B",
    seed: int = 7,
) -> Comparison:
    pairs, unpaired_a, unpaired_b = pair(a_rows, b_rows)
    out = Comparison(a_name=a_name, b_name=b_name, paired=len(pairs),
                     unpaired_a=unpaired_a, unpaired_b=unpaired_b)
    if not pairs:
        return out

    for name in ("duplicate_effects", "duplicate_receipts", "missing_required"):
        out.safety[name] = (
            sum(p.a["metrics"][name] or 0 for p in pairs),
            sum(p.b["metrics"][name] or 0 for p in pairs),
        )

    for name in ("recovery_rate", "logical_correctness"):
        out.binary.append(_mcnemar(name, pairs))

    rng = random.Random(seed)
    harness = {p.a.get("recovery_mechanism") for p in pairs} | {p.b.get("recovery_mechanism") for p in pairs}
    for name in (
        "recovery_latency_ms",
        "extra_model_calls",
        "extra_tokens",
        "wall_clock_overhead_ms",
    ):
        c = _bootstrap(name, pairs, rng)
        if name in DETECTION_BOUND and "harness" in harness:
            # For a `harness` arm, detection is zero by construction — the supervisor re-invokes it
            # the instant it restarts. Any metric that contains detection time is therefore a
            # statement about the harness rather than the framework when the two are compared:
            # printed, tagged, and never claimed (§14.3). Wall-clock overhead after a fault
            # *contains* the detection wait, so it carries the same confound as latency does.
            c.verdict = "not claimable (detection = harness for one arm)"
        out.continuous.append(c)
    return out


def _mcnemar(metric: str, pairs: list[Pairing]) -> BinaryComparison:
    """Only discordant pairs carry information: a trial both arms passed says nothing about which
    is better, and counting it would dilute the very thing being measured."""
    a_only = sum(1 for p in pairs if p.a["metrics"][metric] and not p.b["metrics"][metric])
    b_only = sum(1 for p in pairs if p.b["metrics"][metric] and not p.a["metrics"][metric])
    c = BinaryComparison(metric=metric, n=len(pairs), a_only=a_only, b_only=b_only)
    discordant = a_only + b_only
    if discordant < MIN_EVENTS:
        c.verdict = f"too noisy to claim ({discordant} discordant pairs)"
        return c
    # Exact binomial, two-sided: under the null each discordant pair is a fair coin.
    k = min(a_only, b_only)
    tail = sum(math.comb(discordant, i) for i in range(k + 1)) / (2**discordant)
    c.p_value = min(1.0, 2 * tail)
    c.verdict = (
        f"{'A' if a_only > b_only else 'B'} better (p={c.p_value:.4f})"
        if c.p_value < 0.05
        else f"too noisy to claim (p={c.p_value:.3f})"
    )
    return c


def _bootstrap(metric: str, pairs: list[Pairing], rng: random.Random) -> MetricComparison:
    deltas = [
        p.a["metrics"][metric] - p.b["metrics"][metric]
        for p in pairs
        if p.a["metrics"].get(metric) is not None and p.b["metrics"].get(metric) is not None
    ]
    c = MetricComparison(metric=metric, n=len(deltas))
    if len(deltas) < MIN_EVENTS:
        c.verdict = f"too noisy to claim ({len(deltas)} paired observations)"
        return c
    c.a_median = statistics.median(
        [p.a["metrics"][metric] for p in pairs if p.a["metrics"].get(metric) is not None]
    )
    c.b_median = statistics.median(
        [p.b["metrics"][metric] for p in pairs if p.b["metrics"].get(metric) is not None]
    )
    c.difference = statistics.median(deltas)
    medians = sorted(
        statistics.median([deltas[rng.randrange(len(deltas))] for _ in deltas])
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    lo = medians[int(0.025 * len(medians))]
    hi = medians[min(len(medians) - 1, int(0.975 * len(medians)))]
    c.ci = (lo, hi)
    # An interval containing zero is a real answer, and at n=30 it is the most common honest one.
    c.verdict = "too noisy to claim" if lo <= 0 <= hi else ("A higher" if lo > 0 else "B higher")
    return c


def render(c: Comparison) -> str:
    out = [
        f"# compare — `{c.a_name}` (A) vs `{c.b_name}` (B)",
        "",
        f"{c.paired} paired trials on (workload, variant, trigger, spec_hash, seed)."
        + (f" Unpaired: {c.unpaired_a} in A, {c.unpaired_b} in B." if c.unpaired_a or c.unpaired_b else ""),
        "",
        "## Safety — counted, never estimated",
        "",
        "| observation | A | B |",
        "|---|---|---|",
    ]
    out += [f"| `{k}` | {a} | {b} |" for k, (a, b) in c.safety.items()]
    out += ["", "## Liveness — McNemar over discordant pairs", "",
            "| metric | A only | B only | verdict |", "|---|---|---|---|"]
    out += [f"| `{b.metric}` | {b.a_only} | {b.b_only} | {b.verdict} |" for b in c.binary]
    out += ["", "## Economy — paired bootstrap on the median difference", "",
            "| metric | A median | B median | A−B | 95% CI | verdict |", "|---|---|---|---|---|---|"]
    for m in c.continuous:
        ci = f"[{m.ci[0]:.1f}, {m.ci[1]:.1f}]" if m.ci else "—"
        out.append(
            f"| `{m.metric}` | {_fmt(m.a_median)} | {_fmt(m.b_median)} | {_fmt(m.difference)} | {ci} | {m.verdict} |"
        )
    out += [
        "",
        "A safety observation is a count of what happened, so it carries no p-value: whether a "
        "runtime filed the issue twice is not a sample from a population. The estimates below it "
        "are, and `too noisy to claim` is a real answer — at thirty seeds it is the most common "
        "honest one, and saying so is the point of printing the interval rather than the point "
        "estimate alone.",
        "",
    ]
    return "\n".join(out)


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"
