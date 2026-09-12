"""Folding trial rows into cells (§14.4, §15.4).

Two kinds of statement live in a cell and they are computed differently on purpose:

**Safety is not a proportion.** S1–S5 are PASS (0 violations in n) or FAIL with the list of
counterexamples. "29 of 30" is not a safety result, it is a safety failure with a suspiciously
precise description — one violation is a FAIL, and the counterexample's `(spec_hash, seed)` is
printed so anyone can reproduce it.

**Liveness and economy are estimates.** Proportions and medians, from the same n.

A cell whose trials are invalid — a fault row recorded for a fault that did not happen — is voided
rather than scored, and the void rate is published beside the cell so nobody has to guess how much
was thrown away.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from crashproof.verifier.invariants import MVP_INVARIANTS


@dataclass(slots=True)
class CellSummary:
    cell_id: str
    adapter: str
    config: str
    variant: str
    trigger: str
    key_source: str = ""
    recovery_mechanism: str = ""
    claims: dict[str, str] = field(default_factory=dict)
    n: int = 0
    void: int = 0
    verdicts: dict[str, str] = field(default_factory=dict)
    counterexamples: list[dict[str, Any]] = field(default_factory=list)
    recovery_rate: tuple[int, int] = (0, 0)
    logical_correctness: tuple[int, int] = (0, 0)
    #: `(diverged, measurable)`. Measurable only where a paired baseline exists, so the denominator
    #: is not `n` — a cell with no baseline has nothing to have diverged *from*.
    replay_divergence: tuple[int, int] = (0, 0)
    duplicate_effects: int = 0
    duplicate_receipts: int = 0
    lost_effects: int | None = None
    missing_required: int = 0
    recovery_latency_ms: float | None = None
    extra_model_calls: float | None = None
    extra_tokens: float | None = None
    wall_clock_overhead_ms: float | None = None
    storage_overhead: float | None = None
    spec_hashes: set[str] = field(default_factory=set)
    config_pin: dict[str, Any] = field(default_factory=dict)


def fold(rows: list[dict[str, Any]]) -> dict[str, CellSummary]:
    """One cell is one seed's trial, once.

    The store is append-only, so a `(cell_id, seed)` can appear more than once — a void trial and
    the `--resume` that re-took it, or two bench processes that overlapped. Last write wins, which
    is the ordering resume already relies on: the retake is appended after the row it replaces.
    Without this a re-taken seed is counted twice, and n is larger than the number of seeds that
    ran — which is a published number, not an internal one.
    """
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        latest[(row["cell_id"], row["seed"])] = row
    cells: dict[str, list[dict[str, Any]]] = {}
    for row in latest.values():
        cells.setdefault(row["cell_id"], []).append(row)
    return {cell_id: _summarise(cell_id, group) for cell_id, group in cells.items()}


def _summarise(cell_id: str, rows: list[dict[str, Any]]) -> CellSummary:
    parts = cell_id.split(".")
    head = rows[0]
    valid = [r for r in rows if r.get("valid", True)]
    s = CellSummary(
        cell_id=cell_id,
        adapter=parts[0] if parts else "",
        config=parts[1] if len(parts) > 1 else "",
        variant=parts[2] if len(parts) > 2 else "",
        trigger=".".join(parts[3:]) if len(parts) > 3 else "",
        key_source=head.get("key_source", ""),
        recovery_mechanism=head.get("recovery_mechanism", ""),
        claims=head.get("claims", {}),
        n=len(valid),
        void=len(rows) - len(valid),
        spec_hashes={r["spec_hash"] for r in rows},
        config_pin=head.get("config_pin", {}),
    )
    if not valid:
        return s

    # --- safety: a single violation is a FAIL, and it names itself -----------
    for name in MVP_INVARIANTS:
        seen = [r["verdicts"].get(name, "N/A") for r in valid]
        if all(v == "N/A" for v in seen):
            s.verdicts[name] = "N/A"
        elif any(v == "FAIL" for v in seen):
            s.verdicts[name] = "FAIL"
        else:
            s.verdicts[name] = "PASS"
    s.counterexamples = [
        {"spec_hash": r["spec_hash"], "seed": r["seed"], "trial_id": r["trial_id"], **c}
        for r in valid
        for c in r.get("counterexamples", [])
    ]

    # --- estimates -----------------------------------------------------------
    m = [r["metrics"] for r in valid]
    s.recovery_rate = (sum(x["recovery_rate"] for x in m), len(m))
    s.logical_correctness = (sum(x["logical_correctness"] for x in m), len(m))
    rd = [x["replay_divergence"] for x in m if x.get("replay_divergence") is not None]
    s.replay_divergence = (sum(rd), len(rd))
    s.duplicate_effects = sum(x["duplicate_effects"] for x in m)
    s.duplicate_receipts = sum(x["duplicate_receipts"] for x in m)
    s.missing_required = sum(x["missing_required"] for x in m)
    lost = [x["lost_effects"] for x in m if x["lost_effects"] is not None]
    s.lost_effects = sum(lost) if lost else None
    s.recovery_latency_ms = _median(m, "recovery_latency_ms")
    s.extra_model_calls = _median(m, "extra_model_calls")
    s.extra_tokens = _median(m, "extra_tokens")
    s.wall_clock_overhead_ms = _median(m, "wall_clock_overhead_ms")
    s.storage_overhead = _median(m, "storage_overhead")
    return s


def _median(metrics: list[dict[str, Any]], key: str) -> float | None:
    values = [x[key] for x in metrics if x.get(key) is not None]
    return statistics.median(values) if values else None


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
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
