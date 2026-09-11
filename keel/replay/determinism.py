"""The logical projection hash (§10.5).

Two executions that made the same decisions and produced the same results must hash equal *even if
one of them crashed four times and probed its way to the answer*. That sentence is the whole module,
and everything it excludes follows from it:

    included   step_index, kind, name, args_hash, terminal_state, result_hash
               then the run's terminal status and its result hash
    excluded   ts, lease_epoch, attempt_no, started_at, provider_meta, usage,
               and every control-plane column

`terminal_state` is normalised before hashing — `RESOLVED_COMPLETED` folds to `COMPLETED` and
`RESOLVED_FAILED` to `FAILED` — because *how* a step reached its outcome is recovery history, not
logical state. A step that completed on the first attempt and a step that timed out, went ambiguous,
was probed and found to have landed are the same fact about the world; if the hash disagreed, C1
would fail every trial that recovered, which is every trial worth running.

This is the comparison C1 makes, so it has to be a pure function of the fold and nothing else: no
clock, no journal, no I/O. `keel/state` is the only thing it may reach for.
"""

from __future__ import annotations

import hashlib
from typing import Any

from keel.core.hashing import canonical_json
from keel.state.fold import (
    CANCELLED,
    COMPLETED,
    FAILED,
    RESOLVED_COMPLETED,
    RESOLVED_FAILED,
    RunState,
)

#: How a step reached its outcome is recovery history. What it decided is logical state.
_NORMALISE = {
    RESOLVED_COMPLETED: COMPLETED,
    RESOLVED_FAILED: FAILED,
    COMPLETED: COMPLETED,
    FAILED: FAILED,
    CANCELLED: CANCELLED,
}


def result_hash(value: Any) -> str:
    """`sha256` of the canonical encoding. `None` hashes like any other value, because a step that
    returned nothing and a step that returned `null` are the same decision."""
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def normalise(state: str) -> str:
    """A settled step's logical state. An unsettled one keeps its own name so a hash taken over an
    unfinished run cannot silently equal one taken over a finished one."""
    return _NORMALISE.get(state, state)


def step_row(step: Any) -> tuple[Any, ...]:
    return (
        step.step_index,
        step.kind,
        step.name,
        step.args_hash,
        normalise(step.state),
        result_hash(step.result),
    )


def logical_projection(state: RunState) -> dict[str, Any]:
    """The hashed material, as data. Returned rather than only hashed because a mismatch needs a
    diff: `keel diff` walks these two lists and names the first step that disagrees, and a bare
    hexadecimal difference would tell an operator nothing about what changed."""
    return {
        "steps": [step_row(state.steps[i]) for i in sorted(state.steps)],
        "phase": state.phase,
        "result_hash": result_hash(state.result),
    }


def logical_projection_hash(state: RunState) -> str:
    return hashlib.sha256(canonical_json(logical_projection(state)).encode()).hexdigest()
