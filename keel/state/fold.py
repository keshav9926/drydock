"""The fold. All run state is a pure fold over events; a projection bug is fixed by re-folding,
never by editing events (§4).

This module has no I/O imports — VERIFY, the CLI and the TUI fold the same code (§23.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, TypeAdapter

from keel.core.hashing import projection_hash as _hash
from keel.events import Event
from keel.state import context as _context
from keel.state import plan as _plan

# step states (§7.3); the `effects` mirror uses its own vocabulary (INTENDED/STARTED/COMMITTED/…)
INTENDED = "INTENDED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
AMBIGUOUS = "AMBIGUOUS"
CANCELLED = "CANCELLED"
RESOLVED_COMPLETED = "RESOLVED_COMPLETED"
RESOLVED_FAILED = "RESOLVED_FAILED"
RESOLVED_UNKNOWN = "RESOLVED_UNKNOWN"

_SETTLED = frozenset({COMPLETED, FAILED, CANCELLED, RESOLVED_COMPLETED, RESOLVED_FAILED})

#: §7.2's waiting phases. A park is one event with a reason, and the phase is that reason spelled
#: the way the run projection spells it — the two are not allowed to drift, so the mapping is here
#: and nowhere else.
_WAITING_PHASE = {
    "approval": "WAITING_APPROVAL",
    "children": "WAITING_CHILDREN",
    "sleep": "SLEEPING",
    "signal": "WAITING_SIGNAL",
    "resolution": "WAITING_RESOLUTION",
    "retry_backoff": "SLEEPING",  # §7.2.1: a backoff of a second or more is a zero-compute wait
}


@dataclass(slots=True)
class StepState:
    step_index: int
    kind: str
    name: str
    state: str
    intent_seq: int
    intent_epoch: int
    args_hash: str | None = None
    request_hash: str | None = None
    effect_key: str | None = None
    effect_class: str | None = None
    attempts: int = 0
    outcome_seq: int | None = None
    outcome_epoch: int | None = None
    result: Any = None
    error: str | None = None
    retryable: bool = False
    resolution: str | None = None
    method: str | None = None
    #: A retryable failure the runtime decided to retry, and when (§8.7). None: the failure stands.
    next_attempt_at: Any = None
    #: A waiting step's `wake_at`, from the RUN_WAITING that parked it — a SLEEP's timer (§18.4).
    wake_at: Any = None
    #: The first attempt's `started_at` (store clock): where an IDEMPOTENT key window is measured from.
    first_started_at: Any = None
    #: Attempts a successor closed as `attempt_abandoned` — the crash-open half's own count (§9.1).
    abandoned: int = 0

    @property
    def settled(self) -> bool:
        """Has this step a value the program can be handed without executing anything? A failure
        the runtime journaled a retry for (`next_attempt_at`) is not: the step is still open."""
        if self.state == FAILED and self.next_attempt_at is not None:
            return False
        return self.state in _SETTLED

    def identity(self) -> tuple:
        """Per-kind intent identity (§1): MODEL compares (kind, name); the rest add the args hash."""
        if self.kind in ("MODEL", "COMPACT"):
            return (self.kind, self.name)
        return (self.kind, self.name, self.args_hash)


#: Step kinds whose normal life is STARTED-without-outcome for days. A crash or a spurious wake
#: while one is parked must not re-issue the request — a second APPROVAL_REQUESTED would mint a
#: second `approval_id` and break S7's "exactly one GRANTED approval per gated effect" (§7.3.1).
WAITING_KINDS = frozenset({"APPROVAL", "SLEEP", "SIGNAL_WAIT", "DELEGATE"})


@dataclass(slots=True)
class Approval:
    """The approvals projection (§7.5). One per `approval_id`, folded from its two events."""

    approval_id: Any
    step_index: int
    state: str = "REQUESTED"  # REQUESTED | GRANTED | REJECTED | EXPIRED
    payload: dict[str, Any] = field(default_factory=dict)
    expires_at: Any = None
    binds_effect_key: str | None = None
    by: str = ""

    @property
    def terminal(self) -> bool:
        """Decided. The first non-expired decision is final; everything after it is ignored."""
        return self.state != "REQUESTED"


@dataclass(slots=True)
class ChildState:
    """The parent's view of one delegation (§7.6.1). There is no RUNNING here, deliberately: every
    transition is caused by an event in the *parent's own* journal, and "the child has started" is
    not one. The parent is contractually blind to the child's internals."""

    child_run_id: Any
    delegation_id: Any
    step_index: int
    state: str = "SPAWNED"  # SPAWNED | COMPLETED | FAILED | CANCELLING | CANCELLED
    child_ordinal: int = 0
    retry_no: int = 0
    contract: dict[str, Any] = field(default_factory=dict)
    budget_reserved: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    policy_applied: str | None = None
    usage_settled: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.state in ("COMPLETED", "FAILED", "CANCELLED")


