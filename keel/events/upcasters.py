"""Pure v(n) -> v(n+1) functions keyed by (type, from_version), applied at load only (§6.5).

Empty at MVP by design: the registry and the `load` path are day-1 structure, a real upcaster is
V2 with C4. Stored events are never rewritten; a rename is an upcaster, never a SQL migration.
"""

from __future__ import annotations

from collections.abc import Callable

UPCASTERS: dict[tuple[str, int], Callable[[dict], dict]] = {}


def upcaster(type_: str, from_v: int):
    def reg(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        UPCASTERS[(type_, from_v)] = fn
        return fn

    return reg
