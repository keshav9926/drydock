"""The durable plan: a pure fold of PLAN_UPDATED (§16.2, §18.2).

An item is `{id, title, status, created_at_step, notes}` — §16.2's `PlanItem`, as JSON because it
lives in event payloads. Ids are derived from the step that created the item (`"<step>"` for an
`add`, `"<step>.<k>"` for the k-th item of an `init`), so they are known at `ctx.*` entry, stable
across replays, and unique for the life of the run: step indices never repeat.

One function applies an op, and three callers share it — the fold, the step engine (which computes
the `plan_hash` a PLAN step completes with) and `ctx.plan` (which reads the plan at the replay
cursor) — so the plan a program reads and the plan the journal projects cannot drift apart.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from keel.core.hashing import canonical_json

PENDING = "pending"
COMPLETED = "completed"


def _item(item_id: str, title: str, step_index: int) -> dict[str, Any]:
    return {"id": item_id, "title": str(title), "status": PENDING, "created_at_step": step_index, "notes": []}


def init_diff(step_index: int, titles: Sequence[str]) -> dict[str, Any]:
    return {"items": [_item(f"{step_index}.{k}", t, step_index) for k, t in enumerate(titles)]}


def add_diff(step_index: int, title: str) -> dict[str, Any]:
    return {"item": _item(str(step_index), title, step_index)}


def apply(plan: list[dict[str, Any]], op: str, diff: dict[str, Any]) -> list[dict[str, Any]]:
    """The plan after one op. A new list every time: callers keep the old one as a snapshot."""
    if op == "init":
        return [dict(i) for i in diff["items"]]
    if op == "add":
        return [*plan, dict(diff["item"])]
    if op == "complete":
        if not any(i["id"] == diff["id"] for i in plan):
            raise KeyError(f"no plan item {diff['id']!r}")
        return [{**i, "status": COMPLETED} if i["id"] == diff["id"] else i for i in plan]
    raise ValueError(f"unknown plan op {op!r}")


def plan_hash(plan: list[dict[str, Any]]) -> str:
    """What a PLAN step completes with (§6.2): the plan it left, by content."""
    return hashlib.sha256(canonical_json(plan).encode()).hexdigest()