_DATETIME, _DURATION = TypeAdapter(AwareDatetime), TypeAdapter(timedelta)


def deadline_of(budget: Mapping[str, Any] | None, created_ts: datetime) -> datetime | None:
    """§16.4: `max_wall_clock` is not accumulated from step durations; it becomes an absolute deadline
    once, at RUN_CREATED — the event's own timestamp, the store's clock — and from then on is the same
    object as `deadline_at`. Derived here rather than written back, so every fold agrees on it."""
    budget = budget or {}
    found = []
    if budget.get("deadline_at") is not None:
        found.append(_DATETIME.validate_python(budget["deadline_at"]))
    if budget.get("max_wall_clock") is not None:
        found.append(created_ts + _DURATION.validate_python(budget["max_wall_clock"]))
    return min(found) if found else None


def usd_of(usage: Mapping[str, Any], price: Any) -> float:
    """Tokens at a journaled (input, output) rate in USD per million (§16.4). The runtime prices a
    reservation with it and the fold prices chunks and settlements, so the two cannot disagree."""
    return (int(usage.get("input_tokens", 0)) * price[0] + int(usage.get("output_tokens", 0)) * price[1]) / 1_000_000


@dataclass(slots=True)
class Charged:
    """The budget projection: a run-wide fold, never bounded by a segment boundary, or a run would
    forget what it had spent every few hundred steps (§16.4).

    `tokens_charged` is an *upper bound* on what the provider billed, which is the whole point. A
    model attempt with no outcome stays charged at its reservation for good: it may well have been
    served, the runtime cannot know, so it assumes it was.
    """

    tokens_charged: int = 0
    model_calls: int = 0  # STARTED attempts, not outcomes
    tool_calls: int = 0
    reserved: dict[tuple[int, int], int] = field(default_factory=dict)
    #: USD, the same rule over the rate the attempt's STARTED journaled from the run's pinned table
    #: (§16.4). One attempt with no rate — an unpriced binding — makes the whole figure a floor rather
    #: than a bound, so `usd_priced` goes false for good and `max_usd` is no longer admitted against.
    usd_charged: float = 0.0
    usd_priced: bool = True
    usd_held: dict[Any, tuple[float, Any]] = field(default_factory=dict)

    def start(
        self, step_index: int, attempt_no: int, reservation: int | None, kind: str,
        usd: float | None = None, price: Any = None,
    ) -> None:
        if kind in ("MODEL", "COMPACT"):
            self.model_calls += 1
            if reservation:
                self.tokens_charged += reservation
                self.reserved[(step_index, attempt_no)] = reservation
            if price is None:
                self.usd_priced = False
            else:
                self.usd_charged += usd or 0.0
                self.usd_held[(step_index, attempt_no)] = (usd or 0.0, price)
        elif kind == "TOOL":
            self.tool_calls += 1

    def chunk(self, step_index: int, attempt_no: int, usage_cum: dict[str, int] | None) -> None:
        """A streamed attempt's running usage raises its floor, never lowers it (§9.1, §10.7): an
        attempt that never settles stays charged at `max(reservation, last usage_cum)`, because the
        tokens generated after the last batch are unrecorded and a closure settles nothing."""
        if not usage_cum:
            return
        usd = self.usd_held.get((step_index, attempt_no))
        if usd is not None and usd_of(usage_cum, usd[1]) > usd[0]:
            self.usd_charged += usd_of(usage_cum, usd[1]) - usd[0]
            self.usd_held[(step_index, attempt_no)] = (usd_of(usage_cum, usd[1]), usd[1])
        held = self.reserved.get((step_index, attempt_no))
        if held is None:
            return
        seen = int(usage_cum.get("input_tokens", 0)) + int(usage_cum.get("output_tokens", 0))
        if seen > held:
            self.tokens_charged += seen - held
            self.reserved[(step_index, attempt_no)] = seen

    def settle(self, step_index: int, attempt_no: int, usage: dict[str, int] | None) -> None:
        """Swap the reservation for what the attempt actually reported. An outcome carrying no
        usage — a provider error — leaves the reservation charged."""
        usd = self.usd_held.pop((step_index, attempt_no), None)
        if usd is not None and usage is not None:
            self.usd_charged += usd_of(usage, usd[1]) - usd[0]
        reservation = self.reserved.pop((step_index, attempt_no), None)
        if reservation is None or usage is None:
            return
        self.tokens_charged -= reservation
        self.tokens_charged += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))

    # --- delegation (§17.4): the child's slice is a reservation in the parent's ledger --------
    def reserve_child(self, child_run_id: Any, slice_: dict[str, Any]) -> None:
        """Charged at CHILD_SPAWNED, in full. A child that never reaches terminal — suspended and
        forgotten — stays charged at its slice for good, which is the conservative answer."""
        tokens = int(slice_.get("max_tokens") or 0)
        self.tokens_charged += tokens
        self.reserved[("child", child_run_id)] = tokens
        usd = float(slice_.get("max_usd") or 0.0)
        self.usd_charged += usd
        self.usd_held[("child", child_run_id)] = (usd, None)

    def settle_child(self, child_run_id: Any, usage: dict[str, Any] | None) -> None:
        """Swap the slice for what the child's own journal charged — itself an upper bound on the
        child's provider bill (§16.4), so S9 holds for the whole tree."""
        usd = self.usd_held.pop(("child", child_run_id), None)
        if usd is not None and usage is not None and "usd_charged" in usage:
            self.usd_charged += float(usage["usd_charged"]) - usd[0]
            self.usd_priced = self.usd_priced and bool(usage.get("usd_priced", True))
        reservation = self.reserved.pop(("child", child_run_id), None)
        if reservation is None or usage is None:
            return
        self.tokens_charged -= reservation
        self.tokens_charged += int(usage.get("tokens_charged") or 0)


