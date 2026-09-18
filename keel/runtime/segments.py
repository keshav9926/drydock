"""Continuation segments: `Continue(state)` → SEGMENT_STARTED, and re-execution from the latest one
(§4.9, §10.8, §18.3).

A segment boundary is the point re-execution starts from, so recovery costs the segment, not the
run. The program declares its state as a Pydantic v2 model (`@program(state=Model)`), and a boundary
is taken two ways:

    return Continue(state)          the program ends its segment; Keel journals the boundary and calls
                                    it again with `state` — revalidated from the blob, so the next
                                    segment starts from exactly what a recovery would
    ctx.segment_point(state)        a safe point; Keel cuts at the first one reached once the segment
                                    has issued `FORCED_SEGMENT_STEPS`, before the next step's INTENT

Step indices, effect keys and `seq` continue across a boundary; `run_id` never changes. The plan and
the compaction summary are Keel-owned and never in the blob: the boundary's own transaction re-writes
the plan as an `init` snapshot and names the latest summary by `compact_seq`, so both projections
are rebuildable from the boundary alone — which is what C2 checks.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from keel.core.errors import StateSchemaMismatch

#: N (§18.3): the forced boundary falls at the first `ctx.segment_point` after a segment has issued
#: this many steps. Worker configuration, not program input — it consumes no step index and is never
#: compared with the journal, so changing it moves only where the *next* boundary falls (§10.8).
FORCED_SEGMENT_STEPS = 400


class Continue:
    """What a program returns to end its segment and start the next from `state` (§18.3)."""

    __slots__ = ("state",)

    def __init__(self, state: BaseModel) -> None:
        self.state = state


def restore(model: type[BaseModel] | None, blob: Any) -> BaseModel:
    """A boundary's `state_blob` as the program's declared model, or `StateSchemaMismatch` with the
    validation error — the program's own `model_validator(mode="before")` is its upcaster (§18.3)."""
    if model is None:
        raise StateSchemaMismatch("the program declares no state model; `@program(state=...)` is required")
    try:
        return model.model_validate(blob)
    except ValidationError as exc:
        raise StateSchemaMismatch(str(exc)) from exc


async def run(program: Any, ctx: Any, args: Any, state: BaseModel | None, model: type[BaseModel] | None) -> Any:
    """Call the program from `state` (None: from the top); at each `Continue`, journal the boundary and
    call it again. Returns the program's final result; raises whatever it raises."""
    while True:
        result = await (program(ctx, args) if state is None else program(ctx, args, state))
        if not isinstance(result, Continue):
            return result
        if model is None:
            raise StateSchemaMismatch("Continue(state) from a program that declares no state model")
        blob = result.state.model_dump(mode="json")
        await ctx._continue(blob)
        state = restore(model, blob)
