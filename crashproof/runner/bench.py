"""The matrix: cells, seeds, and the baselines that make the deltas mean anything (§14.2, §25.3).

A **cell** is `(adapter, config, variant, trigger)`. A cell's value is n **seeds**, not n trials of
one seed — because `(spec_hash, seed)` is simultaneously the reproduction key and the pairing key
for `compare`, and that is only true if the seed varies per trial.

Every fault cell is paired with the no-fault baseline for the same `(config, variant, seed)`. The
baselines are not an afterthought to be run later: without τ₀ the delta metrics are not imprecise,
they are undefined. So they run first, and the fault cells read them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from crashproof.faults.spec import FaultSpec, from_doc
from crashproof.runner.store import ResultStore, slug
from crashproof.runner.trial import TrialRow, run_trial
from crashproof.verifier.metrics import Metrics
from crashproof.workloads.spec import Workload, load_named

BASELINE_TRIGGER = "baseline"


@dataclass(slots=True)
class Cell:
    id: str
    adapter: str
    config: str
    variant: str
    trigger: str
    spec: FaultSpec
    key_source: str = "none"
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def is_baseline(self) -> bool:
        return self.trigger == BASELINE_TRIGGER


@dataclass(slots=True)
class Matrix:
    workload: str
    mode: str = "shim"
    seeds: int = 30
    base_seed: int = 7
    max_recoveries: int = 3
    timeout: float = 60.0
    variants: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    adapters: list[dict[str, Any]] = field(default_factory=list)
    landmark: str = "tool:create_issue"

    @classmethod
    def load(cls, path: Path | str) -> "Matrix":
        doc = yaml.safe_load(Path(path).read_text(encoding="utf8"))
        seeds = doc.pop("seeds", {}) or {}
        doc.pop("verifier", None)  # the MVP set is fixed; the key documents intent, not behaviour
        doc.pop("t_recover_s", None)
        return cls(seeds=seeds.get("count", 30), base_seed=seeds.get("base", 7), **doc)

    def seed_range(self) -> list[int]:
        return list(range(self.base_seed, self.base_seed + self.seeds))

    def cells(self) -> list[Cell]:
        out: list[Cell] = []
        for adapter in self.adapters:
            for config in adapter.get("configs", [{"id": "default"}]):
                for variant in self.variants:
                    for trigger in [BASELINE_TRIGGER, *self.triggers]:
                        out.append(
                            Cell(
                                id=f"{adapter['name']}.{config['id']}.{variant['id']}.{trigger}",
                                adapter=adapter["name"],
                                config=config["id"],
                                variant=variant["id"],
                                trigger=trigger,
                                key_source=adapter.get("key_source", "none"),
                                settings={k: v for k, v in config.items() if k != "id"},
                                spec=self._spec_for(trigger, variant["id"]),
                            )
                        )
        return out

    def _spec_for(self, trigger: str, variant: str) -> FaultSpec:
        """One trigger becomes one spec. The same document runs against every arm in the cell —
        that is the publication rule, and it is why the trigger names a landmark rather than an
        ordinal in anybody's traffic."""
        base = {
            "name": f"{self.workload}.{variant}.{trigger}",
            "workload": self.workload,
            "workload_variant": variant,
            "mode": self.mode,
            "max_recoveries": self.max_recoveries,
            "timeout": self.timeout,
            "faults": [],
        }
        if trigger == BASELINE_TRIGGER:
            return from_doc(base)
        fault_type, _, boundary = trigger.rpartition("@")
        boundary = boundary or trigger
        base["faults"] = [
            {
                "id": "f1",
                "type": fault_type or "kill",
                "trigger": {"boundary": boundary, "landmark": self.landmark, "occurrence": 1},
            }
        ]
        return from_doc(base)


async def run_matrix(
    matrix: Matrix,
    *,
    out_dir: Path,
    adapters: dict[str, Any],
    cells: list[str] | None = None,
    resume: bool = False,
    on_row: Any = None,
    keel_commit: str = "",
) -> list[TrialRow]:
    """Baselines first, then the fault cells that are paired against them."""
    import fnmatch

    workload = load_named(matrix.workload)
    store = ResultStore(out_dir)
    already = store.done() if resume else set()
    selected = [c for c in matrix.cells() if not cells or any(fnmatch.fnmatch(c.id, g) for g in cells)]
    baselines: dict[tuple[str, str, str, int], Metrics] = {}
    rows: list[TrialRow] = []

    for cell in sorted(selected, key=lambda c: (not c.is_baseline, c.id)):
        factory = adapters.get(cell.adapter)
        if factory is None:
            # A missing arm and an N/A arm are different findings, so it is recorded, not skipped.
            if on_row:
                on_row(None, cell, "adapter not built")
            continue
        for seed in matrix.seed_range():
            if (cell.id, seed) in already:
                continue
            adapter = factory(workload, cell.variant, **cell.settings)
            row = await run_trial(
                adapter=adapter,
                workload=workload,
                variant=cell.variant,
                spec=cell.spec,
                seed=seed,
                out_dir=out_dir / slug(cell.id),
                cell_id=cell.id,
                baseline=baselines.get((cell.adapter, cell.config, cell.variant, seed)),
                keel_commit=keel_commit,
            )
            if cell.is_baseline:
                baselines[(cell.adapter, cell.config, cell.variant, seed)] = _metrics(row)
            store.append(row.as_dict())
            store.write_cursor({"cell": cell.id, "seed": seed})
            rows.append(row)
            if on_row:
                on_row(row, cell, None)
    return rows


def _metrics(row: TrialRow) -> Metrics:
    m = Metrics(**{k: v for k, v in row.metrics.items() if k != "raw"})
    m.raw = row.metrics["raw"]
    return m