@dataclass(slots=True)
class SegmentState:
    """The latest continuation boundary (§10.8): where re-execution starts and what it starts from."""

    segment_no: int
    first_step_index: int
    seq: int
    program_version: str
    state_blob: Any = None
    compact_seq: int | None = None


@dataclass(slots=True)
class RunState:
    run_id: UUID | None = None
    program: str = ""
    program_version: str = ""
    phase: str = "CREATED"
    args: Any = None
    result: Any = None
    error: str | None = None
    suspended_reason: str | None = None
    suspended_detail: Any = None
    waiting_reason: str | None = None
    wake_at: Any = None
    forced_by: str | None = None
    #: The step index the program was told a cancel at. `None` means no cancel has been
    #: acknowledged, which is not the same as no cancel having been *requested*.
    cancel_acknowledged_at: int | None = None
    signals_drained: int = 0
    last_seq: int = 0
    steps: dict[int, StepState] = field(default_factory=dict)
    epochs: list[int] = field(default_factory=list)
    live_from_step: dict[int, int] = field(default_factory=dict)
    recovery_cause: dict[int, str] = field(default_factory=dict)
    recovery_open: bool = False
    budget: Mapping[str, Any] = field(default_factory=dict)
    #: `Budget.deadline_at`, with `max_wall_clock` converted once at RUN_CREATED by the store's clock
    #: (§16.4) — the earlier of the two. None: no deadline.
    deadline_at: Any = None
    #: The current model binding — RUN_CREATED's, then each MODEL_BINDING_CHANGED (§16.7).
    model_config: dict[str, Any] = field(default_factory=dict)
    charged: Charged = field(default_factory=Charged)
    approvals: dict[Any, Approval] = field(default_factory=dict)
    children: dict[Any, ChildState] = field(default_factory=dict)
    #: The durable plan (§16.2): a fold of PLAN_UPDATED from seq 1, never touched by compaction.
    plan: list[dict[str, Any]] = field(default_factory=list)
    #: Plan item id -> the step that completed it: what §18.6's `items_completed_without_effects` needs.
    plan_completed_at: dict[str, int] = field(default_factory=dict)
    #: The context projection (§16.2): outcomes since the latest compaction, summary first.
    context: list[dict[str, Any]] = field(default_factory=list)
    #: The seq of the latest COMPACT step's outcome, None until the run has compacted (§10.8).
    compact_seq: int | None = None
    #: The latest COMPACT outcome as the message it leaves behind: what a boundary resets context to.
    summary: dict[str, Any] | None = None
    #: The latest continuation boundary, and the Keel-owned projections as it left them — the plan
    #: snapshot written with it and the context it reset to. A recovery seeds `ctx` from these.
    segment: SegmentState | None = None
    segment_plan: list[dict[str, Any]] = field(default_factory=list)
    segment_context: list[dict[str, Any]] = field(default_factory=list)

    def children_of(self, step_index: int) -> list[ChildState]:
        """The delegations one DELEGATE step spawned, in ordinal order."""
        return sorted(
            (c for c in self.children.values() if c.step_index == step_index),
            key=lambda c: (c.child_ordinal, c.retry_no),
        )

    # --- what re-execution asks -------------------------------------------
    def step(self, step_index: int) -> StepState | None:
        return self.steps.get(step_index)

    def approval_at(self, step_index: int) -> Approval | None:
        """The approval requested by this step, if any. One per APPROVAL step by construction: the
        request is appended in the step's own transaction and is never re-issued."""
        for a in self.approvals.values():
            if a.step_index == step_index:
                return a
        return None

    def approval_for(self, effect_key: str) -> Approval | None:
        """The approval that binds this effect key — the read the TOOL executor makes before it
        starts a gated attempt, and the whole of S7 on the runtime side."""
        for a in self.approvals.values():
            if a.binds_effect_key is not None and a.binds_effect_key == effect_key:
                return a
        return None

    @property
    def next_step_index(self) -> int:
        return max(self.steps, default=-1) + 1

    @property
    def open_step(self) -> StepState | None:
        """At most one step lacks an outcome at a crash (steps are strictly sequential, §1)."""
        for s in self.steps.values():
            if not s.settled and s.state != RESOLVED_UNKNOWN:
                return s
        return None

    @property
    def latest_epoch(self) -> int:
        return self.epochs[-1] if self.epochs else 0

    @property
    def terminal(self) -> bool:
        return self.phase in ("COMPLETED", "FAILED", "CANCELLED", "SUPERSEDED")

    def origin(self, step_index: int, epoch: int | None = None) -> str:
        """memo | recovered | live, computed against an epoch — a property of the STEP (§25.4)."""
        epoch = self.latest_epoch if epoch is None else epoch
        s = self.steps.get(step_index)
        if s is None:
            return "-"
        live_from = self.live_from_step.get(epoch)
        if live_from is not None and step_index >= live_from:
            return "live"
        if s.outcome_epoch == epoch:
            return "recovered"
        return "memo"

    def projection_hash(self) -> str:
        """Raw projection hash: sha256(canonical_json(RunState)) — the MVP form of §4.5."""
        return _hash(
            {
                "phase": self.phase,
                "result": self.result,
                "error": self.error,
                "steps": [
                    {
                        "i": s.step_index,
                        "kind": s.kind,
                        "name": s.name,
                        "state": s.state,
                        "args_hash": s.args_hash,
                        "effect_key": s.effect_key,
                        "result": s.result,
                        "error": s.error,
                    }
                    for s in sorted(self.steps.values(), key=lambda s: s.step_index)
                ],
            }
        )


