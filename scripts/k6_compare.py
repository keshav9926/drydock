"""K6's fallback, last clause (§30): the Keel trials re-run at the same `(spec_hash, seed)` after the two
design fixes (c509409, 2ffbe91), against the published rows — the diff, from committed rows only.

    published  bench/results/v1_<set>/results.jsonl   at 251e52d, Keel rows
    re-run     bench/results/k6_<set>/results.jsonl   at the v1 tag (4b8eb62)

Pairs on `(cell_id, seed)`, last write wins (a re-take supersedes); a pair whose spec_hash differs, or
that is void on either side, is counted and not compared. Prints every verdict that flipped, every
status that moved, and every count whose sum over a cell's paired trials moved. Sizes and
latencies (`storage_overhead`, `*_ms`) move with the host on every re-run and are not printed.

    uv run python scripts/k6_compare.py [set ...]
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"
SETS = ("w1_shim", "w1_proxy", "w5", "w5_pre", "reask", "w3", "w7")


def rows(path: Path) -> dict[tuple[str, int], dict]:
    out = {}
    for line in path.read_text(encoding="utf8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["cell_id"].startswith("keel."):
                out[(r["cell_id"], r["seed"])] = r
    return out


def compare(name: str) -> int:
    pub = rows(RESULTS / f"v1_{name}" / "results.jsonl")
    new = rows(RESULTS / f"k6_{name}" / "results.jsonl")
    commits = collections.Counter(r.get("keel_commit") for r in new.values())
    paired, mismatch, void, changed = 0, 0, 0, 0
    flips: collections.Counter = collections.Counter()
    sums: dict[tuple[str, str], list[float]] = collections.defaultdict(lambda: [0.0, 0.0])
    lines = []
    for key in sorted(new):
        p, n = pub.get(key), new[key]
        if p is None:
            continue
        if p["spec_hash"] != n["spec_hash"]:
            mismatch += 1
            continue
        if not (p["valid"] and n["valid"]):
            void += 1
            continue
        paired += 1
        diff = {k: (p["verdicts"].get(k), n["verdicts"].get(k))
                for k in sorted(set(p["verdicts"]) | set(n["verdicts"]))
                if p["verdicts"].get(k) != n["verdicts"].get(k)}
        for k, ab in diff.items():
            flips[(k, *ab)] += 1
        if diff or p["status"] != n["status"]:
            changed += 1
            lines.append(f"   trial {key[0]} seed {key[1]}: status {p['status']} -> {n['status']} {diff or ''}")
        for m in set(p["metrics"]) | set(n["metrics"]):
            a, b = p["metrics"].get(m), n["metrics"].get(m)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
                sums[(key[0], m)][0] += a
                sums[(key[0], m)][1] += b
    print(f"== {name}: {len(pub)} published Keel rows, {len(new)} re-run at {dict(commits)}")
    print(f"   paired {paired}, spec_hash mismatch {mismatch}, void on either side {void}")
    for (k, a, b), c in sorted(flips.items(), key=str):
        print(f"   verdict {k}: {a} -> {b} x{c}")
    if lines:
        print("\n".join(lines))
    for (cell, m), (a, b) in sorted(sums.items()):
        if round(a, 6) != round(b, 6) and not m.endswith("_ms") and m != "storage_overhead":
            print(f"   sum {m:24s} {a:g} -> {b:g}   {cell}")
    return changed


if __name__ == "__main__":
    total = sum(compare(name) for name in (sys.argv[1:] or SETS))
    print(f"trials with a verdict or status change: {total}")
