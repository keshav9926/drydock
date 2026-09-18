"""Policy: capabilities and approval gates as a pre-step verdict (§20.2, §20.3, §4.3).

A `Policy` answers `allow | deny | require_approval` for a TOOL call at its step entry, in memory,
before the step's index is consumed and before any transaction opens. The answer is journaled as
`policy_verdict` on the INTENT, and the consequence commits with it:

    allow             STEP_INTENDED{policy_verdict=allow} ▸ effects row ▸ STARTED — as always
    deny              STEP_INTENDED{policy_verdict=deny} ▸ effects row DENIED ▸ STEP_FAILED{attempt_no=0,
                      PolicyDenied | PolicyTimeout, retryable=false} — one transaction, no attempt
    require_approval  the one `ctx.tool` call takes two indices: APPROVAL at i (name = the tool,
                      payload = what the key covers, binds_effect_key = key of i+1), then the TOOL at
                      i+1 — the shape `ctx.approve(gates=)` + `ctx.tool` produces, so the approvals
                      machinery (the park, expiry, `_check_binding`, `_gate`) is the whole gate

Replay reads the journal, never the Policy (`Ctx._verdict`): a journaled step at i is memoized
whatever the Policy now says, and a journaled APPROVAL at i binding this call's key at i+1 is the gate
this call inserted. A policy edited while a run sits parked for three days cannot renumber its steps.

Section-local decisions: the Policy is consulted for TOOL steps only (model, plan and wait steps
carry no capability); a policy that does not answer within the tool's timeout is a `deny` with
`PolicyTimeout` (§20.2); `require_approval` on a call the program already gated with
`ctx.approve(gates=)` at i-1 is satisfied by that approval rather than asking twice; and §20.2's
schema filter at `ctx.model()` is not built — it would change the journaled request, so VERIFY
without the same Policy would report PromptDrift on every MODEL step; the wall at `ctx.tool` is what
enforces.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from keel.core.protocols import EffectClass, StepIntent
from keel.state import drift
from keel.state.fold import RunState, _apply, fold

Verdict = Literal["allow", "deny", "require_approval"]


class StaticPolicy:
    """§20.2's default Policy: `deny` a tool outside `allowed_tools` (None: every registered tool),
    `require_approval` for a tool named in `require_approval`, else `allow`.

    `stale_plan_after` is §18.6's drift threshold (`drift.STALE_PLAN_AFTER` = 25 is the document's
    number; None, the default, is off): a non-PURE call made more than that many steps after the
    run's plan last changed waits for a human. PURE reads never do — they carry no risk to gate, and
    a stalled plan is exactly when a run should be free to look around. The other detector,
    `items_completed_without_effects`, is shown and not gated on: an item once ticked off stays
    ticked, so a gate on it would hold every later effect of the run for good."""

    def __init__(
        self,
        *,
        allowed_tools: Iterable[str] | None = None,
        require_approval: Iterable[str] = (),
        stale_plan_after: int | None = None,
    ) -> None:
        self.allowed_tools = frozenset(allowed_tools) if allowed_tools is not None else None
        self.require_approval = frozenset(require_approval)
        self.stale_plan_after = stale_plan_after

    async def pre_step(self, intent: StepIntent, run: RunState) -> Verdict:
        if self.allowed_tools is not None and intent.name not in self.allowed_tools:
            return "deny"
        if intent.name in self.require_approval:
            return "require_approval"
        if self.stale_plan_after is not None and intent.effect_class not in (None, EffectClass.PURE):
            stale = drift.steps_since_plan_update(run)
            if stale is not None and stale > self.stale_plan_after:
                return "require_approval"
        return "allow"


def capabilities(policy: Any, created: Any) -> frozenset[str] | None:
    """A run's capability set: the worker Policy's `allowed_tools` ∩ the run's own (a child's
    contract, in its RUN_CREATED). None: nothing narrows it. What `ctx.tool` denies against and what
    a delegation's `allowed_tools` must be a subset of (§17.2)."""
    sets = [getattr(policy, "allowed_tools", None)]
    own = (getattr(created, "policy", None) or {}).get("allowed_tools")
    sets.append(frozenset(own) if own is not None else None)
    known = [s for s in sets if s is not None]
    return frozenset.intersection(*known) if known else None


class JournalView:
    """The run as its journal has it *now* — what a Policy is shown.

    Not the engine's working state: that is folded once at acquisition and advanced in place only for
    what the engine itself needs, never for this epoch's live steps, so a Policy reading it would not
    see the steps it is gating. Folded on first use, then advanced by the events appended since
    through the fold's own `_apply` — one indexed read per consulted step, not a re-fold.
    """

    def __init__(self, journal: Any, run_id: Any) -> None:
        self.journal = journal
        self.run_id = run_id
        self.state: RunState | None = None

    async def read(self) -> RunState:
        if self.state is None:
            self.state = fold(await self.journal.read(self.run_id))
            return self.state
        for ev in await self.journal.read(self.run_id, from_seq=self.state.last_seq):
            _apply(self.state, ev)
            self.state.last_seq = ev.seq
        return self.state
