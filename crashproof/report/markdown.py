"""The matrix, as a page someone can read (§14.4).

Rows are `(location, fault)`. Columns are runtime configs, each printed under its
`recovery_mechanism` and its declared `claims`, because a verdict without them is not a
comparison — it is a scoreboard with the rules left off.

Every cell shows raw observations next to its verdicts. A reader who distrusts the verdict can
recompute it; a reader who distrusts the harness can find the trial directory from the
counterexample's `(spec_hash, seed)`. That is the whole contamination stance in one table: the
grammar, the workloads, the schedules and the seeds are public, so a runtime that changes to pass
a published schedule has fixed a bug.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from crashproof.report.matrix import CellSummary, wilson
from crashproof.stats.ci import MDD_TABLES

#: Claims are printed under every column, because a verdict without the claim it was judged
#: against is a scoreboard with the rules left off.
SHORT_CLAIM = {
    "none": "none",
    "at_most_once": "at-most-once",
    "at_least_once": "at-least-once",
    "effectively_once": "effectively-once",
    "exactly_once": "exactly-once",
}
SHORT_CLASS = {"PURE": "PURE", "IDEMPOTENT": "IDEM", "EXTERNAL": "EXT", "TRANSACTIONAL": "TXN"}


def render(
    cells: dict[str, CellSummary],
    *,
    workload: str,
    title: str = "matrix v0",
    sources: list[tuple[str, list[dict[str, Any]]]] = (),
) -> str:
    """`sources` is `(results directory, the rows read from it)`: what the provenance names."""
    variants = sorted({c.variant for c in cells.values()})
    columns = sorted({(c.adapter, c.config) for c in cells.values()})
    out: list[str] = [f"# {title}", "", f"Workload `{workload}`. One cell is n **seeds**, not n trials of one seed.", ""]

    for variant in variants:
        band = {k: v for k, v in cells.items() if v.variant == variant}
        if not band:
            continue
        out += _band(band, variant, columns)

    out += _counterexamples(cells)
    out += _provenance(cells, sources)
    return "\n".join(out)


def _band(band: dict[str, CellSummary], variant: str, columns: list[tuple[str, str]]) -> list[str]:
    key_sources = sorted({c.key_source for c in band.values()})
    out = [f"## {variant}  ·  key_source={', '.join(key_sources)}", ""]

    header = ["(location, fault)"] + [f"`{a}.{c}`" for a, c in columns]
    sub = [""] + [_column_note(band, a, c) for a, c in columns]
    out += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), "| " + " | ".join(sub) + " |"]

    triggers = sorted({c.trigger for c in band.values()}, key=lambda t: (t != "baseline", t))
    for trigger in triggers:
        cells_row = [_cell(band.get(f"{a}.{c}.{variant}.{trigger}")) for a, c in columns]
        out.append("| " + " | ".join([f"`{trigger}`", *cells_row]) + " |")
    out.append("")
    return out


def _column_note(band: dict[str, CellSummary], adapter: str, config: str) -> str:
    sample = next((c for c in band.values() if c.adapter == adapter and c.config == config), None)
    if sample is None:
        return "—"
    order = ["PURE", "IDEMPOTENT", "EXTERNAL", "TRANSACTIONAL"]
    claims = " · ".join(
        f"{SHORT_CLASS.get(k, k)} {SHORT_CLAIM.get(v, v)}"
        for k in order
        if (v := sample.claims.get(k)) is not None
    )
    return f"recovery={sample.recovery_mechanism}<br>claims: {claims}"


def _cell(cell: CellSummary | None) -> str:
    if cell is None or cell.n == 0:
        return "—"
    safety = " ".join(
        f"{name}{'✓' if cell.verdicts.get(name) == 'PASS' else '✗' if cell.verdicts.get(name) == 'FAIL' else '·'}"
        # §15.11 rule 3: never omitted from the grid. S7 prints `·` for a workload that gates
        # nothing, which is a different statement from a workload that gates something and passed.
        for name in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "C1")
    )
    lo, hi = wilson(*cell.recovery_rate)
    live = f"L1 {cell.recovery_rate[0]}/{cell.recovery_rate[1]} [{lo:.2f}–{hi:.2f}]"
    raw = f"dup_eff {cell.duplicate_effects} · dup_rcpt {cell.duplicate_receipts}"
    if cell.lost_effects is not None:
        raw += f" · lost {cell.lost_effects}"
    extra = []
    if cell.recovery_latency_ms is not None:
        extra.append(f"lat {cell.recovery_latency_ms / 1000:.1f}s")
    if cell.extra_model_calls is not None:
        extra.append(f"+calls {cell.extra_model_calls:g}")
    if cell.replay_divergence[1]:
        # Printed whenever it is measurable, including the zero — "this runtime never diverged"
        # is the finding in half these cells, and a column that only appears when something went
        # wrong cannot report it.
        extra.append(f"diverged {cell.replay_divergence[0]}/{cell.replay_divergence[1]}")
    if cell.void:
        extra.append(f"void {cell.void}")
    return "<br>".join([safety, live, raw] + ([" · ".join(extra)] if extra else []))


def _pin_value(value: Any) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _counterexamples(cells: dict[str, CellSummary]) -> list[str]:
    rows = [(cell_id, c) for cell_id, c in sorted(cells.items()) if c.counterexamples]
    if not rows:
        return ["## Counterexamples", "", "None. Every safety invariant held in every scored trial.", ""]
    out = ["## Counterexamples", "", "| cell | invariant | spec_hash | seed | trial | detail |", "|---|---|---|---|---|---|"]
    for cell_id, cell in rows:
        for c in cell.counterexamples:
            out.append(
                f"| `{cell_id}` | {c.get('invariant')} | `{c.get('spec_hash', '')[:12]}` | "
                f"{c.get('seed')} | `{c.get('trial_id')}` | {c.get('detail', '')} |"
            )
    out.append("")
    return out


def sources_block(sources: list[tuple[str, list[dict[str, Any]]]]) -> list[str]:
    """Which rows a page was computed from: each results directory, how many rows, and every
    `keel_commit` they ran at, counted. §29.3's go/no-go asks whether a page's commits match its
    rows', which nobody can check on a page that names none.

    The page's only date is the last trial's end, read from the rows, so re-rendering the same rows
    is byte-identical — which is the check CI makes on every published page."""
    out = ["| results | rows | keel_commit |", "|---|---|---|"]
    latest, dirty = 0.0, 0
    for where, rows in sources:
        commits = Counter(r.get("keel_commit") or "(none)" for r in rows)
        dirty += sum(n for commit, n in commits.items() if commit.endswith("-dirty"))
        listed = ", ".join(
            f"`{commit}` ×{n}" + (" **dirty**" if commit.endswith("-dirty") else "")
            for commit, n in sorted(commits.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        out.append(f"| `{where}` | {len(rows)} | {listed} |")
        latest = max([latest, *(float(r.get("ended_at") or 0.0) for r in rows)])
    when = datetime.fromtimestamp(latest, UTC).isoformat(timespec="seconds") if latest else "—"
    out = [f"Rows through {when} (the last trial's end).", "", *out]
    if dirty:
        out += [
            "",
            f"**{dirty} row(s) ran from a dirty tree** (`-dirty`): uncommitted changes were present, "
            "so checking out the commit does not reproduce the code that ran.",
        ]
    return out


def _provenance(
    cells: dict[str, CellSummary], sources: list[tuple[str, list[dict[str, Any]]]] = ()
) -> list[str]:
    # A pin that varies across a config's cells must show both values, not whichever cell was
    # summarised first: `worker_count` is 2 exactly where the zombie cell needs a successor, and a
    # table that hid that would be pinning something the trials did not run.
    pins: dict[str, dict[str, set[str]]] = {}
    for cell in cells.values():
        config = pins.setdefault(f"{cell.adapter}.{cell.config}", {})
        for key, value in cell.config_pin.items():
            config.setdefault(key, set()).add(_pin_value(value))
    out = [
        "## Provenance",
        "",
        *sources_block(sources),
        "",
        "| config | pin |",
        "|---|---|",
    ]
    for name, pin in sorted(pins.items()):
        rendered = ", ".join(
            f"{k}={'|'.join(sorted(v))}" for k, v in sorted(pin.items()) if k != "framework_versions"
        )
        out.append(f"| `{name}` | {rendered} |")
    counts = sorted({c.n for c in cells.values() if c.n})
    if len(counts) > 1:
        out += [
            "",
            f"**Mixed n.** Cells in this report were run at different seed counts ({counts}); each "
            "cell prints its own n in the liveness line. A reduced-n cell is a weaker estimate, "
            "not a different verdict: safety is still PASS only on zero violations in the n that "
            "ran, and the interval beside it widens to say so (§15.3).",
        ]
    out += [
        "",
        "**How to read a cell.** The first line is safety: PASS means zero violations in n, and a "
        "single violation is a FAIL with its counterexample listed above — safety is never a "
        "proportion. The second line is liveness with a Wilson interval. The third is raw "
        "observation, published whatever the verdicts say: `dup_eff` counts effects the World "
        "actually applied more than once, `dup_rcpt` counts requests it received more than once. "
        "The gap between them is what the receiver's idempotency bought, and the runtime gets no "
        "credit for it.",
        "",
        "**Judged against claims.** An arm that declares `at_least_once` and produces a duplicate "
        "has not failed S1; the duplicate is in the table regardless. An arm that declares "
        "`effectively_once` and applies twice has failed, and the seed that did it is named.",
        "",
        # §15.11 rule 6: unconditional, not behind `report --mdd`. The objection this answers —
        # "you only ran it thirty times" — is one a reader has while looking at the page, and an
        # answer that needs a second command to produce is an answer they will not find.
        MDD_TABLES,
        "",
        faq(confirmed=any(c.n > 30 for c in cells.values())),
    ]
    return out


def faq(*, confirmed: bool) -> str:
    """§15.9, printed in every report for the same reason as the MDD tables. The objection has five
    answers and they are different answers — two of them concede the point and say what the numbers
    therefore cannot be used for, which is why the section is a fixture of the page rather than a
    rebuttal kept in reserve.

    Answer 3 describes the confirmation tier, and it is only true of a page that has one: a page
    whose every cell is at the screening n says so instead of claiming a confirmation nobody ran."""
    return FAQ.replace("{confirmation}", CONFIRMED if confirmed else SCREENING_ONLY)


CONFIRMED = """**3. Confirmation is automatic where it matters.** Every non-unanimous cell and every cell under a
claimed difference goes to n = 300 on fresh seeds, together with the arm it is compared against.
Unanimous cells that no claim depends on stay at thirty, because three hundred more of the same
outcome tighten an interval nothing rests on."""

SCREENING_ONLY = """**3. This page is the screening tier only.** Every cell here is at n ≤ 30. §15.3's confirmation
tier — every non-unanimous cell and every cell under a claimed difference re-run at n = 300 on fresh
seeds, together with the arm it is compared against — has not been run for these rows, so no
difference on this page is confirmed."""

FAQ = """### "You only ran this thirty times" (§15.9)

