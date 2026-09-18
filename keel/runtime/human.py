"""A human's decision about a RESOLVED_UNKNOWN step (§6.2, §7.3, §10.3, §25.2).

An EXTERNAL `escalate` and an IDEMPOTENT `key_window_expired` both end the same way: STEP_RESOLVED
{RESOLVED_UNKNOWN} and the run SUSPENDED, because a human is owed the decision. This is where the
human's answer lands. It travels as a `custom` signal — the signal type enum stays the constitution's
nine values — whose payload is `{kind: resolve_step, resolve_step: i, as, evidence}` (§25.2's note),
and it is drained, like every signal, by the lease holder under the fence:

    SIGNAL_RECEIVED{custom} ▸ STEP_RESOLVED{step i, COMPLETED|FAILED, method=human, evidence} ▸ effects row

A second STEP_RESOLVED, not a STEP_COMPLETED: `events_outcome_once` already holds the attempt's
STEP_AMBIGUOUS, and `events_resolved_once` keys on `(step_index, method)` — escalate once, a human
once (§6.2). Re-execution returns `evidence.result` of the last STEP_RESOLVED as the step's value;
RESOLVED_FAILED raises `StepFailed` like any terminal failure.

**A resolve implies resume** (§7.2.1): the acquiring worker picks `cause=RESUME` when a pending
`resume` *or* `custom{kind=resolve_step}` row sits on a SUSPENDED run, so no second `keel resume` is
needed. `lifts_suspension` is that one predicate, read by the worker's peek and by the drain that
hands a suspended run back when such a row lands after the cause was chosen.

Section-local decisions, each named once:

- `failed` settles the step as RESOLVED_FAILED; it does not start attempt n+1. §7.3 lets the retry
  policy decide after a RESOLVED_FAILED, but a re-attempt that went ambiguous again would need a
  second `escalate` row, which `events_resolved_once` refuses. The program is handed `StepFailed`
  and may issue a new call (a new index, a new key) if it wants the effect after all.
- `completed` hands the program the signal's `result` when one is given, else §23.4's sentinel
  `{"__keel_resolved__": "COMMITTED", effect_key, evidence}` — the probe path's honest answer when
  nothing was read back. §10.3's "validated against the tool's `result` model" is not built: tools
  here declare no result model.
- `cancelled` is not this signal. It is the ordinary run cancel (§7.3), and `close_on_cancel` is
  its step half: a cancel acknowledged at a RESOLVED_UNKNOWN step closes it with STEP_CANCELLED.
  The effects row stays RESOLVED_UNKNOWN — cancelling the run does not tell anyone whether the
  effect landed.
"""

from __future__ import annotations

from typing import Any

from keel.events import SignalIgnored, StepCancelled, StepResolved
from keel.state.fold import CANCELLED, RESOLVED_COMPLETED, RESOLVED_FAILED, RESOLVED_UNKNOWN

KIND = "resolve_step"

#: `as` -> (the step's resolution, the effects row's status) — §7.4's human edges.
OUTCOMES = {
    "completed": (RESOLVED_COMPLETED, "RESOLVED_COMMITTED"),
    "failed": (RESOLVED_FAILED, "RESOLVED_ABSENT"),
}


def signal_payload(
    step_index: int, outcome: str, *, evidence: str = "", result: Any = None, by: str = ""
) -> dict[str, Any]:
    """The row `Keel.resolve` and `keel signal --resolve` both write."""
    p: dict[str, Any] = {"kind": KIND, "resolve_step": int(step_index), "as": outcome, "evidence": evidence}
    if result is not None:
        p["result"] = result
    if by:
        p["by"] = by
    return p


def is_resolve(row: Any) -> bool:
    return row.type == "custom" and (row.payload or {}).get("kind") == KIND


def lifts_suspension(row: Any) -> bool:
    """§7.2.1: the rows that make an acquisition of a SUSPENDED run a RESUME."""
    return row.type == "resume" or is_resolve(row)


async def resolve(engine: Any, tx: Any, row: Any, seq: int) -> None:
    """Apply one drained `resolve_step` signal, judged against the step's state *now*."""
    p = row.payload or {}
    i = p.get("resolve_step")
    step = engine.state.steps.get(i) if isinstance(i, int) else None
    outcome = OUTCOMES.get(p.get("as"))
    reason = (
        "bad_resolution" if outcome is None
        else "unknown_step" if step is None
        else "step_not_unresolved" if step.state != RESOLVED_UNKNOWN
        else None
    )
    if reason is not None:
        await tx.append(
            SignalIgnored(signal_id=row.signal_id, signal_type=row.type, reason=reason), causation_seq=seq
        )
        return
    resolution, status = outcome
    evidence: dict[str, Any] = {
        "signal_id": str(row.signal_id),
        "evidence": str(p.get("evidence") or f"resolved {p['as']} by a human"),
    }
    if p.get("by"):
        evidence["by"] = str(p["by"])
    result = external_ref = None
    if resolution == RESOLVED_COMPLETED:
        result = p.get("result")
        if result is None:
            result = {"__keel_resolved__": "COMMITTED", "effect_key": step.effect_key, "evidence": evidence["evidence"]}
        evidence["result"] = result
        # The receiver's id, read the way the TOOL executor reads it off a live result — what S2 and
        # C3 match a committed effect to the World by (§7.4). A human who names none leaves it unset.
        external_ref = result.get("external_ref") if isinstance(result, dict) else None
    out = await tx.append(
        StepResolved(step_index=i, attempt_no=step.attempts, resolution=resolution, method="human", evidence=evidence),
        causation_seq=seq,
    )
    if step.effect_key:
        await tx.update_effect(
            step.effect_key, status=status, outcome_seq=out, resolution="human", external_ref=external_ref
        )
    # The engine's fold, advanced in place, as the fold would: the replay that follows this drain
    # reads the step as settled and hands the program its value.
    step.state = step.resolution = resolution
    step.method = "human"
    step.outcome_seq, step.outcome_epoch = out, engine.lease.epoch
    if resolution == RESOLVED_COMPLETED:
        step.result = result
    else:
        step.error = evidence["evidence"]


async def close_on_cancel(engine: Any, tx: Any, step_index: int, causation_seq: int) -> None:
    """§7.3's `RESOLVED_UNKNOWN → CANCELLED : STEP_CANCELLED (run cancelled)`."""
    step = engine.state.steps.get(step_index)
    if step is None or step.state != RESOLVED_UNKNOWN:
        return
    out = await tx.append(StepCancelled(step_index=step_index, attempt_no=step.attempts), causation_seq=causation_seq)
    step.state, step.outcome_seq, step.outcome_epoch = CANCELLED, out, engine.lease.epoch
