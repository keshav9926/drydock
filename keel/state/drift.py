"""Plan-vs-journal drift (§18.6): projection fields, never events.

The durable plan is what a run *believes* it is doing; the journal is what it did. Two detectors,
both pure functions of the fold — `keel show` prints them and a `Policy` may gate on the first:

    steps_since_plan_update          steps issued since the last PLAN step. A fifty-step run whose
                                     plan has not moved in forty steps is doing something the plan
                                     does not describe — the failure mode nobody journals (§29.2)
    items_completed_without_effects  items marked complete with no non-PURE STEP_COMPLETED between
                                     the step that created them and the step that completed them

Surfaced, never corrected: Keel does not know what the plan should say. §18.6's fifth row — a stale
plan after FORK — is not here because FORK is not built (cut per §28.5, week-3 backfill last in
§29.2's cut order); its check belongs to `keel fork`, which would print the plan items created after
`fork_seq`.
"""

from __future__ import annotations

from typing import Any

from keel.state import plan as _plan
from keel.state.fold import COMPLETED, RESOLVED_COMPLETED, RunState

#: §18.6's section-local threshold: past this many steps without a plan update, the `Policy` may
#: `require_approval` for the next effect (`StaticPolicy(stale_plan_after=STALE_PLAN_AFTER)`).
STALE_PLAN_AFTER = 25


def steps_since_plan_update(st: RunState) -> int | None:
    """None for a run that has never touched its plan: with no plan there is nothing to drift from."""
    plan_steps = [i for i, s in st.steps.items() if s.kind == "PLAN"]
    return st.next_step_index - 1 - max(plan_steps) if plan_steps else None


def items_completed_without_effects(st: RunState) -> list[str]:
    """Plan item ids, in plan order."""
    effects = [
        i for i, s in st.steps.items()
        if s.kind == "TOOL" and s.effect_class not in (None, "PURE") and s.state in (COMPLETED, RESOLVED_COMPLETED)
    ]
    out = []
    for item in st.plan:
        done = st.plan_completed_at.get(item["id"])
        if item["status"] == _plan.COMPLETED and done is not None and not any(
            item["created_at_step"] < i < done for i in effects
        ):
            out.append(item["id"])
    return out


def drift(st: RunState) -> dict[str, Any]:
    return {
        "steps_since_plan_update": steps_since_plan_update(st),
        "items_completed_without_effects": items_completed_without_effects(st),
    }