**1. For safety rows the objection points the wrong way.** Thirty passing trials are not a claim of
safety, and this report never makes that claim. One *failing* trial is a proof of a bug with a
reproducible `(spec_hash, seed)`; thirty of them would add nothing. Jepsen finds consensus bugs in a
handful of runs because the faults are aimed at the mechanism rather than sampled from production,
and every trial here is aimed at a named window — `after:tool_effect` with the response held — that
a random production crash would reach rarely.

**2. For estimate rows the printed interval is the answer.** `28/30 [0.79, 0.98]` says exactly what
thirty trials can and cannot exclude, and the MDD table above says what gap would have been visible
at all. Neither is hidden behind a flag.

{confirmation}

**4. The variance being sampled is the right one.** Schedules are seeded and shared between arms, so
the residual variance is the SUT's own internal timing — which is precisely the quantity a
durability claim is about. Thirty samples of "does the reaper beat the zombie" are thirty draws from
the distribution a user would experience.

**5. Everything is reproducible.** Every row carries `(spec_hash, seed, keel_commit)` and its
`config_pin`, framework versions included. `keel_commit` pins the adapters as well as Keel, because
they live in the same repository, and it is marked `-dirty` when the tree had uncommitted changes.
`crashproof verify <dir>/results.jsonl --recheck` re-runs the verifier over each trial's own facts
and fails if a verdict moved or a row cannot be re-verified. Disagreement is settled by running it.
"""
