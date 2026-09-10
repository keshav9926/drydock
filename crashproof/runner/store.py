"""Where the rows go (§5.11, §11.9).

JSONL during the run, one row per trial, appended durably — a bench run that dies halfway must
leave every completed trial readable, because re-running an hour of trials to recover a crash in
the reporting step would be its own kind of unreliability.

Parquet and DuckDB arrive with the statistics (v1). The report reads JSONL today; a format nobody
can `grep` is a format nobody checks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

RESULTS = "results.jsonl"
CURSOR = "cursor.json"


class ResultStore:
    def __init__(self, out_dir: Path | str) -> None:
        self.path = Path(out_dir)
        self.path.mkdir(parents=True, exist_ok=True)

    @property
    def results_path(self) -> Path:
        return self.path / RESULTS

    @property
    def cursor_path(self) -> Path:
        return self.path / CURSOR

    def append(self, row: dict[str, Any]) -> None:
        with self.results_path.open("a", encoding="utf8") as fh:
            fh.write(json.dumps(row, default=str, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def rows(self) -> Iterator[dict[str, Any]]:
        if not self.results_path.exists():
            return iter(())
        return (
            json.loads(line)
            for line in self.results_path.read_text(encoding="utf8").splitlines()
            if line.strip()
        )

    def done(self) -> set[tuple[str, int]]:
        """`(cell_id, seed)` pairs already recorded, so `bench --resume` does not re-run them."""
        return {(r["cell_id"], r["seed"]) for r in self.rows()}

    def write_cursor(self, cursor: dict[str, Any]) -> None:
        self.cursor_path.write_text(json.dumps(cursor, indent=2, default=str), encoding="utf8")
