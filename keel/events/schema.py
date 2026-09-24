"""The discriminated union of every event body (§6.2).

MVP rows only (§27.4): run core, run suspension, step core, step ambiguity. The rest arrive with
their mechanisms — a body added later is a new member of this union and a new CURRENT entry, never
a rewrite of a stored row.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class Body(BaseModel):
    model_config = ConfigDict(frozen=True)


class BlobRef(BaseModel):
    """Replaces any field whose serialised size exceeds 32 KiB (§6.1)."""

    model_config = ConfigDict(frozen=True)
    blob_id: str
    media_type: str = "application/json"
    size_bytes: int


# --- run core ----------------------------------------------------------------
class RunCreated(Body):
    type: Literal["RUN_CREATED"] = "RUN_CREATED"
    program: str
    program_version: str
    args: Any = None
    budget: dict[str, Any] = Field(default_factory=dict)
    model_config_: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    parent_run_id: UUID | None = None
    delegation_id: UUID | None = None
    fork_of: dict[str, Any] | None = None
    #: The run's own capability set, `{"allowed_tools": [...]}` — a child's, from its contract (§20.2:
    #: it lives in RUN_CREATED so a re-fold can reconstruct it). None: the worker's Policy alone.
    policy: dict[str, Any] | None = None


class RecoveryStarted(Body):
    """First append after any lease acquisition. Recovery is not a special path (§1)."""

    type: Literal["RECOVERY_STARTED"] = "RECOVERY_STARTED"
    lease_epoch: int
    cause: Literal["START", "WAKE", "ORPHANED", "RESUME", "DRAIN", "VERIFY"]
    from_seq: int
    from_segment: int = 0
    #: Set by a takeover writer (§7.6.2): a takeover *is* an ORPHANED acquisition — no new cause —
    #: but the record says who forced it, because "the lease lapsed" and "the parent took it"
    #: are different facts about the same epoch.
    forced_by: str | None = None


class RecoveryCompleted(Body):
    type: Literal["RECOVERY_COMPLETED"] = "RECOVERY_COMPLETED"
    live_from_step: int
    replayed_steps: int
    elapsed_ms: int


class RunCompleted(Body):
    type: Literal["RUN_COMPLETED"] = "RUN_COMPLETED"
    result: Any = None


class RunFailed(Body):
    type: Literal["RUN_FAILED"] = "RUN_FAILED"
    error: str
    step_index: int | None = None


class RunSuspended(Body):
    type: Literal["RUN_SUSPENDED"] = "RUN_SUSPENDED"
    reason: str  # MVP: nondeterminism | resolved_unknown
    detail: Any = None


class RunCancelled(Body):
    """Appended after CANCEL_ACKNOWLEDGED, by the holder that acknowledged it or by a takeover."""

    type: Literal["RUN_CANCELLED"] = "RUN_CANCELLED"
    reason: str = ""
    forced_by: str | None = None


class RunWaiting(Body):
    """A park. Appended in the same transaction as the release, which is what makes the wait cost
    zero compute *and* zero ticks: `lease_expires_at` and `runnable_at` both go NULL, so no worker
    holds it and no scheduler polls it — only a signal or `wake_at` brings it back (§4.2)."""

    type: Literal["RUN_WAITING"] = "RUN_WAITING"
    reason: Literal["approval", "children", "sleep", "signal", "resolution", "retry_backoff"]
    wake_at: AwareDatetime | None = None
    step_index: int | None = None


class RunPaused(Body):
    type: Literal["RUN_PAUSED"] = "RUN_PAUSED"
    step_index: int | None = None


class RunPauseLifted(Body):
    type: Literal["RUN_PAUSE_LIFTED"] = "RUN_PAUSE_LIFTED"


class ModelBindingChanged(Body):
    """A drained `rebind` (§16.7): the binding the next LIVE MODEL step uses, with `runs.model_config`
    updated in the same transaction. Memoized steps keep the answers the old binding gave — model
    identity is a binding, not program input, so a provider switch is never nondeterminism."""

    type: Literal["MODEL_BINDING_CHANGED"] = "MODEL_BINDING_CHANGED"
    model_config_: dict[str, Any] = Field(alias="model_config", default_factory=dict)
    previous: dict[str, Any] = Field(default_factory=dict)


class SegmentStarted(Body):
    """A continuation boundary (§4.9, §10.8): re-execution starts here, with `state_blob` as the
    program's input and the step counter at `first_step_index` — never reset. One event in one fenced
    transaction (with the plan snapshot after it), so a torn boundary is impossible; a second with the
    same `segment_no` is refused by `events_segment_once`.

    `compact_seq` is the `seq` of the latest COMPACT outcome before the boundary, None if the run has
    never compacted — a section-local extension of the declared fields (§10.8) that keeps the context
    projection rebuildable from the boundary alone."""

    type: Literal["SEGMENT_STARTED"] = "SEGMENT_STARTED"
    segment_no: int
    first_step_index: int
    program_version: str
    state_blob: Any = None
    compact_seq: int | None = None


# --- the inbox (§4.10, §5.6) --------------------------------------------------
class SignalReceived(Body):
    """Written at the drain, in the same fenced transaction that sets `signals.consumed_seq`.

    Inert in the fold by itself: a signal *received* changes nothing. What it causes — an approval
    decided, a cancel acknowledged, a pause — is a separate event in the same transaction, so the
    journal records both that the signal arrived and what the run did about it.
    """

    type: Literal["SIGNAL_RECEIVED"] = "SIGNAL_RECEIVED"
    signal_id: UUID
    signal_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalIgnored(Body):
    """Consumed and deliberately not applied — a second approve for an approval already decided, a
    resume for a run that is not paused. The inbox is at-least-once, so this is the ordinary case
    rather than an error, and it is journaled because "nothing happened" is an audit answer."""

    type: Literal["SIGNAL_IGNORED"] = "SIGNAL_IGNORED"
    signal_id: UUID
    signal_type: str
    reason: str


class ApprovalRequested(Body):
    """Appended inside `ctx.approve`, in the same transaction as the INTENT, the STARTED and the
    RUN_WAITING that parks the run.

    `binds_effect_key` is the whole of S7. It is `effect_key(run_root_id, i+1, tool, args)` —
    computable *before* anyone decides, because the runtime owns the step counter — so the approval
    names the exact effect it authorises rather than authorising "the next thing that happens".
    `None` for a bare `ctx.approve`, which is a plain durable wait and binds nothing.
    """

    type: Literal["APPROVAL_REQUESTED"] = "APPROVAL_REQUESTED"
    step_index: int
    approval_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    expires_at: AwareDatetime | None = None
    binds_effect_key: str | None = None


class ApprovalDecided(Body):
    """The first drained *non-expired* decision. Terminal for the approval: any later approve,
    reject or timer for the same id is `SIGNAL_IGNORED{approval_terminal}` and still consumed."""

    type: Literal["APPROVAL_DECIDED"] = "APPROVAL_DECIDED"
    step_index: int
    approval_id: UUID
    decision: Literal["granted", "rejected", "expired"]
    by: str = ""
    signal_id: UUID | None = None


class CancelAcknowledged(Body):
    """The step index at which the program was told. Recorded because re-execution has to raise
    `Cancelled` at *exactly* this index or a replay would take a different path (§4.10)."""

    type: Literal["CANCEL_ACKNOWLEDGED"] = "CANCEL_ACKNOWLEDGED"
    step_index: int


class StepCancelled(Body):
    """An open step closed by a cancel rather than by an outcome — the holder's own step at
    acknowledgement, or a child's open step under a takeover. Memoized as `Cancelled` on replay."""

    type: Literal["STEP_CANCELLED"] = "STEP_CANCELLED"
    step_index: int
    attempt_no: int | None = None
    forced_by: str | None = None
    #: Why, when it was not a cancel: `DeadlineExceeded` for a wait woken past the run's deadline
    #: (§16.4), which replays as that failure rather than as `Cancelled`.
    reason: str | None = None