def fold(events: list[Event]) -> RunState:
    st = RunState()
    for ev in events:
        _apply(st, ev)
        st.last_seq = ev.seq
    return st


def _apply(st: RunState, ev: Event) -> None:  # noqa: C901 - one dispatch, deliberately flat
    b = ev.body
    t = ev.type
    if t == "RUN_CREATED":
        st.run_id = ev.run_id
        st.program = b.program
        st.program_version = b.program_version
        st.args = b.args
        st.context = _context.initial(b.args)
        st.budget = b.budget
        st.deadline_at = deadline_of(b.budget, ev.ts)
        st.model_config = dict(b.model_config_)
        st.phase = "CREATED"
    elif t == "RECOVERY_STARTED":
        st.epochs.append(b.lease_epoch)
        st.recovery_cause[b.lease_epoch] = b.cause
        st.recovery_open = True
        # §7.2.1: an acquisition moves CREATED and WAITING_* to RUNNING, lifts SUSPENDED only for a
        # manual resume, and never lifts PAUSED — only RUN_PAUSE_LIFTED does. A woken paused or
        # suspended run is still paused or suspended until the drain says otherwise.
        if st.phase == "SUSPENDED":
            if b.cause == "RESUME":
                st.phase = "RUNNING"
        elif st.phase != "PAUSED" and not st.terminal:
            st.phase = "RUNNING"
    elif t == "RECOVERY_COMPLETED":
        st.live_from_step[ev.lease_epoch] = b.live_from_step
        st.recovery_open = False
    elif t == "RUN_COMPLETED":
        st.phase = "COMPLETED"
        st.result = b.result
    elif t == "RUN_FAILED":
        st.phase = "FAILED"
        st.error = b.error
    elif t == "RUN_SUSPENDED":
        st.phase = "SUSPENDED"
        st.suspended_reason = b.reason
        st.suspended_detail = b.detail
    elif t == "RUN_CANCELLED":
        st.phase = "CANCELLED"
        st.error = b.reason or st.error
        st.forced_by = b.forced_by
    elif t == "RUN_WAITING":
        st.phase = _WAITING_PHASE[b.reason]
        st.waiting_reason = b.reason
        st.wake_at = b.wake_at
        if b.step_index in st.steps:
            st.steps[b.step_index].wake_at = b.wake_at
    elif t == "RUN_PAUSED":
        st.phase = "PAUSED"
    elif t == "RUN_PAUSE_LIFTED":
        st.phase = "RUNNING"
    elif t == "MODEL_BINDING_CHANGED":
        st.model_config = dict(b.model_config_)
    elif t in ("SIGNAL_RECEIVED", "SIGNAL_IGNORED"):
        # Inert by design (§6.2). A signal arriving changes nothing; what the run *did* about it is
        # a separate event in the same transaction, and that one carries the state change. Folding
        # the arrival too would make the inbox a second, competing source of truth.
        st.signals_drained += 1
    elif t == "PLAN_UPDATED":
        st.plan = _plan.apply(st.plan, b.op, b.diff)
        if b.op == "complete" and b.step_index is not None:
            st.plan_completed_at[b.diff["id"]] = b.step_index
        if b.step_index is None:  # the snapshot a boundary's own transaction writes (§10.8)
            st.segment_plan = [dict(i) for i in st.plan]
    elif t == "SEGMENT_STARTED":
        # Phase unchanged; step indices continue. The context resets to the latest summary, which
        # is what makes it rebuildable from the boundary alone (§10.8) — C2 checks the two agree.
        st.segment = SegmentState(
            segment_no=b.segment_no,
            first_step_index=b.first_step_index,
            seq=ev.seq,
            program_version=b.program_version,
            state_blob=b.state_blob,
            compact_seq=b.compact_seq,
        )
        st.context = [dict(st.summary)] if st.summary else []
        st.segment_context = [dict(m) for m in st.context]
    elif t == "APPROVAL_REQUESTED":
        st.approvals[b.approval_id] = Approval(
            approval_id=b.approval_id,
            step_index=b.step_index,
            payload=b.payload,
            expires_at=b.expires_at,
            binds_effect_key=b.binds_effect_key,
        )
    elif t == "APPROVAL_DECIDED":
        a = st.approvals[b.approval_id]
        a.state = {"granted": "GRANTED", "rejected": "REJECTED", "expired": "EXPIRED"}[b.decision]
        a.by = b.by
    elif t == "STEP_CANCELLED":
        s = st.steps.get(b.step_index)
        if s is not None:
            s.state = CANCELLED
            s.error = b.reason or s.error
            s.outcome_seq = ev.seq
            s.outcome_epoch = ev.lease_epoch
    elif t == "CHILD_SPAWNED":
        st.children[b.child_run_id] = ChildState(
            child_run_id=b.child_run_id,
            delegation_id=b.delegation_id,
            step_index=b.step_index,
            child_ordinal=b.child_ordinal,
            retry_no=b.retry_no,
            contract=b.contract,
            budget_reserved=b.budget_reserved,
        )
        st.charged.reserve_child(b.child_run_id, b.budget_reserved)
    elif t == "CHILD_COMPLETED":
        c = st.children[b.child_run_id]
        c.state = "COMPLETED"
        c.result = b.result
        c.usage_settled = b.usage_settled
        st.charged.settle_child(b.child_run_id, b.usage_settled)
    elif t == "CHILD_FAILED":
        c = st.children[b.child_run_id]
        # `ChildCancelled` is a failure with a policy applied like any other; the parent's view has
        # no separate CANCELLED transition because no parent event of its own produces one (§7.6.1).
        c.state = "CANCELLED" if b.error == "ChildCancelled" else "FAILED"
        c.error = b.error
        c.policy_applied = b.policy_applied
        c.usage_settled = b.usage_settled
        st.charged.settle_child(b.child_run_id, b.usage_settled)
    elif t == "CANCEL_ACKNOWLEDGED":
        # The index the program was told at. Re-execution reads exactly this and raises `Cancelled`
        # there — without it a replay would run further or less far than the original did, and a
        # cancelled run would not be reproducible (§4.10).
        st.cancel_acknowledged_at = b.step_index
        # Every child still open was told in the same transaction — one `cancel` row per inbox
        # (§7.6.2). The parent's view moves to CANCELLING; only a `child_result`, or the takeover
        # that forces one, moves it further.
        for c in st.children.values():
            if not c.terminal:
                c.state = "CANCELLING"
    elif t == "STEP_INTENDED":
        st.steps[b.step_index] = StepState(
            step_index=b.step_index,
            kind=b.kind,
            name=b.name,
            state=INTENDED,
            intent_seq=ev.seq,
            intent_epoch=ev.lease_epoch,
            args_hash=b.args_hash,
            request_hash=b.request_hash,
            effect_key=b.effect_key,
            effect_class=b.effect_class,
        )
    elif t == "STEP_ATTEMPT_STARTED":
        s = st.steps[b.step_index]
        s.state = RUNNING
        s.attempts = b.attempt_no
        if s.first_started_at is None:
            s.first_started_at = b.started_at
        st.charged.start(b.step_index, b.attempt_no, b.reservation, s.kind, b.reservation_usd, b.price)
    elif t == "STEP_CHUNK":
        # Observability, and the budget: the one fold that reads a chunk (§10.7). Never the step's
        # state, never the context — the semantic content of a streamed step is its outcome.
        st.charged.chunk(b.step_index, b.attempt_no, b.usage_cum)
    elif t == "STEP_COMPLETED":
        s = st.steps[b.step_index]
        st.charged.settle(b.step_index, b.attempt_no, b.usage)
        s.state = COMPLETED
        s.result = b.result
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
        st.context = _context.apply(st.context, s.kind, s.name, b.result)
        if s.kind == "COMPACT":
            st.compact_seq = ev.seq
            st.summary = _context.summary(b.result)
    elif t == "STEP_FAILED":
        s = st.steps[b.step_index]
        s.state = FAILED
        s.error = b.error
        s.abandoned += b.error == "attempt_abandoned"
        s.retryable = b.retryable
        s.next_attempt_at = b.next_attempt_at
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
    elif t == "STEP_AMBIGUOUS":
        s = st.steps[b.step_index]
        s.state = AMBIGUOUS
        s.error = b.cause
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
    elif t == "STEP_RESOLVED":
        s = st.steps[b.step_index]
        s.state = b.resolution
        s.resolution = b.resolution
        s.method = b.method
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
        if b.resolution == RESOLVED_COMPLETED:
            s.result = b.evidence.get("result")
            st.context = _context.apply(st.context, s.kind, s.name, s.result)
        elif b.resolution == RESOLVED_FAILED:
            s.error = b.evidence.get("evidence") or "resolved failed"
