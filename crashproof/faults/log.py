"""The trial directory: firing state that outlives the process it belongs to (§11.7).

A worker that has just been restarted must not fire a fault it already fired, and a worker cannot
remember anything — it was killed. So firing state lives in files the supervisor owns and both
incarnations can read.

Three single writers, five files, no locks across processes:

    supervisor  → cursor.json, program_variant
    firing site → faults.jsonl, observations.jsonl
    World       → world/receipts.jsonl

The write order inside the firing site is the whole reliability argument. Observe and fsync first,
so the occurrence counter survives the kill that is about to happen; append the fault row and fsync
*before* executing the fault, so "each entry fires at most once per trial" holds across a kill. A
process that dies between the row and the fault leaves a row for a fault that did not happen — the
supervisor stamps that trial invalid rather than scoring it, which is the honest disposal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

CURSOR = "cursor.json"
FAULTS = "faults.jsonl"
OBSERVATIONS = "observations.jsonl"
SCHEDULE = "schedule.json"
SPEC = "spec.yaml"
RESULT = "result.json"


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    landmark: str
    boundary: str
    occurrence: int
    recovery_index: int
    ts: float


class FaultFired(BaseModel):
    """One firing. `executed` is deliberately not here: the firing site cannot know whether the
    fault it is about to execute actually happened, so the supervisor stamps that on its own copy
    in `result.json` and never writes back into this file."""

    model_config = ConfigDict(frozen=True)

    fault_id: str
    trial_id: str
    recovery_index: int
    type: str
    boundary: str
    landmark: str
    occurrence: int
    params: dict[str, Any] = {}
    trigger_observed_at: float = 0.0
    trigger_observed_mono_ns: int = 0
    sut_ref: dict[str, Any] = {}


class Cursor(BaseModel):
    """Written by the supervisor BEFORE every spawn, so a worker reads its own incarnation number
    rather than being told one on a command line that must stay identical."""

    model_config = ConfigDict(frozen=True)

    trial_id: str
    recovery_index: int = 0
    sut_pid: int | None = None
    started_at: float = 0.0


class TrialDir:
    """The one channel between the supervisor and an in-SUT injector, and the only thing that
    changes content across restarts."""

    ENV = "CRASHPROOF_TRIAL_DIR"

    def __init__(self, path: Path | str, *, fresh: bool = False) -> None:
        self.path = Path(path)
        if fresh and self.path.exists():
            # A trial directory IS the firing state. Reusing a dirty one means every entry in the
            # schedule is already spent, the fault never fires, and the trial reports a clean
            # recovery it never performed — a false PASS, which is the one result this harness
            # must never produce. The SUT never passes `fresh`: it is joining a trial, not
            # starting one.
            import shutil

            shutil.rmtree(self.path)
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "world").mkdir(exist_ok=True)
        (self.path / "sut").mkdir(exist_ok=True)

    # --- paths ---------------------------------------------------------------
    @property
    def cursor_path(self) -> Path:
        return self.path / CURSOR

    @property
    def faults_path(self) -> Path:
        return self.path / FAULTS

    @property
    def observations_path(self) -> Path:
        return self.path / OBSERVATIONS

    @property
    def schedule_path(self) -> Path:
        return self.path / SCHEDULE

    @property
    def receipts_path(self) -> Path:
        return self.path / "world" / "receipts.jsonl"

    def thaw_marker(self, fault_id: str) -> Path:
        """Written by the supervisor after it resumes a frozen worker, and polled by the worker.
        A frozen process cannot poll, so the first successful read is necessarily after the thaw."""
        return self.path / f"thawed-{fault_id}"

    @classmethod
    def from_env(cls) -> "TrialDir":
        path = os.environ.get(cls.ENV)
        if not path:
            raise RuntimeError(f"{cls.ENV} is not set; a SUT is always started with a trial dir")
        return cls(path)

    # --- supervisor side -----------------------------------------------------
    def write_cursor(self, cursor: Cursor) -> None:
        _durably_write(self.cursor_path, cursor.model_dump_json(indent=2))

    def read_cursor(self) -> Cursor:
        return Cursor.model_validate_json(self.cursor_path.read_text(encoding="utf8"))

    # --- firing site side ----------------------------------------------------
    def append_observation(self, obs: Observation) -> None:
        _durably_append(self.observations_path, obs.model_dump_json())

    def append_fault(self, row: FaultFired) -> None:
        _durably_append(self.faults_path, row.model_dump_json())

    def observations(self) -> list[Observation]:
        return [Observation.model_validate(d) for d in _read_jsonl(self.observations_path)]

    def faults(self) -> list[FaultFired]:
        return [FaultFired.model_validate(d) for d in _read_jsonl(self.faults_path)]

    def fired_ids(self) -> set[str]:
        """Entries already spent. Rebuilt at process start, because the process that spent them
        is gone."""
        return {row.fault_id for row in self.faults()}

    def occurrence_counts(self) -> dict[tuple[str, str], int]:
        """The trial-wide counter, replayed from disk. This is what lets `occurrence: 2` mean
        "after the restart" — the semantics the cross-restart triggers are built on."""
        counts: dict[tuple[str, str], int] = {}
        for obs in self.observations():
            key = (obs.landmark, obs.boundary)
            counts[key] = counts.get(key, 0) + 1
        return counts


def _durably_write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())


def _durably_append(path: Path, line: str) -> None:
    """Append, flush, fsync — in that order, before anything irreversible happens next."""
    with path.open("a", encoding="utf8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