# --- delegation (§4.11, §7.6, §17) ------------------------------------------------
class ChildSpawned(Body):
    """Appended by the parent's holder inside `ctx.delegate`, in the *same* transaction as the
    child's `runs` row, its RUN_CREATED and its `delegations` row. A crash between "the parent
    says it spawned" and "the child exists" is therefore impossible, which is the one property a
    delegation protocol cannot do without (§5.10). `budget_reserved` is charged to the parent
    here and settled at CHILD_COMPLETED / CHILD_FAILED."""

    type: Literal["CHILD_SPAWNED"] = "CHILD_SPAWNED"
    step_index: int
    child_run_id: UUID
    delegation_id: UUID
    child_ordinal: int = 0
    retry_no: int = 0
    contract: dict[str, Any] = Field(default_factory=dict)
    budget_reserved: dict[str, Any] = Field(default_factory=dict)


class ChildCompleted(Body):
    """The parent's verdict on a child's result, at the drain of its `child_result` signal and
    after validation against the contract's `result_schema`. The parent's contract decides, not the
    child's opinion of itself (§17.8)."""

    type: Literal["CHILD_COMPLETED"] = "CHILD_COMPLETED"
    child_run_id: UUID
    result: Any = None
    usage_settled: dict[str, Any] = Field(default_factory=dict)


