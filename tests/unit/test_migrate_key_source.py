"""`scripts/migrate_key_source.py`: one field on the rows that need it, and not one byte elsewhere."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("migrate_key_source", ROOT / "scripts" / "migrate_key_source.py")
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


def _line(adapter: str, key_source: str, **extra) -> str:
    row = {"adapter": adapter, "cell_id": f"{adapter}.x.IDEMPOTENT.baseline", "seed": 7,
           "key_source": key_source, "metrics": {"wall_ms": 1234.5678901234}, **extra}
    return json.dumps(row, sort_keys=True)  # ResultStore.append's own serialisation


def test_a_langgraph_row_labelled_framework_becomes_none_and_nothing_else_moves(tmp_path) -> None:
    keel, lg, lg_ok = _line("keel", "framework"), _line("langgraph", "framework"), _line("langgraph", "none")
    path = tmp_path / "results.jsonl"
    path.write_bytes(f"{keel}\r\n{lg}\r\n{lg_ok}\n".encode())

    assert migration.migrate(path) == 1
    keel_after, lg_after, lg_ok_after = path.read_bytes().decode().splitlines(keepends=True)
    assert keel_after == keel + "\r\n" and lg_ok_after == lg_ok + "\n", "untouched lines, byte for byte"
    assert lg_after == lg.replace('"key_source": "framework"', '"key_source": "none"') + "\r\n"
    assert json.loads(lg_after)["key_source"] == "none"
    assert migration.migrate(path) == 0, "idempotent"
