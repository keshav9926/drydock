"""Paired comparison between two arms (§15.5–§15.8, §24.6).

Pairing is on `(workload, variant, trigger, spec_hash, seed)` — the same spec and the same seed on
both sides — because that is the only way a difference is a difference between *runtimes* rather
than between the schedules they happened to draw. Unpaired rows are reported as unpaired, never
silently averaged in.

Two kinds of statement, computed differently, for the same reason they are typeset differently in
the matrix:

**Safety is counted, not estimated.** Duplicate and lost effects are reported as totals with their
counterexamples. There is no p-value on "did this runtime file the issue twice", because that is an
observation, not a sample from a population.

**Liveness and economy are estimated, one `(location, fault)` cell at a time.** A comparison is
made per trigger and never pooled across triggers: `kill @ after:tool_effect` and `pause_past_ttl`
are different questions, and an average over them is an answer to neither. Binary outcomes get
McNemar's exact test over the discordant pairs; continuous ones get the exact sign test for the
p-value and a paired bootstrap for the interval.

The verdict is `too noisy to claim` whenever any of §15.8's five rules fails — the CI contains
zero, too few events, fewer than six discordant pairs, the MDD at this `n` exceeds the observed
effect, or the Holm-adjusted p exceeds 0.05 within its family. The failing rule is named. At thirty
seeds this is the most common honest answer, and the point estimates stay on the page either way:
a rule that fails takes away the verb, never the numbers.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Any

from crashproof.stats.ci import (
    DISCORDANT_FLOOR,
    MDD_TABLES,
    exact_binomial,
    holm,
    mdd_paired_binary,
    mdd_paired_continuous,
    paired_bootstrap,
)

#: A family needs enough events to say anything at all; below this the answer is that the trial
#: count was too small, not that the runtimes are the same (§15.8 rule 2). An *event* is a
#: realisation of the phenomenon in the rate's own denominator, not the raw trial count.
MIN_EVENTS = 5

TOO_NOISY = "too noisy to claim"

#: Metrics whose value includes the runtime's own detection wait. Comparing them against an arm
#: the harness re-invokes is comparing against zero detection by construction.
DETECTION_BOUND = frozenset({"recovery_latency_ms", "wall_clock_overhead_ms"})

BINARY_METRICS = ("recovery_rate", "logical_correctness", "replay_divergence")
#: Binary metrics where a 1 is a *defect* rather than a success. `recovery_rate` and
#: `logical_correctness` count good outcomes; `replay_divergence` counts a run that took a path its
#: own journal does not describe. Without this the verdict reads the polarity off the count and
#: reports the arm that diverged in every trial as the better one — which is not a rounding error
#: in a published table, it is the opposite claim.
DEFECT_METRICS = frozenset({"replay_divergence"})
CONTINUOUS_METRICS = ("recovery_latency_ms", "extra_model_calls", "extra_tokens", "wall_clock_overhead_ms")
SAFETY_METRICS = ("duplicate_effects", "duplicate_receipts", "missing_required")


@dataclass(slots=True)
class Pairing:
    key: tuple[Any, ...]
    a: dict[str, Any]
    b: dict[str, Any]

    @property
    def cell(self) -> str:
        """The `(location, fault)` this pair belongs to: variant and trigger, which is the row a
        family is made of. The seed and the spec hash are what was paired *away*."""
        return f"{self.key[1]}·{self.key[2]}"


@dataclass(slots=True)
class Row:
    """One printed comparison. Binary and continuous rows share a shape because they share a
    verdict rule, and because the report prints them in the same column layout."""

    metric: str
    cell: str
    n: int = 0
    #: binary: discordant counts. continuous: the sign test's positive and negative differences.
    a_only: int = 0
    b_only: int = 0
    a_median: float | None = None
    b_median: float | None = None
    difference: float | None = None
    ci: tuple[float, float] | None = None
    p_value: float | None = None
    p_holm: float | None = None
    mdd: float | None = None
    verdict: str = TOO_NOISY
    #: The §15.8 rule that took the verb away, or "" when a claim was made.
    rule: str = ""

    def claimed(self) -> bool:
        return not self.verdict.startswith((TOO_NOISY, "not claimable"))


@dataclass(slots=True)
class Family:
    """One `(metric, workload, variant)` table. Holm is applied across its rows and nowhere else:
    this is the unit a reader consumes as a single claim, so it is the unit at which the
    family-wise error rate is controlled (§15.6)."""

    metric: str
    workload: str
    variant: str
    rows: list[Row] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.metric} · {self.workload} · {self.variant}"


@dataclass(slots=True)
class Comparison:
    a_name: str = ""
    b_name: str = ""
    paired: int = 0
    unpaired_a: int = 0
    unpaired_b: int = 0
    safety: dict[str, tuple[int, int]] = field(default_factory=dict)
    families: list[Family] = field(default_factory=list)

    @property
    def rows(self) -> list[Row]:
        return [r for f in self.families for r in f.rows]


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

    for name in SAFETY_METRICS:
        out.safety[name] = (
            sum(p.a["metrics"][name] or 0 for p in pairs),
            sum(p.b["metrics"][name] or 0 for p in pairs),
        )

    rng = random.Random(seed)
    harness = {p.a.get("recovery_mechanism") for p in pairs} | {p.b.get("recovery_mechanism") for p in pairs}
    # A family is one (metric, workload, variant) table; its rows are the triggers. Grouping is by
    # the pair key's own fields so a comparison can never silently span two workloads.
    groups: dict[tuple[str, str], list[Pairing]] = {}
    for p in pairs:
        groups.setdefault((p.key[0], p.key[1]), []).append(p)

    for metric in BINARY_METRICS:
        for (workload, variant), members in sorted(groups.items()):
            family = Family(metric=metric, workload=workload, variant=variant)
            for cell in sorted({p.cell for p in members}):
                family.rows.append(_mcnemar(metric, [p for p in members if p.cell == cell], cell))
            _holm(family)
            out.families.append(family)

    for metric in CONTINUOUS_METRICS:
        for (workload, variant), members in sorted(groups.items()):
            family = Family(metric=metric, workload=workload, variant=variant)
            for cell in sorted({p.cell for p in members}):
                row = _paired(metric, [p for p in members if p.cell == cell], cell, rng)
                if metric in DETECTION_BOUND and "harness" in harness:
                    # For a `harness` arm, detection is zero by construction — the supervisor
                    # re-invokes it the instant it restarts. Any metric that contains detection
                    # time is therefore a statement about the harness rather than the framework
                    # when the two are compared: printed, tagged, and never claimed (§14.3).
                    # Wall-clock overhead after a fault *contains* the detection wait, so it
                    # carries the same confound as latency does.
                    row.verdict = "not claimable (detection = harness for one arm)"
                    row.rule = "confound"
                family.rows.append(row)
            _holm(family)
            out.families.append(family)
    return out


def _holm(family: Family) -> None:
    """§15.8 rule 5, applied after rules 1–4 and only to rows those rules left standing.

    A row already disqualified is not a hypothesis test, so it does not count toward `m` — the
    same reason §15.6 excludes `N/A` cells. Including them would inflate the correction with rows
    that were never going to make a claim, which penalises the family for its own honesty.
    """
    live = [r for r in family.rows if r.p_value is not None and r.claimed()]
    if not live:
        return
    for row, adjusted in zip(live, holm([r.p_value or 1.0 for r in live]), strict=True):
        row.p_holm = adjusted
        if adjusted >= 0.05:
            row.verdict = f"{TOO_NOISY} (Holm p={adjusted:.3f} in a family of {len(live)})"
            row.rule = "5 · Holm"


def _mcnemar(metric: str, pairs: list[Pairing], cell: str) -> Row:
    """Only discordant pairs carry information: a trial both arms passed says nothing about which
    is better, and counting it would dilute the very thing being measured."""
    a_only = sum(1 for p in pairs if p.a["metrics"].get(metric) and not p.b["metrics"].get(metric))
    b_only = sum(1 for p in pairs if p.b["metrics"].get(metric) and not p.a["metrics"].get(metric))
    n = len(pairs)
    r = Row(metric=metric, cell=cell, n=n, a_only=a_only, b_only=b_only)
    r.a_median = sum(1 for p in pairs if p.a["metrics"].get(metric))
    r.b_median = sum(1 for p in pairs if p.b["metrics"].get(metric))
    discordant = a_only + b_only
    if discordant < DISCORDANT_FLOOR:
        # Rule 3, not rule 2: the five-event floor exists because the normal approximation is
        # meaningless there, and the exact test does not use one. What stops a small discordant
        # count here is that the exact two-sided p cannot reach 0.05 at all below six.
        r.verdict = f"{TOO_NOISY} ({discordant} discordant pairs)"
        r.rule = f"3 · fewer than {DISCORDANT_FLOOR} discordant"
        return r
    r.p_value = exact_binomial(a_only, b_only)
    r.difference = (a_only - b_only) / n
    r.mdd = mdd_paired_binary(discordant / n, n)
    if r.mdd is not None and abs(r.difference) < r.mdd:
        r.verdict = f"{TOO_NOISY} (δ={r.difference:+.2f} below MDD {r.mdd:.2f} at n={n})"
        r.rule = "4 · below MDD"
    elif r.p_value < 0.05:
        more = "A" if a_only > b_only else "B"
        winner = {"A": "B", "B": "A"}[more] if metric in DEFECT_METRICS else more
        r.verdict = f"{winner} better (p={r.p_value:.4f})"
    else:
        r.verdict = f"{TOO_NOISY} (p={r.p_value:.3f})"
        r.rule = "1 · p ≥ 0.05"
    return r


def _paired(metric: str, pairs: list[Pairing], cell: str, rng: random.Random) -> Row:
    """Exact sign test for the p-value, paired bootstrap for the interval.

    The sign test rather than a t-test because these distributions are not normal and `n` is 30;
    exact rather than approximate for the same reason the binary branch is. It is the same
    `exact_binomial` over the same kind of coin — here the coin is the sign of each per-seed
    difference, and a zero difference is no evidence either way, so it is not a trial.
    """
    deltas = [
        p.a["metrics"][metric] - p.b["metrics"][metric]
        for p in pairs
        if p.a["metrics"].get(metric) is not None and p.b["metrics"].get(metric) is not None
    ]
    r = Row(metric=metric, cell=cell, n=len(deltas))
    if len(deltas) < MIN_EVENTS:
        r.verdict = f"{TOO_NOISY} ({len(deltas)} paired observations)"
        r.rule = f"2 · fewer than {MIN_EVENTS} events"
        return r
    r.a_median = statistics.median(
        [p.a["metrics"][metric] for p in pairs if p.a["metrics"].get(metric) is not None]
    )
    r.b_median = statistics.median(
        [p.b["metrics"][metric] for p in pairs if p.b["metrics"].get(metric) is not None]
    )
    r.difference, lo, hi = paired_bootstrap(deltas, rng)
    r.ci = (lo, hi)
    r.a_only = sum(1 for d in deltas if d > 0)
    r.b_only = sum(1 for d in deltas if d < 0)
    r.p_value = exact_binomial(r.a_only, r.b_only)
    sigma = statistics.stdev(deltas) if len(deltas) > 1 else 0.0
    r.mdd = mdd_paired_continuous(len(deltas), sigma)
    if lo <= 0 <= hi:
        # An interval containing zero is a real answer, and at n=30 it is the most common honest
        # one — which is why the interval is printed rather than the point estimate alone.
        r.verdict = TOO_NOISY
        r.rule = "1 · CI contains 0"
    elif r.mdd is not None and abs(r.difference) < r.mdd:
        r.verdict = f"{TOO_NOISY} (|Δ| below MDD {r.mdd:.1f} at n={len(deltas)})"
        r.rule = "4 · below MDD"
    elif r.p_value >= 0.05:
        r.verdict = f"{TOO_NOISY} (sign test p={r.p_value:.3f})"
        r.rule = "1 · p ≥ 0.05"
    else:
        r.verdict = "A higher" if lo > 0 else "B higher"
    return r


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

    for family in c.families:
        if not family.rows:
            continue
        binary = family.metric in BINARY_METRICS
        out += [
            "",
            f"## {family.label}",
            "",
            ("| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |" if binary
             else "| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |"),
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in family.rows:
            left, right, middle = (
                (f"{int(r.a_median or 0)}/{r.n}", f"{int(r.b_median or 0)}/{r.n}",
                 f"{_fmt(r.difference, 2)} | {r.a_only}/{r.b_only}")
                if binary
                else (_fmt(r.a_median), _fmt(r.b_median),
                      f"{_fmt(r.difference)} | " + (f"[{r.ci[0]:.1f}, {r.ci[1]:.1f}]" if r.ci else "—"))
            )
            out.append(
                f"| `{r.cell}` (n={r.n}) | {left} | {right} | {middle} | "
                f"{_p(r.p_value)} | {_p(r.p_holm)} | {_fmt(r.mdd, 2)} | {r.verdict} |"
            )

    out += [
        "",
        "A safety observation is a count of what happened, so it carries no p-value: whether a "
        "runtime filed the issue twice is not a sample from a population. The estimates above it "
        "are, and every one of them is made per `(location, fault)` cell — averaging a kill at "
        "`after:tool_effect` together with a `pause_past_ttl` answers neither question. Holm runs "
        "across the cells of one metric table and nowhere else (§15.6); rows already disqualified "
        "by rules 1–4 are not hypothesis tests and do not count toward `m`.",
        "",
        "`too noisy to claim` is a real answer — at thirty seeds it is the most common honest one, "
        "and the failing rule is named beside it. The point estimate, the interval and the "
        "adjusted p stay on the page whatever the verdict: a rule that fails takes away the verb, "
        "never the numbers.",
        "",
        MDD_TABLES,
    ]
    return "\n".join(out)


def _fmt(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _p(value: float | None) -> str:
    return "—" if value is None else (f"{value:.4f}" if value < 0.001 else f"{value:.3f}")
