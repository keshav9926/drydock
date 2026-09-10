"""Schedule expansion: the one place a trial's randomness lives (§11.6).

`expand(spec, seed)` is a pure function. Every random choice the harness controls is made here and
nowhere else, which is what makes `(spec_hash, seed)` reproduce a trial exactly — and what makes
"we re-ran the same schedule after the fix" a meaningful sentence rather than a hope.

Four guarantees an engineer may rely on:

1. `(spec_hash, seed)` determines `schedule.json` byte for byte.
2. Matching is history-only. An entry fires on the `occurrence`-th observation of its
   `(landmark, boundary)` in the trial — never on a clock, a pid or a port.
3. Faults have independent PRNG streams keyed by `fault.id`, so adding a third fault does not move
   the draws of the first two. (Adding one does change `spec_hash`, which is the point: the
   schedule's identity is the spec's identity.)
4. A trigger that could never fire is an error at expansion, never a trial that quietly scores zero.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from crashproof.faults.spec import (
    RESTART_CAUSING,
    FaultSpec,
    ScheduleExceedsRecoveries,
    UnreachableTrigger,
)


class OccurrenceSource(Protocol):
    """Whatever can say how often a landmark is reached in a *fault-free* run — the workload."""

    def expected_occurrences(self, landmark: str, boundary: str) -> int: ...


class Entry(BaseModel):
    model_config = ConfigDict(frozen=True)

    fault_id: str
    type: str
    boundary: str
    landmark: str
    occurrence: int
    recovery_index: int | None = None
    delay_ms: int = 0
    params: dict[str, Any] = {}

    def key(self) -> tuple[str, str]:
        return (self.landmark, self.boundary)


class Schedule(BaseModel):
    model_config = ConfigDict(frozen=True)

    spec_hash: str
    seed: int
    max_recoveries: int
    timeout: float
    entries: tuple[Entry, ...] = ()

    def hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]

    def write(self, path: Path) -> Path:
        path.write_text(self.model_dump_json(indent=2), encoding="utf8")
        return path

    @classmethod
    def read(cls, path: Path) -> "Schedule":
        return cls.model_validate_json(Path(path).read_text(encoding="utf8"))


def expand(spec: FaultSpec, seed: int, workload: OccurrenceSource | None = None) -> Schedule:
    trial_seed = hashlib.sha256(f"{spec.spec_hash}:{seed}".encode()).hexdigest()
    entries: list[Entry] = []

    for f in spec.faults:
        rng = random.Random(f"{trial_seed}:{f.id}")  # one stream per fault, independent of the rest
        occ = f.trigger.occurrence
        n_fires = spec.max_recoveries + 1 if f.every else f.count
        for k in range(n_fires):
            if f.probability is not None:
                occ += _geometric(rng, f.probability) - 1
            entries.append(
                Entry(
                    fault_id=hashlib.sha256(f"{trial_seed}:{f.id}:{k}".encode()).hexdigest()[:16],
                    type=f.type,
                    boundary=f.trigger.boundary,
                    landmark=f.trigger.landmark,
                    occurrence=occ,
                    recovery_index=f.trigger.recovery_index,
                    delay_ms=f.trigger.delay_ms,
                    params=_draw_params(rng, f.params),
                )
            )
            occ += 1

        # Reachability is bounded by the schedule, not by the fault-free count: each incarnation
        # may re-issue a landmark at most once per fault-free occurrence, which is exactly what
        # counting occurrences across restarts is for.
        if workload is not None and not f.every and (f.trigger.recovery_index or 0) < 1:
            fault_free = workload.expected_occurrences(f.trigger.landmark, f.trigger.boundary)
            bound = fault_free * (1 + spec.max_recoveries)
            if fault_free and occ - 1 > bound:
                raise UnreachableTrigger(f.id, occ - 1, bound)
        if f.type in RESTART_CAUSING and n_fires > spec.max_recoveries:
            raise ScheduleExceedsRecoveries(f.id, n_fires, spec.max_recoveries)

    return Schedule(
        spec_hash=spec.spec_hash,
        seed=seed,
        max_recoveries=spec.max_recoveries,
        timeout=spec.timeout,
        entries=tuple(sorted(entries, key=lambda e: (e.landmark, e.boundary, e.occurrence))),
    )


def _geometric(rng: random.Random, p: float) -> int:
    """Occurrences until the next success, inclusive. Drawn here so a probabilistic spec is still
    a fixed schedule once the seed is known."""
    if p >= 1:
        return 1
    return int(math.floor(math.log(1.0 - rng.random()) / math.log(1.0 - p))) + 1


def _draw_params(rng: random.Random, params: dict[str, Any]) -> dict[str, Any]:
    """`{uniform: [a, b]}` and `{choice: [...]}` become concrete values at expansion, so the trial
    directory records what was drawn rather than a distribution to re-draw."""
    out: dict[str, Any] = {}
    for name, value in params.items():
        if isinstance(value, dict) and "uniform" in value:
            lo, hi = value["uniform"]
            out[name] = rng.uniform(float(lo), float(hi))
        elif isinstance(value, dict) and "choice" in value:
            out[name] = rng.choice(list(value["choice"]))
        else:
            out[name] = value
    return out


def canonical_json(schedule: Schedule) -> str:
    return json.dumps(schedule.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
