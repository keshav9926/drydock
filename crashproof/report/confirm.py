"""The confirmation tier's plan (§15.3): which cells go to n = 300 on fresh seeds, and the commands.

Selection is §15.3's flowchart and decision list, and nothing more:

- **Safety rows are never confirmed.** S*, C* and L* verdicts are PASS or FAIL with counterexamples
  (§15.4); more trials of a PASS prove nothing and a FAIL is already proven. They select nothing.
- **A binary estimate that is not unanimous at screening is confirmed** — `recovery_rate`,
  `logical_correctness`, `replay_divergence`, `ambiguity_surfacing_rate`, `wait_durability`
  (§15.5's list), anywhere strictly between 0/n and n/n.
- **Any metric under a claimed difference is confirmed**: a `compare` row whose verdict is a verb —
  neither `too noisy to claim` nor `not claimable` — re-derived from the rows with `compare()` itself,
  for the arm pairs a page claims about (`claims`). Continuous and degenerate-count metrics are
  confirmed only this way; a zero-variance continuous metric is unanimous and never claimed.
- **What runs**: the triggering cell, Keel's cell at the same `(variant, location, fault)` — so the
  paired comparison has both arms on the same fresh seeds — and the other arm of a claim. Nothing else
  in the family. Plus each confirmed fault cell's own baseline at the same seeds, which is not a family
  member but the τ₀ its delta metrics are paired against (§15.1); without it `extra_model_calls`,
  `replay_divergence` and `wall_clock_overhead_ms` are undefined at the confirmation tier.

Seeds are `base … base+n−1` with `base ≥ CONFIRMATION_BASE_SEED`, which is how every page tells the
tiers apart (`matrix.is_confirmation`). The plan is written, never run: running it is `bench`.
"""

from __future__ import annotations

import fnmatch
import statistics
from pathlib import Path
from typing import Any

from crashproof.report.compare import compare
from crashproof.report.matrix import CONFIRMATION_BASE_SEED, is_confirmation

CONFIRMATION_SEEDS = 300
#: Per trial, outside `wall_ms`: the World, the SUT's dependency (a database, a server) and teardown.
SETUP_S = 3.0
BINARY_METRICS = ("recovery_rate", "logical_correctness", "replay_divergence",
                  "ambiguity_surfacing_rate", "wait_durability")
#: restate-sdk has no Windows wheel: its cells run the whole harness under WSL.
WSL_ADAPTERS = frozenset({"restate"})


def screening_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`fold`'s rule — last write per `(cell_id, seed)`, void rows out — over the screening tier."""
    latest = {(r["cell_id"], r["seed"]): r for r in rows}
    return [r for r in latest.values() if r.get("valid", True) and not is_confirmation(r)]


def select(rows: list[dict[str, Any]], claims: list[tuple[str, str]], *, seed: int = 7) -> dict[str, list[str]]:
    """`cell_id → why it is confirmed`, over one results file's screening rows."""
    screening = screening_rows(rows)
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in screening:
        by_cell.setdefault(r["cell_id"], []).append(r)
    picks: dict[str, list[str]] = {}

    def add(cell_id: str, why: str) -> None:
        reasons = picks.setdefault(cell_id, [])
        if why not in reasons:
            reasons.append(why)

    def with_keel(cell_id: str, why: str) -> None:
        add(cell_id, why)
        _, _, variant, trigger = cell_id.split(".", 3)
        for twin in sorted(by_cell):
            adapter, _, v, t = twin.split(".", 3)
            if adapter == "keel" and (v, t) == (variant, trigger) and twin != cell_id:
                add(twin, f"Keel's arm at the same (variant, location, fault) as `{cell_id}`")

    for cell_id, group in sorted(by_cell.items()):
        for metric in BINARY_METRICS:
            values = [r["metrics"].get(metric) for r in group if r["metrics"].get(metric) is not None]
            hits = sum(1 for v in values if v)
            if values and 0 < hits < len(values):
                with_keel(cell_id, f"{metric} {hits}/{len(values)} at screening: not unanimous")

    for a_glob, b_glob in claims:
        a = [r for r in screening if fnmatch.fnmatch(r["cell_id"], a_glob)]
        b = [r for r in screening if fnmatch.fnmatch(r["cell_id"], b_glob)]
        for family in compare(a, b, a_name=a_glob, b_name=b_glob, seed=seed).families:
            for row in family.rows:
                if not row.claimed():
                    continue
                variant, trigger = row.cell.split("·", 1)
                why = f"claimed: `{a_glob}` vs `{b_glob}` on {row.metric} — {row.verdict}"
                for cell_id in sorted({r["cell_id"] for r in a + b
                                       if r["workload"] == family.workload and r["workload_variant"] == variant
                                       and r["cell_id"].split(".", 3)[3] == trigger}):
                    with_keel(cell_id, why)

    for cell_id in sorted(picks):
        adapter, config, variant, trigger = cell_id.split(".", 3)
        base = f"{adapter}.{config}.{variant}.baseline"
        if trigger != "baseline" and base in by_cell:
            add(base, f"τ₀ for `{cell_id}`: the baseline its delta metrics are paired against at the same seeds")
    return picks


