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

from datetime import UTC, datetime
from typing import Any

from crashproof.report.matrix import CellSummary, wilson

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


def render(cells: dict[str, CellSummary], *, workload: str, title: str = "matrix v0") -> str:
    variants = sorted({c.variant for c in cells.values()})
    columns = sorted({(c.adapter, c.config) for c in cells.values()})
    out: list[str] = [f"# {title}", "", f"Workload `{workload}`. One cell is n **seeds**, not n trials of one seed.", ""]

    for variant in variants:
        band = {k: v for k, v in cells.items() if v.variant == variant}
        if not band:
            continue
        out += _band(band, variant, columns)

    out += _counterexamples(cells)
    out += _provenance(cells)
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
        for name in ("S1", "S2", "S3", "S4", "S5")
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
    if cell.void:
        extra.append(f"void {cell.void}")
    return "<br>".join([safety, live, raw] + ([" · ".join(extra)] if extra else []))


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


def _provenance(cells: dict[str, CellSummary]) -> list[str]:
    pins = {}
    for cell in cells.values():
        pins.setdefault(f"{cell.adapter}.{cell.config}", cell.config_pin)
    out = [
        "## Provenance",
        "",
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')}.",
        "",
        "| config | pin |",
        "|---|---|",
    ]
    for name, pin in sorted(pins.items()):
        rendered = ", ".join(f"{k}={v}" for k, v in sorted(pin.items()) if k != "framework_versions")
        out.append(f"| `{name}` | {rendered} |")
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
    ]
    return out
