"""Pure v(n) -> v(n+1) functions keyed by (type, from_version), applied at load only (§6.5).

Stored events are never rewritten; a rename is an upcaster, never a SQL migration, because a
migration would rewrite history and break C4 — `fold(v1 rows) == fold(upcast(v1 rows))` for every
projection over every archived run (§12.6, `tests/property/test_fold_props.py`). Registering one
raises that type's CURRENT version (`registry.py`), which is the version every writer emits.
"""

from __future__ import annotations

from collections.abc import Callable

UPCASTERS: dict[tuple[str, int], Callable[[dict], dict]] = {}


def upcaster(type_: str, from_v: int):
    def reg(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        UPCASTERS[(type_, from_v)] = fn
        return fn

    return reg


@upcaster("STEP_COMPLETED", 1)
def step_completed_v1_to_v2(raw: dict) -> dict:
    """v1 usage: {input_tokens, output_tokens}. v2 adds cache_read_tokens, prompt tokens served from the
    provider's cache and billed apart. No v1 writer had a cache, so an old event read no cache: 0 —
    the choice that keeps the budget fold equal (C4). A copy, never the caller's dict: upcasters are pure."""
    usage = raw.get("usage")
    if usage is not None:
        usage = {**usage, "cache_read_tokens": 0}
    return {**raw, "usage": usage, "schema_version": 2}
