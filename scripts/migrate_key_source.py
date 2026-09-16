"""One-off migration: `key_source` on published rows becomes the key source *in effect* (§14.2).

Rows written before `crashproof/runner/trial.py` recorded `key_source_in_effect` copied the
variant's declared key source into the row. The IDEMPOTENT variant declares `framework`, so every
LangGraph IDEMPOTENT row in `matrix_v0`, `tier1a` and `tier1p` says `key_source=framework` — though
LangGraph presents no key (`LangGraphAdapter.key_sources == {"none"}`; none of those trials' World
receipts carries an Idempotency-Key). Its IDEMPOTENT band was the receiver's natural dedup at F0,
and the page headers said F1.

This rewrites that one field on the rows whose adapter cannot present the recorded key source, using
the same function new rows go through, and changes nothing else: the field's text is replaced in
place, the line is re-parsed to prove only that field moved, and every other line is written back
byte for byte (line endings included). No verdict, count or metric changes; the pages re-render
with `key_source=framework, none` over the IDEMPOTENT band.

    uv run python scripts/migrate_key_source.py bench/results/{matrix_v0,tier1a,tier1p}/results.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from crashproof.adapters.keel import KeelAdapter
from crashproof.adapters.langgraph import LangGraphAdapter
from crashproof.runner.trial import key_source_in_effect

ADAPTERS: dict[str, Any] = {"keel": KeelAdapter, "langgraph": LangGraphAdapter}


def migrate_line(line: str) -> str:
    """The line with `key_source` set to what its adapter presents, or the line itself."""
    body = line.rstrip("\r\n")
    if not body.strip():
        return line
    row = json.loads(body)
    recorded = row["key_source"]
    in_effect = key_source_in_effect(ADAPTERS[row["adapter"]], recorded)
    if in_effect == recorded:
        return line
    old, new = json.dumps({"key_source": recorded})[1:-1], json.dumps({"key_source": in_effect})[1:-1]
    assert body.count(old) == 1, f"{row['cell_id']} t-{row['seed']}: expected one {old}"
    migrated = body.replace(old, new)
    assert json.loads(migrated) == {**row, "key_source": in_effect}, "only key_source may change"
    return migrated + line[len(body):]


def migrate(path: Path) -> int:
    lines = path.read_bytes().decode("utf8").splitlines(keepends=True)
    out = [migrate_line(line) for line in lines]
    changed = sum(a != b for a, b in zip(lines, out, strict=True))
    if changed:
        path.write_bytes("".join(out).encode("utf8"))
    return changed


def main(argv: list[str]) -> None:
    for name in argv:
        print(f"{name}: {migrate(Path(name))} row(s) rewritten")


if __name__ == "__main__":
    main(sys.argv[1:])