def spec_index(specs: Path) -> dict[tuple[str, str], list[str]]:
    """`(cell_id, spec_hash) → the matrix files that declare that cell with that spec`."""
    from crashproof.runner.bench import Matrix

    index: dict[tuple[str, str], list[str]] = {}
    for path in sorted(specs.glob("*.yaml")):
        try:
            cells = Matrix.load(path).cells()
        except Exception:  # noqa: BLE001 - a file in the directory that is not a matrix
            continue
        for cell in cells:
            index.setdefault((cell.id, cell.spec.spec_hash), []).append(path.as_posix())
    return index


def plan(
    sources: list[tuple[str, list[dict[str, Any]]]],
    claims: list[tuple[str, str]],
    *,
    n: int = CONFIRMATION_SEEDS,
    base_seed: int = CONFIRMATION_BASE_SEED,
    specs: Path = Path("bench/specs"),
) -> dict[str, Any]:
    """The plan for `(results.jsonl path, its rows)` sources: cells, reasons, spec files, commands."""
    index = spec_index(specs)
    out_sources, total_cells, total_trials, total_s = [], 0, 0, 0.0
    for where, rows in sources:
        picks = select(rows, claims)
        screening = screening_rows(rows)
        hashes: dict[str, set[str]] = {}
        walls: dict[str, list[float]] = {}
        for r in screening:
            hashes.setdefault(r["cell_id"], set()).add(r["spec_hash"])
            walls.setdefault(r["cell_id"], []).append(float(r.get("wall_ms") or 0.0) / 1000)
        # Where a cell's spec is declared by several matrix files, the one that declares the most of
        # this results file's cells is the one it ran from.
        coverage: dict[str, int] = {}
        for cell_id, hs in hashes.items():
            for h in hs:
                for path in index.get((cell_id, h), []):
                    coverage[path] = coverage.get(path, 0) + 1
        cells, groups = [], {}
        for cell_id in sorted(picks):
            if len(hashes[cell_id]) > 1:
                picks[cell_id].append(f"WARNING: {len(hashes[cell_id])} spec hashes in its screening rows")
            spec_hash = sorted(hashes[cell_id])[-1]
            candidates = index.get((cell_id, spec_hash), [])
            spec = max(candidates, key=lambda p: (coverage.get(p, 0), p)) if candidates else None
            host = "wsl" if cell_id.split(".", 1)[0] in WSL_ADAPTERS else "windows"
            wall = statistics.mean(walls[cell_id])
            cells.append({
                "cell": cell_id,
                "spec": spec or f"NOT FOUND: no bench/specs file declares this cell with spec_hash {spec_hash[:12]}",
                "spec_hash": spec_hash,
                "host": host,
                "screening_n": len(walls[cell_id]),
                "screening_mean_wall_s": round(wall, 2),
                "why": picks[cell_id],
            })
            if spec is not None:
                group = groups.setdefault((spec, host), {"cells": [], "seconds": 0.0})
                group["cells"].append(cell_id)
                group["seconds"] += n * (wall + SETUP_S)
        name = Path(where).parent.name
        commands = []
        for (spec, host), group in sorted(groups.items()):
            out_dir = f"bench/results/{name}_confirm" + ("_wsl" if host == "wsl" else "")
            commands.append({
                "spec": spec,
                "host": host,
                "cells": len(group["cells"]),
                "trials": len(group["cells"]) * n,
                "estimate_hours": round(group["seconds"] / 3600, 1),
                "command": " ".join([
                    "uv run crashproof bench", f"--matrix {spec}",
                    *(f"--cells '{c}'" for c in group["cells"]),
                    f"--seeds {n} --base-seed {base_seed} --out {out_dir}",
                ]),
            })
        seconds = sum(g["seconds"] for g in groups.values())
        out_sources.append({
            "results": where,
            "screening_rows": len(screening),
            "cells": len(cells),
            "trials": len(cells) * n,
            "estimate_hours": round(seconds / 3600, 1),
            "confirm": cells,
            "commands": commands,
        })
        total_cells += len(cells)
        total_trials += len(cells) * n
        total_s += seconds
    return {
        "tier_rule": f"a row whose seed is >= {CONFIRMATION_BASE_SEED} is confirmation tier; below it, screening",
        "confirmation": {"base_seed": base_seed, "seeds": n, "seed_range": [base_seed, base_seed + n - 1]},
        "claims": [f"{a}:{b}" for a, b in claims],
        "estimate": f"per cell: n x (the cell's mean screening wall_ms + {SETUP_S:g} s setup), serial",
        "total": {"cells": total_cells, "trials": total_trials, "estimate_hours": round(total_s / 3600, 1)},
        "sources": out_sources,
    }


HEADER = """\
# The confirmation tier's plan (§15.3), written by `crashproof confirm`; regenerate, never hand-edit.
#
# Selection: a binary estimate not unanimous at screening; any metric under a claimed difference for
# the `claims` arm pairs (re-derived with compare()); Keel's cell at the same (variant, location,
# fault); and each confirmed fault cell's baseline, the τ₀ its delta metrics are paired against.
# Safety verdicts (S*, C*, L*) select nothing.
#
# Running it is `bench`: one serial process per command (shard with --cells into separate --out dirs
# to parallelise), re-issued with --resume when a long run is killed for memory. `host: wsl` commands
# run from the WSL clone (restate-sdk has no Windows wheel). Then put each confirmation results.jsonl
# beside its screening rows — `cat` both into one directory — and `crashproof report` / `compare`
# report every confirmed cell at the confirmation n, with its screening numbers in an appendix.
"""


def dump(doc: dict[str, Any]) -> str:
    import yaml

    return HEADER + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=10_000)