class ChildFailed(Body):
    """Also at the drain. `ContractViolation` lands here even though the child's own journal says
    COMPLETED — the two can disagree only in the direction that matters. Carries the settlement
    too, because a ledger that cannot settle a failure leaves the full reservation charged and
    over-reports every run that lost a child (§17.4)."""

    type: Literal["CHILD_FAILED"] = "CHILD_FAILED"
    child_run_id: UUID
    error: str
    policy_applied: Literal["retry", "escalate", "fail_parent"] = "escalate"
    usage_settled: dict[str, Any] = Field(default_factory=dict)
    detail: Any = None


# --- the durable plan (§16.2, §18.2) ------------------------------------------
class PlanUpdated(Body):
    """Fold-only: the plan projection's input. Appended in the PLAN step's own transaction, between
    its STARTED and its STEP_COMPLETED{plan_hash} — the step's memo is the STEP_COMPLETED, so the
    recovery table needs no case for PLAN (§6.2). `step_index` is None for the one PLAN_UPDATED the
    runtime writes itself: the `init` snapshot right after a SEGMENT_STARTED (§10.8).

    `init` replaces the plan with `diff.items`; `add` appends `diff.item`; `complete` marks
    `diff.id` completed. `reorder` and `note` are the constitution's other two ops and are not
    built: nothing in week 3 issues them."""

    type: Literal["PLAN_UPDATED"] = "PLAN_UPDATED"
    op: Literal["init", "add", "complete"]
    diff: dict[str, Any] = Field(default_factory=dict)
    step_index: int | None = None


# --- step core ---------------------------------------------------------------
class StepIntended(Body):
    type: Literal["STEP_INTENDED"] = "STEP_INTENDED"
    step_index: int
    kind: str
    name: str
    args_hash: str | None = None
    args: Any = None
    request_hash: str | None = None
    effect_key: str | None = None
    effect_class: str | None = None
    modifiers: tuple[str, ...] = ()
    policy_verdict: str = "allow"
    program_version: str = ""


class StepAttemptStarted(Body):
    """The attempt's write-ahead barrier: no effect may begin before this is durably committed."""

    type: Literal["STEP_ATTEMPT_STARTED"] = "STEP_ATTEMPT_STARTED"
    step_index: int
    attempt_no: int
    lease_epoch: int
    started_at: AwareDatetime
    attempt_deadline: AwareDatetime | None = None
    reservation: int | None = None
    #: A MODEL attempt's rate, USD per million (input, output) tokens, from the run's pinned price
    #: table, and its reservation priced at it (§16.4). None on a MODEL attempt: an unpriced binding.
    price: tuple[float, float] | None = None
    reservation_usd: float | None = None


