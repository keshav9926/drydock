"""The MVP metric set (§14.3, §27.8).

Every delta metric is paired against τ₀ — the no-fault baseline trial for the same
`(config, workload, variant, key_source, seed)`. That pairing is why the eight baseline cells ship
with the matrix rather than after it: without τ₀, `extra_model_calls` and `wall_clock_overhead` are
not merely imprecise, they are undefined.

Two time anchors are defined so that every arm's number means the same thing:

    t_fault   the last fault row's `trigger_observed_at`
    t_live    the first SUT-originated World request after the restart that is not a replay

`t_restart` sits between them and happens at *harness* speed for every arm, so it is printed and
excluded from cross-arm comparison. Measuring Keel from `RECOVERY_COMPLETED` while measuring
another runtime at the wire would be measuring one from inside its own process and the other from
outside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Metrics:
    recovery_rate: int = 0
    recovery_detect_ms: float | None = None
    recovery_latency_ms: float | None = None
    time_to_first_live_step_ms: float | None = None
    logical_correctness: int = 0
    duplicate_effects: int = 0
    duplicate_receipts: int = 0
    lost_effects: int | None = None
    missing_required: int = 0
    extra_model_calls: int | None = None
    extra_tokens: int | None = None
    storage_overhead: int | None = None
    wall_clock_overhead_ms: float | None = None
    void_rate: int = 0
    restart_latency_ms: float | None = None  # harness-owned; printed, never compared across arms
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import fields

        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "raw"} | {
            "raw": self.raw
        }


def compute(
    *,
    world_applied: dict[str, int],
    world_receipts: list[dict[str, Any]],
    sut_committed: set[str] | None,
    required_effects: tuple[str, ...],
    status: str,
    expected_status: str,
    expected_world_state: dict[str, int],
    faults: list[dict[str, Any]],
    t_restarts: list[float],
    wall_ms: float,
    model_calls: int | None,
    tokens: int | None,
    storage_bytes: int | None,
    detect_ms: float | None,
    verdicts: dict[str, str],
    world_probes: list[dict[str, Any]] | None = None,
    valid: bool = True,
    baseline: "Metrics | None" = None,
) -> Metrics:
    receipts_by_label: dict[str, int] = {}
    for r in world_receipts:
        label = r["logical_identity"]
        receipts_by_label[label] = receipts_by_label.get(label, 0) + 1

    m = Metrics()
    m.duplicate_effects = sum(max(0, n - 1) for n in world_applied.values())
    m.duplicate_receipts = sum(max(0, n - 1) for n in receipts_by_label.values())
    m.lost_effects = (
        None if sut_committed is None else len([c for c in sut_committed if c not in world_applied])
    )
    m.missing_required = (
        len([r for r in required_effects if world_applied.get(r, 0) < 1]) if status == "COMPLETED" else 0
    )

    # Logical correctness is an equality against the workload's declared end state, not a
    # similarity: a run that completed with the wrong world is not partially right.
    m.logical_correctness = int(
        status == expected_status
        and all(world_applied.get(k, 0) == v for k, v in expected_world_state.items())
    )
    m.recovery_rate = int(verdicts.get("L1") == "PASS" and verdicts.get("L2") == "PASS")
    m.void_rate = 0 if valid else 1

    t_fault = max((f["trigger_observed_at"] for f in faults), default=None)
    t_live = _first_live(list(world_receipts) + list(world_probes or []), faults)
    if t_fault is not None and t_restarts:
        m.restart_latency_ms = (t_restarts[-1] - t_fault) * 1000
    if t_fault is not None and t_live is not None:
        m.recovery_latency_ms = (t_live - t_fault) * 1000
        if t_restarts:
            m.time_to_first_live_step_ms = (t_live - t_restarts[-1]) * 1000
    m.recovery_detect_ms = detect_ms

    if baseline is not None:
        m.extra_model_calls = _delta(model_calls, baseline.raw.get("model_calls"))
        m.extra_tokens = _delta(tokens, baseline.raw.get("tokens"))
        m.storage_overhead = _delta(storage_bytes, baseline.raw.get("storage_bytes"))
        m.wall_clock_overhead_ms = _delta(wall_ms, baseline.raw.get("wall_ms"))

    m.raw = {
        "world_applied": dict(world_applied),
        "world_receipts": receipts_by_label,
        "receipts_total": len(world_receipts),
        "sut_committed": sorted(sut_committed) if sut_committed is not None else None,
        "model_calls": model_calls,
        "tokens": tokens,
        "storage_bytes": storage_bytes,
        "wall_ms": wall_ms,
        "faults_fired": len(faults),
        "world_probes": len(world_probes or []),
    }
    return m


def _first_live(requests: list[dict[str, Any]], faults: list[dict[str, Any]]) -> float | None:
    """The first request the SUT made *after* the last fault, observed at the wire so that every
    arm is measured the same way.

    A re-fired duplicate counts as live, because it is: the runtime really did issue it. So does a
    probe — in the EXTERNAL band, asking the receiver what happened is the entire live act, and a
    definition that only counted effects would report no recovery for the band that recovered
    most carefully.
    """
    t_fault = max((f["trigger_observed_at"] for f in faults), default=None)
    if t_fault is None:
        return None
    later = [r["ts"] for r in requests if r["ts"] > t_fault]
    return min(later) if later else None


def _delta(value: Any, base: Any) -> Any:
    if value is None or base is None:
        return None
    return value - base
