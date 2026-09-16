"""The placement histogram (§19.5 view 4) and K3's two numbers (§30), over a results directory.

`crashproof placement <results dir>` — not in §25.3's command tree; it is the report-only view §19.5
names, given its own command because it needs the trial directories and a matrix page does not.

Per cell: across the seeds, where each fired fault landed (the attempt that was open, or the last
checkpoint written), and whether it fell inside the window K3 defines — after the World receipt of
the aimed tool and before the SUT's next committed record. A cell whose modal landing is outside
that window is flagged *mis-aimed*: a harness defect, never a runtime finding. Per `(variant,
trigger)`: whether the in-window fraction differs between arms by more than ten points.

It computes what the artefacts can support and says so where they cannot. Rows alone cannot place
a fault — the join needs `facts.json` — and a fault is placeable only where the runtime's committed
record is readable on the trigger's own terms: Keel's journal through the fault row's `sut_ref`,
LangGraph's checkpoints through their SUT-side timestamps. Everything else is counted as
unobservable, never as in or out of the window, and a K3 clause with an unobservable fault in it is
printed as not computable rather than as a verdict.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from crashproof.runner.store import ResultStore, slug
from crashproof.verifier import invariants, views
from crashproof.workloads.spec import load_named

K3_IN_WINDOW = 0.90
K3_BETWEEN_ARMS = 0.10


@dataclass(slots=True)
class CellPlacement:
    cell_id: str
    trials: int = 0
    with_facts: int = 0
    fired: int = 0
    in_window: int = 0
    out_of_window: int = 0
    histogram: Counter = field(default_factory=Counter)
    unobservable: Counter = field(default_factory=Counter)

    @property
    def observable(self) -> int:
        return self.in_window + self.out_of_window

    @property
    def fraction(self) -> float | None:
        """Defined only when every fired fault was placed: a fraction over the placeable subset
        would be a K3 number for trials nobody could see."""
        if not self.fired or self.observable != self.fired:
            return None
        return self.in_window / self.fired

    @property
    def mis_aimed(self) -> bool:
        """Not unimodal at the intended landmark: the commonest landing is outside the window."""
        placed = [(key, n) for key, n in self.histogram.most_common() if key[1] is not None]
        return bool(placed) and placed[0][0][1] is False


def placements(results: Path) -> dict[str, CellPlacement]:
    rows = _latest_valid(ResultStore(results).rows())
    out: dict[str, CellPlacement] = {}
    for row in rows:
        if row["cell_id"].endswith(".baseline"):
            continue
        cell = out.setdefault(row["cell_id"], CellPlacement(row["cell_id"]))
        cell.trials += 1
        path = results / slug(row["cell_id"]) / row["trial_id"] / "facts.json"
        if not path.exists():
            cell.fired += len(row.get("faults") or [])
            cell.unobservable["no facts.json in the trial directory"] += len(row.get("faults") or [])
            continue
        cell.with_facts += 1
        facts = invariants.load(json.loads(path.read_text(encoding="utf8")))
        endpoints = {t.name: t.endpoint for t in load_named(row["workload"]).tools_for(row["workload_variant"])}
        for placed in views.placement(facts, endpoints):
            cell.fired += 1
            cell.histogram[(f"{placed['boundary']} · {placed['where']}", placed["in_window"])] += 1
            if placed["in_window"] is True:
                cell.in_window += 1
            elif placed["in_window"] is False:
                cell.out_of_window += 1
            else:
                cell.unobservable[_why_unobservable(placed)] += 1
    return out


def _latest_valid(rows: Any) -> list[dict[str, Any]]:
    """`fold`'s rule: last write wins per `(cell_id, seed)`, then void trials go."""
    latest = {(r["cell_id"], r["seed"]): r for r in rows}
    return [r for r in latest.values() if r.get("valid", True)]


def _why_unobservable(placed: dict[str, Any]) -> str:
    if placed["boundary"] not in views.WINDOW_BOUNDARIES or not str(placed["landmark"]).startswith("tool:"):
        return f"no K3 window at {placed['boundary']}"
    if placed["join"] == "no journal" and placed["where"] == "unobservable":
        return "runtime side not observable: no journal and no checkpoints exported"
    return f"runtime side not observable: {placed['join']}"


def render(cells: dict[str, CellPlacement], *, sources: list[tuple[str, list[dict[str, Any]]]] = ()) -> str:
    from crashproof.report.markdown import sources_block

    lines = [
        "# Placement — where the faults landed (§19.5 view 4, K3)",
        "",
        "Per cell, across its seeds: where each fired fault landed and whether it fell inside K3's "
        "window — after the World receipt of the aimed tool, before the SUT's next committed record "
        "(for `before:tool_call`, before any receipt). A fault the artefacts cannot place is "
        "*unobservable* and counted as neither; a K3 clause with one in it is not computable.",
        "",
        *sources_block(sources),
        "",
        "## Per cell",
        "",
        "| cell | trials (facts) | fired | in window | K3 ≥ 90 % | histogram | mis-aimed |",
        "|---|---|---|---|---|---|---|",
    ]
    for cell_id, c in sorted(cells.items()):
        histogram = "<br>".join(
            f"{where}{'' if ok is None else ' ✓' if ok else ' ✗'} ×{n}"
            for (where, ok), n in sorted(c.histogram.items(), key=lambda kv: (-kv[1], kv[0][0]))
        ) or "—"
        if c.fraction is None:
            reasons = "; ".join(f"{why} ×{n}" for why, n in sorted(c.unobservable.items()))
            k3 = f"not computable: {c.fired - c.observable} of {c.fired} unobservable ({reasons})"
        else:
            k3 = f"{'PASS' if c.fraction >= K3_IN_WINDOW else '**FAIL**'} ({c.fraction:.0%})"
        lines.append(
            f"| `{cell_id}` | {c.trials} ({c.with_facts}) | {c.fired} | {c.in_window}/{c.observable} "
            f"| {k3} | {histogram} | {'**mis-aimed**' if c.mis_aimed else 'no'} |"
        )

    lines += [
        "",
        "## K3 between arms",
        "",
        "| (variant, trigger) | in-window fraction by arm | K3 ≤ 10 points |",
        "|---|---|---|",
    ]
    groups: dict[str, list[CellPlacement]] = {}
    for cell_id, c in cells.items():
        adapter, config, variant, trigger = cell_id.split(".", 3)
        groups.setdefault(f"{variant} · {trigger}", []).append(c)
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        arms = " · ".join(
            f"`{'.'.join(m.cell_id.split('.', 2)[:2])}` "
            + ("—" if m.fraction is None else f"{m.fraction:.0%}")
            for m in sorted(members, key=lambda m: m.cell_id)
        )
        fractions = [m.fraction for m in members]
        if any(f is None for f in fractions):
            verdict = "not computable: an arm has unobservable faults"
        else:
            spread = max(fractions) - min(fractions)
            verdict = f"{'PASS' if spread <= K3_BETWEEN_ARMS else '**FAIL**'} ({spread * 100:.0f} points)"
        lines.append(f"| {key} | {arms} | {verdict} |")
    lines.append("")
    return "\n".join(lines)