class StepChunk(Body):
    """A batch of what a STREAMS attempt has emitted so far (§9.3, §10.7): observability and UI
    resume, never semantics. `blob` is the delta since the previous chunk, `usage_cum` the attempt's
    cumulative usage (MODEL only; a tool carries no token reservation). Replay reads chunks for three
    things and never for control flow: the budget charges an attempt that never settled at
    `max(reservation, last usage_cum)`; the timeline shows what streamed, by `attempt_no`; and a
    diff can show where a truncated stream stopped. The semantic result is the outcome alone."""

    type: Literal["STEP_CHUNK"] = "STEP_CHUNK"
    step_index: int
    attempt_no: int
    chunk_no: int
    blob: Any = None
    usage_cum: dict[str, int] | None = None


class StepCompleted(Body):
    type: Literal["STEP_COMPLETED"] = "STEP_COMPLETED"
    step_index: int
    attempt_no: int
    result: Any = None
    #: v2 (§6.5): `{input_tokens, cache_read_tokens, output_tokens}` when present. `cache_read_tokens`
    #: is required here and defaulted only by the v1 upcaster, so a v2 writer that forgets it is refused.
    usage: dict[str, int] | None = None
    provider_meta: dict[str, Any] | None = None
    synthetic: bool = False

    @field_validator("usage")
    @classmethod
    def _usage_is_v2(cls, usage: dict[str, int] | None) -> dict[str, int] | None:
        if usage is not None and "cache_read_tokens" not in usage:
            raise ValueError("STEP_COMPLETED v2: usage needs cache_read_tokens (a v1 row is upcast at load)")
        return usage


class StepFailed(Body):
    type: Literal["STEP_FAILED"] = "STEP_FAILED"
    step_index: int
    attempt_no: int
    error: str
    retryable: bool = False
    next_attempt_at: AwareDatetime | None = None


class StepAmbiguous(Body):
    """STARTED with no outcome, class EXTERNAL — or an EXTERNAL timeout. A state, not a guarantee."""

    type: Literal["STEP_AMBIGUOUS"] = "STEP_AMBIGUOUS"
    step_index: int
    attempt_no: int
    cause: str


class StepResolved(Body):
    """The memo of an ambiguous step — not a later STEP_COMPLETED (§6.2)."""

    type: Literal["STEP_RESOLVED"] = "STEP_RESOLVED"
    step_index: int
    attempt_no: int
    resolution: Literal["RESOLVED_COMPLETED", "RESOLVED_FAILED", "RESOLVED_UNKNOWN"]
    method: Literal["probe", "assume_failed", "assume_succeeded", "escalate", "human", "key_window_expired"]
    evidence: dict[str, Any] = Field(default_factory=dict)


EventBody = Annotated[
    RunCreated
    | RecoveryStarted
    | RecoveryCompleted
    | RunCompleted
    | RunFailed
    | RunSuspended
    | RunCancelled
    | RunWaiting
    | RunPaused
    | RunPauseLifted
    | ModelBindingChanged
    | SegmentStarted
    | ApprovalRequested
    | ApprovalDecided
    | StepCancelled
    | ChildSpawned
    | ChildCompleted
    | ChildFailed
    | SignalReceived
    | SignalIgnored
    | CancelAcknowledged
    | PlanUpdated
    | StepIntended
    | StepAttemptStarted
    | StepChunk
    | StepCompleted
    | StepFailed
    | StepAmbiguous
    | StepResolved,
    Field(discriminator="type"),
]

TERMINAL_TYPES = frozenset({"RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED"})
OUTCOME_TYPES = frozenset({"STEP_COMPLETED", "STEP_FAILED", "STEP_AMBIGUOUS"})
