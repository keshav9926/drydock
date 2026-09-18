"""The step executor: INTENT -> STARTED barrier -> execute -> outcome, and the per-class recovery
table (§8.3). This is the module the whole thesis rests on.

`runtime` imports no sibling package. TOOL steps are executed by an executor that `keel.effects`
registers into `EXECUTORS` at import time; MODEL/NOW/RANDOM are runtime-owned because they need
nothing but the provider (§23.2).
"""

from __future__ import annotations

import asyncio
import random as _random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from keel.core.clock import SystemClock
from keel.core.errors import Cancelled, ContractInvalid, Fenced, KeelError, StepFailed, Rejected, UnknownOutcome
from keel.core.errors import ApprovalBindingError, NondeterminismDetected, WakeRaced
from keel.core.ids import uuid7
from keel.core.protocols import (
    Ambiguous,
    Completed,
    EffectClass,
    Failed,
    StepCtx,
    StepExecutor,
    StepIntent,
    StepKind,
    StepOutcome,
)
from keel.core.versions import KEEL_VERSION
from keel.events import (
    ApprovalDecided,
    ApprovalRequested,
    CancelAcknowledged,
    ChildCompleted,
    ChildFailed,
    ChildSpawned,
    ModelBindingChanged,
    RecoveryCompleted,
    RunCreated,
    RunPaused,
    RunPauseLifted,
    RunWaiting,
    SignalIgnored,
    SignalReceived,
    StepAmbiguous,
    StepAttemptStarted,
    StepCancelled,
    StepCompleted,
    StepFailed as StepFailedEvent,
    StepIntended,
    StepResolved,
)
from keel.journal.protocol import DelegationRow, EffectRow, JournalBackend, Lease, RunRow
from keel.providers.protocol import ModelRequest
from keel.runtime import hooks
from keel.runtime.budget import BudgetExceeded, Reservation, admit, reserve_model, reserve_tool
from keel.runtime.delegation import (
    MAX_CHILDREN_IN_FLIGHT,
    Delegation,
    cancel_signal,
    delegation_id,
    json_schema_ok,
    row_role,
    validate,
)
from keel.runtime.retry import NO_RETRY, RetryPolicy
from keel.runtime.takeover import DEFAULT_CANCEL_GRACE_S, force_cancel
from keel.state.fold import (
    AMBIGUOUS,
    CANCELLED,
    COMPLETED,
    FAILED,
    INTENDED,
    RESOLVED_UNKNOWN,
    RUNNING,
    WAITING_KINDS,
    ChildState,
    RunState,
    fold,
)

EXECUTORS: dict[StepKind, StepExecutor] = {}

#: A model call with no bound is an unbounded wait, which is the weak behaviour the `model_timeout`
#: cell exists to catch — so MODEL steps get a deadline like everything else. Generous by default
#: and pinned small in the benchmark, where a trial cannot afford to wait a minute to learn nothing.
DEFAULT_MODEL_TIMEOUT_S = 60.0

#: §7.2.1: a retry backoff shorter than this is slept in-process under the lease; a longer one parks
#: as RUN_WAITING{retry_backoff} and releases the lease, because waiting is zero compute everywhere.
PARK_BACKOFF_AFTER_S = 1.0

# A probe that cannot tell, distinguished from a step whose value happens to be None.
_UNRESOLVED = object()


def register(executor: StepExecutor) -> StepExecutor:
    EXECUTORS[executor.kind] = executor
    return executor


class Abandon(Exception):
    """Leave the run without journaling anything: the pre-dispatch gate refused, or the fence went
    away mid-attempt. The successor disposes the open step from journal state alone (§8.2)."""


class Drain(Exception):
    """SIGTERM arrived and the next step would be live work. Stop at the step boundary, release the
    lease voluntarily, append nothing special: the next holder's RECOVERY_STARTED{cause=DRAIN} is
    the whole record (§5, drain). Draining is not a lifecycle state."""


class Paused(Exception):
    """A `pause` signal was drained. RUN_PAUSED, `paused_at` and the release committed together, so
    the run costs nothing until a `resume` or `cancel` makes the claim consider it again (§16.6)."""


class Parked(Exception):
    """The run is waiting on something that is not compute, and RUN_WAITING — with the release —
    is already committed.

    `lease_expires_at = NULL` *and* `runnable_at = NULL`, keeping only `wake_at`, in the waiting
    event's own transaction (§5.4 (4)). Both NULLs matter: the first is what makes the wait cost no
    compute, the second is what makes it cost no *ticks* — no worker holds the run and no scheduler
    polls it. Days pass for the price of one row (§4.2). A SUSPENDED run re-parked by a wake that
    carried no `resume` raises this too, with reason `suspended`.
    """

    def __init__(self, reason: str, wake_at: Any = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.wake_at = wake_at


class StopReplay(Exception):
    """VERIFY reached a point it is not allowed to pass (§10.9).

    VERIFY is the memoization loop with `allow_live=False`, and there are exactly two places the
    loop would otherwise start *doing* things: the first un-journaled step, and an open step that
    the recovery table would re-attempt or resolve. Both are writes. VERIFY takes no lease and
    appends nothing, so it stops at either and reports where it stopped — `live_from_step` for the
    first, `in_flight_ambiguity` for the second.

    Raised rather than returned because it has to unwind the *program's* stack, not the engine's:
    the program is a coroutine in the middle of an `await ctx.tool(...)`, and there is no value to
    hand it that would be true.
    """

    def __init__(self, reason: str, step_index: int) -> None:
        super().__init__(f"{reason} at step {step_index}")
        self.reason = reason
        self.step_index = step_index


class Suspended(Exception):
    """The run must stop and wait for a human: nondeterminism, or an ambiguity that escalated."""

    def __init__(self, reason: str, detail: Any = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class StepEngine:
    """Owns one run's journal writes for one lease epoch."""

    def __init__(
        self,
        journal: JournalBackend,
        lease: Lease,
        state: RunState,
        *,
        run_root_id: Any,
        provider: Any = None,
        tools: Any = None,
        clock: Any = None,
        should_drain: Callable[[], bool] | None = None,
        retry: RetryPolicy = NO_RETRY,
        model_retry: RetryPolicy | None = None,
        model_timeout_s: float = DEFAULT_MODEL_TIMEOUT_S,
        allow_live: bool = True,
        parent_run_id: Any = None,
        depth: int = 0,
        model_config: Any = None,
        resolve_program: Callable[[str], Any] | None = None,
        cancel_grace_s: float = DEFAULT_CANCEL_GRACE_S,
        breaker: Any = None,
    ) -> None:
        self.journal = journal
        self.lease = lease
        self.state = state
        self.run_root_id = run_root_id
        self.provider = provider
        self.tools = tools
        self.clock = clock
        self.should_drain = should_drain
        self.retry = retry
        self.model_retry = model_retry or retry  # §8: MODEL steps may have their own
        self.model_timeout_s = model_timeout_s
        #: Delegation (§17). The parent, if this run is a child — the worker co-commits the
        #: `child_result` row with the terminal event; the depth, so a verifier cannot delegate to a
        #: verifier; the binding a child inherits; and how a child's program becomes a version,
        #: which is the worker's business (`runtime` imports no sibling) and is lent here.
        self.parent_run_id = parent_run_id
        self.depth = depth
        self.model_config = dict(model_config or {})
        self.resolve_program = resolve_program
        self.cancel_grace_s = cancel_grace_s
        #: The worker's per-provider circuit breaker (§8): below the journal, shared by every lease
        #: this process holds. None means no breaker, which is what a bare engine gets.
        self.breaker = breaker
        self._waiting_intent: StepIntent | None = None
        #: VERIFY (§10.9). One flag rather than a second loop: a separate replayer would drift from
        #: this one, and the drift would be invisible — VERIFY would keep passing while the thing
        #: it is supposed to be checking had changed underneath it.
        self.allow_live = allow_live
        self.live_from_step: int | None = None
        self.replayed_steps = 0
        self.recovery_completed = False
        #: §16.6. A paused run woken for a `resume` or `cancel` stays paused until its drain lifts
        #: the pause, and a drain that finds neither parks it again rather than running on.
        self._paused = state.phase == "PAUSED"
        #: A park lost the release guard (§5.4 (4)): `runnable_at` is set and the next drain must clear
        #: it even when the inbox is empty. The reaper's ORPHANED mark on a lease that lapsed and was
        #: never taken sets it with no signal behind it, and a drain that only opened for signals left
        #: it set — every park after that raced it again, for ever.
        self._wake_pending = False

    # --- public entry --------------------------------------------------------
    async def execute(self, intent: StepIntent) -> Any:
        # A cancel acknowledged at this index is raised here on every pass, live or replay. On the
        # original pass the drain below has just appended CANCEL_ACKNOWLEDGED; on every later one
        # the journal says where it landed, and raising at exactly that index is what makes a
        # cancelled run reproducible rather than a run that stopped somewhere near there (§4.10).
        #
        # One exception, and it is §7.6.2's: a DELEGATE step acknowledged while parked stays open
        # until its children are terminal — cancelled cooperatively or taken over — and is closed
        # by STEP_CANCELLED then. Until that event exists the step is re-entered, not raised past.
        journaled = self.state.step(intent.step_index)
        if self.state.cancel_acknowledged_at == intent.step_index and not (
            journaled is not None and journaled.kind == "DELEGATE" and not journaled.settled
        ):
            raise Cancelled(f"cancelled at step {intent.step_index}")
        if journaled is not None:
            if journaled.identity() != intent.identity():
                raise NondeterminismDetected(
                    intent.step_index, journaled.identity(), intent.identity()
                )
            if journaled.settled:
                self.replayed_steps += 1
                return _value_of(journaled)
            if journaled.state == RESOLVED_UNKNOWN:
                reason = "key_window_expired" if journaled.method == "key_window_expired" else "resolved_unknown"
                raise Suspended(reason, {"step_index": intent.step_index})
            return await self._recover_open(intent, journaled)
        # The one boundary where stopping is free: everything behind is journaled, nothing ahead
        # has been attempted. An in-flight step is never interrupted — it is already bounded by
        # `clock.timeout(tool.timeout)`, which is what `shutdown_grace` must exceed.
        if self.should_drain is not None and self.should_drain():
            raise Drain(f"draining at step {intent.step_index}")
        await self._drain_inbox(intent.step_index, force=self._paused)
        await self._reach_live(intent.step_index)
        return await self._live(intent)

    async def hold_suspended(self, step_index: int) -> None:
        """§7.2.1: a SUSPENDED run woken without a `resume` drains its inbox, acts on `cancel`, and
        otherwise parks again *without re-executing* — replaying up to the step that suspended it
        would only suspend it again, and would never consume the row that woke it."""
        await self._drain_inbox(step_index, force=True, park_as="SUSPENDED")

    async def drain_before_resuming(self, step_index: int) -> None:
        """A SUSPENDED run lifted by `resume`: consume the inbox first, so a run that suspends
        again on replay is not re-claimed for ever by the row that resumed it."""
        await self._drain_inbox(step_index, force=True)

    async def _refold(self) -> None:
        """After a rolled-back transaction, the in-place fold may say things the journal does not.
        Re-reading it is the undo, and the rare path (a signal raced a park) can afford it."""
        self.state = fold(await self.journal.read(self.lease.run_id))

    # --- the inbox drain (§4.3, §4.10) ---------------------------------------
    async def _drain_inbox(
        self, step_index: int, waiting: Any = None, *, force: bool = False, park_as: str | None = None
    ) -> None:
        """Apply every unconsumed signal, at the boundary before the step they precede.

        At *every* step boundary, not only at acquisition. Without that, a cancel sent to a held
        run in the middle of a forty-step loop would not be seen until the run parked or ended,
        "acknowledged at the next step boundary" would be false, and a busy child could not honour
        its parent's `cancel_grace`. The cost is one indexed read of
        `signals(run_id) WHERE consumed_seq IS NULL`.

        Only on the live path. A memoized step re-reads a decision already journaled, and draining
        there would let a signal that arrived *after* the original pass change what a replay does —
        the journal would stop being the whole history of the run.

        `force` opens the transaction even when the peek found nothing: after a park lost the race
        to a signal (§5.4 (4)), for a paused run that must park again, and for `park_as` — a
        SUSPENDED run woken without a resume, which parks again in this same transaction.
        """
        if not self.allow_live or not hasattr(self.journal, "pending_signals"):
            return
        peek = await self.journal.pending_signals(self.lease.run_id)
        if not peek and not force and not self._wake_pending:
            return

        cancel = telling_children = False
        # The drain is one fenced transaction, and these two boundaries bracket it. A crash before
        # it leaves every signal unconsumed and the run exactly as it was — the successor drains the
        # same rows. A crash after it leaves the decision durable and consumed, and nothing done
        # about it yet by the program — which is the window S7's "decided once" is about.
        if peek:
            hooks.at("before:signal_consume", step_index=step_index, signals=len(peek))
        resumed = False
        async with self.journal.append(self.lease) as tx:
            # Read again *under the fence*: every row whose wake bump is committed is visible now,
            # and none that lands later can commit before this transaction does (§5.4 (7)).
            pending = await tx.pending_signals()
            if park_as == "SUSPENDED" and any(r.type == "resume" for r in pending):
                # A `resume` landed after the cause was chosen. Consuming it here would lose it;
                # hand the run back instead, and the next holder's peek makes the cause RESUME.
                resumed, pending = True, []
            # One `now()` for the whole drain: expiry is judged by the store's clock at drain time,
            # never by the worker's, and two signals in one transaction must be judged against the
            # same instant or the order they happen to be read in could change the answer (§7.5).
            now = await tx.now()
            for row in pending:
                seq = await tx.append(
                    SignalReceived(signal_id=row.signal_id, signal_type=row.type, payload=row.payload)
                )
                # Consumed in the same transaction as the event that records it, always — including
                # for a signal this run declines to act on. An ignored signal that stayed unconsumed
                # would be re-read at every boundary for the life of the run.
                await tx.consume_signal(row.signal_id, seq)
                applied = await self._apply_signal(tx, row, seq, step_index, waiting, now)
                cancel = cancel or applied == "cancel"
                telling_children = telling_children or applied == "cancel_children"
            stopping = cancel or (telling_children and waiting is None)
            # §16.6: the lease is released and `paused_at` set in the pause's own transaction.
            # Cancel outranks pause: a run told to stop for good does not first stop for a while.
            park = None if stopping or resumed else ("PAUSED" if self._paused else park_as)
            if not resumed:
                await tx.clear_wake()
            if park is not None:
                await tx.release_park(phase=park, wake_at=None, paused=park == "PAUSED")
        self._wake_pending = False
        if peek:
            hooks.at("after:signal_consume", step_index=step_index, signals=len(peek))
        # Raised after the commit, so the journal is already durable when the program is told.
        #
        # A cancel with children still open is acknowledged but not raised: the parent's open
        # DELEGATE step waits for them to end (§7.6.2), and `_wait_children` owns that wait. The
        # one place that cannot be true — a cancel drained at a live boundary with open children,
        # which no program can reach because it cannot pass an open DELEGATE step — falls through
        # to the plain cancel, and the reaper's liveness rule collects the strays (§17.7).
        if resumed:
            raise Drain(f"resume for a suspended run at step {step_index}")
        if stopping:
            raise Cancelled(f"cancelled at step {step_index}")
        if park == "PAUSED":
            raise Paused(f"paused at step {step_index}")
        if park is not None:
            raise Parked(park.lower())

    async def _decide_approval(self, tx: Any, row: Any, seq: int, waiting: Any, now: Any) -> None:
        """`approve` / `reject` / `timer`, against the open approval. §7.5's rules, in order.

        The ordering rule is the subtle one, and it is deliberately not "first row wins". Expiry is
        judged by the store's clock at drain time and **outranks seq order**: an `approve` drained
        after `expires_at` is ignored and the approval expires, whether or not the timer row has
        arrived. Otherwise a decision made in time but drained late — a worker that died and took
        four seconds to be replaced — would be honoured on the wrong side of a deadline somebody
        else is relying on.
        """
        async def ignore(reason: str) -> None:
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=row.type, reason=reason),
                causation_seq=seq,
            )

        approval = self.state.approval_at(waiting.step_index) if waiting is not None else None
        # A decision that names its gate is judged against *that* gate (§7.5). Without this, a
        # retried click aimed at an approval already decided would decide whichever approval
        # happened to be open when it was drained — authorising an effect nobody approved.
        named = (row.payload or {}).get("approval_id")
        if named is not None and (approval is None or str(named) != str(approval.approval_id)):
            known = next((a for a in self.state.approvals.values() if str(a.approval_id) == str(named)), None)
            await ignore("approval_terminal" if known is not None and known.terminal else "unknown_approval")
            return None
        if approval is None:
            await ignore("unknown_approval")
            return None
        if approval.terminal:
            await ignore("approval_terminal")
            return None
        if self.state.cancel_acknowledged_at is not None:
            # §7.5.1: the approval step is being cancelled; a grant drained after that must not
            # record an authorisation nobody will act on.
            await ignore("step_terminal")
            return None

        expired = approval.expires_at is not None and now is not None and now >= approval.expires_at
        if row.type == "timer" and not expired:
            # A timer that fired early, or one that raced a decision. Consumed, not acted on.
            await ignore("not_yet_expired")
            return None
        if expired and row.type != "timer":
            await ignore("expired")
        decision = "expired" if expired else ("granted" if row.type == "approve" else "rejected")
        by = str(row.payload.get("by", "")) if row.payload else ""
        decided_seq = await tx.append(
            ApprovalDecided(
                step_index=approval.step_index,
                approval_id=approval.approval_id,
                decision=decision,
                by=by,
                signal_id=row.signal_id,
            ),
            causation_seq=seq,
        )
        # The decision reaches the program only as its own step's outcome — that is how "the program
        # observes a signal only through its own step" is implemented without a second channel
        # (§4.10). The APPROVAL step completes for all three decisions; what a rejection *means* is
        # the program's business, and a bound tool call is refused separately.
        #
        # One dict, journaled and handed to the program. Two copies once differed by `decided_at`,
        # and a program that passed the decision on made different args live than on replay.
        result = {"decision": decision, "by": by, "decided_at": str(now) if now else None}
        completed_seq = await tx.append(
            StepCompleted(step_index=approval.step_index, attempt_no=1, result=result),
            causation_seq=decided_seq,
        )
        await tx.set_run(phase="RUNNING", wake_at=None)
        # The engine's own fold is advanced in place: the rest of this drain, and the step that
        # follows it, read `state` rather than re-reading the journal.
        approval.state = {"granted": "GRANTED", "rejected": "REJECTED", "expired": "EXPIRED"}[decision]
        approval.by = by
        step = self.state.steps.get(approval.step_index)
        if step is not None:
            step.state, step.result = COMPLETED, result
            step.outcome_seq, step.outcome_epoch = completed_seq, self.lease.epoch
        return None

    async def _settle_waiting(self, intent: StepIntent, journaled: Any) -> Any:
        """A parked step, woken. Drain; if a decision arrived the step is settled and its value is
        returned, and if not the run parks again for the price of one row."""
        self._waiting_intent = intent
        while True:
            await self._drain_inbox(intent.step_index, waiting=journaled, force=self._paused)
            journaled = self.state.step(intent.step_index) or journaled
            if journaled.settled:
                if journaled.state == CANCELLED:
                    raise Cancelled(f"cancelled at step {intent.step_index}")
                return _value_of(journaled)
            if journaled.kind == "DELEGATE":
                parked = await self._wait_children(intent, journaled)
            elif journaled.kind == "SLEEP":
                if await self._wake_if_due(intent, journaled):
                    return None  # §10.4: a completed sleep's value is None
                parked = await self._commit_park(
                    "sleep", intent.step_index, phase="SLEEPING", wake_at=journaled.wake_at
                )
            else:
                approval = self.state.approval_at(intent.step_index)
                # Park *again*, with its own RUN_WAITING. The acquisition already appended
                # RECOVERY_STARTED, which moves the run to RUNNING — so without this the fold would
                # report a parked run as running for ever after its first spurious wake. A re-park
                # is a real transition and is journaled, and it releases in the same transaction.
                parked = await self._commit_park(
                    "approval", intent.step_index, phase="WAITING_APPROVAL",
                    wake_at=approval.expires_at if approval else None,
                )
                if parked:
                    hooks.at("during:approval_wait", step_index=intent.step_index, wake_at=self.state.wake_at)
            if parked:
                reason = {"DELEGATE": "children", "SLEEP": "sleep"}.get(journaled.kind, "approval")
                raise Parked(reason, wake_at=self.state.wake_at)
            # A signal raced the release: drain it and decide again.

    async def _wake_if_due(self, intent: StepIntent, journaled: Any) -> bool:
        """A sleep completes when the *store's* clock says `wake_at` has passed, whatever woke it
        (§8.7 Timer: never before `wake_at`). The timer row is only the doorbell — the drain
        consumed it as a plain wake, as it does a backoff's — so a spurious wake re-parks and a
        timer consumed by an epoch that died is not needed by the next one."""
        async with self.journal.append(self.lease) as tx:
            now = await tx.now()
            if journaled.wake_at is not None and now < journaled.wake_at:
                return False
            result = {"woke_at": now.isoformat()}
            seq = await tx.append(
                StepCompleted(step_index=intent.step_index, attempt_no=journaled.attempts or 1, result=result)
            )
            await tx.set_run(phase="RUNNING", wake_at=None)
        step = self.state.step(intent.step_index) or journaled
        step.state, step.result = COMPLETED, result
        step.outcome_seq, step.outcome_epoch = seq, self.lease.epoch
        return True

    async def _park_for_sleep(self, intent: StepIntent) -> Any:
        """INTENT, STARTED, RUN_WAITING{sleep, wake_at} and the release: one transaction, then
        nothing until the timer sweep (§18.4). `wake_at` is the store's `now()` plus the duration."""
        seconds = float((intent.args or {}).get("seconds", 0.0))
        hooks.at("before:intent_commit", **_where(intent))
        while not await self._commit_park(
            "sleep", intent.step_index, phase="SLEEPING", wake_in=seconds, intent=intent
        ):
            await self._drain_inbox(intent.step_index, force=True)
        hooks.at("after:intent_commit", **_where(intent))
        hooks.at("after:attempt_commit", attempt_no=1, **_where(intent))
        raise Parked("sleep", wake_at=self.state.wake_at)

    async def _commit_park(
        self,
        reason: str,
        step_index: int,
        *,
        phase: str,
        wake_at: Any = None,
        wake_in: float | None = None,
        intent: StepIntent | None = None,
    ) -> bool:
        """RUN_WAITING and the release, one transaction (§5.4 (4)). False when a signal arrived
        since the last drain: the transaction rolled back and the caller must drain again.
        `wake_in` is measured from the store's `now()`, never the worker's. With `intent`, the
        waiting step's INTENT and attempt 1's STARTED open the same transaction — every wait is
        INTENT + STARTED + RUN_WAITING + release, together (§18.4)."""
        try:
            async with self.journal.append(self.lease) as tx:
                now = await tx.now() if wake_in is not None or intent is not None else None
                if wake_in is not None:
                    wake_at = now + timedelta(seconds=wake_in)
                causation = None
                if intent is not None:
                    causation = await tx.append(_intended(intent))
                    await tx.append(
                        StepAttemptStarted(
                            step_index=intent.step_index, attempt_no=1, lease_epoch=self.lease.epoch, started_at=now
                        ),
                        causation_seq=causation,
                    )
                await tx.append(
                    RunWaiting(reason=reason, wake_at=wake_at, step_index=step_index), causation_seq=causation
                )
                await tx.release_park(phase=phase, wake_at=wake_at)
        except WakeRaced:
            await self._refold()
            self._wake_pending = True
            return False
        self.state.wake_at = wake_at
        return True

    async def _apply_signal(
        self, tx: Any, row: Any, seq: int, step_index: int, waiting: Any = None, now: Any = None
    ) -> str | None:
        """What the run does about one signal, judged from its state *now* rather than at insert.

        This is the half that makes an at-least-once inbox safe: a second `cancel` for a run already
        cancelling, or a `resume` for a run that is not paused, is consumed and journaled as
        SIGNAL_IGNORED with the reason. Nothing is refused at the API; everything is decided here.
        """
        kind = row.type
        if kind == "child_result":
            return await self._settle_child(tx, row, seq)
        if kind == "timer" and (waiting is None or waiting.kind != "APPROVAL"):
            # A wake with nothing to decide: `cancel_grace` on a DELEGATE, a retry backoff coming
            # due. The drain's caller acts on the time; the row is consumed so it is not re-read.
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason="wake"),
                causation_seq=seq,
            )
            return None
        if kind in ("approve", "reject", "timer"):
            return await self._decide_approval(tx, row, seq, waiting, now)
        if kind == "cancel":
            if self.state.cancel_acknowledged_at is not None:
                await tx.append(
                    SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason="already_cancelling"),
                    causation_seq=seq,
                )
                return None
            ack = await tx.append(CancelAcknowledged(step_index=step_index), causation_seq=seq)
            self.state.cancel_acknowledged_at = step_index
            if self._paused:
                # Cancel overrides pause (§16.6): an operator must always be able to stop a paused
                # run, and a paused parent must be free to wait out its children's cancellation.
                # `PAUSED → CANCELLED` needs no lift event; `paused_at` is control plane.
                self._paused = False
                await tx.set_run(paused_at=None)
            # Propagation (§7.6.2): one `cancel` per child still open, in *this* transaction, so
            # the acknowledgement and the telling cannot be separated by a crash. The child is
            # asked, not forced — forcing is the takeover, after `cancel_grace`.
            open_children = [c for c in self.state.children.values() if not c.terminal]
            for c in open_children:
                await tx.insert_signal(
                    cancel_signal(
                        c.child_run_id,
                        client_key=f"cancel:{self.lease.run_id}:{ack}",
                        by=f"parent:{self.lease.run_id}",
                        reason="parent_cancel",
                    )
                )
                c.state = "CANCELLING"
            return "cancel_children" if open_children else "cancel"
        if kind == "pause":
            if self._paused or self.state.cancel_acknowledged_at is not None:
                reason = "already_paused" if self._paused else "already_cancelling"
                await tx.append(
                    SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason=reason),
                    causation_seq=seq,
                )
                return None
            # RUN_PAUSED now; `paused_at` and the release are the drain's last statement, so a
            # `resume` later in this same drain can still lift it before anything is released.
            await tx.append(RunPaused(step_index=step_index), causation_seq=seq)
            self._paused = True
            self.state.phase = "PAUSED"
            return "pause"
        if kind == "resume":
            if self._paused:
                await tx.append(RunPauseLifted(), causation_seq=seq)
                await tx.set_run(paused_at=None, phase="RUNNING")
                self._paused = False
                self.state.phase = "RUNNING"
                return "resume"
            # A resume for a run that is not paused is the ordinary shape of a retried click, or of
            # the row that lifted a suspension: the signal woke the worker, and the worker is here.
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason="not_paused"),
                causation_seq=seq,
            )
            return None
        if kind == "rebind":
            # §16.7: the binding the next LIVE MODEL step uses, and what children spawned from here
            # inherit. Memoized steps keep the answers the old binding gave, so a provider switch in
            # the middle of a recovery is never nondeterminism.
            new = dict((row.payload or {}).get("model_config") or {})
            if not new:
                await tx.append(
                    SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason="empty_binding"),
                    causation_seq=seq,
                )
                return None
            await tx.append(
                ModelBindingChanged.model_validate({"model_config": new, "previous": dict(self.model_config)}),
                causation_seq=seq,
            )
            await tx.set_run(model_config=new)
            self.model_config = new
            return None
        await tx.append(
            SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason="no_handler"),
            causation_seq=seq,
        )
        return None

    async def _reach_live(self, step_index: int) -> None:
        """RECOVERY_COMPLETED is appended on reaching the first un-journaled step (§5.5)."""
        if self.recovery_completed:
            return
        self.live_from_step = step_index
        if not self.allow_live:
            raise StopReplay("live_from_step", step_index)
        await self._append_recovery_completed(step_index)

    async def _append_recovery_completed(self, live_from_step: int) -> None:
        self.recovery_completed = True
        elapsed = 0
        async with self.journal.append(self.lease) as tx:
            seq = await tx.append(
                RecoveryCompleted(
                    live_from_step=live_from_step,
                    replayed_steps=live_from_step,
                    elapsed_ms=elapsed,
                )
            )
        await self.journal.set_recovery(
            self.lease.run_id,
            self.lease.epoch,
            completed_seq=seq,
            live_from_step=live_from_step,
            replayed_steps=live_from_step,
            outcome="LIVE",
        )

    async def _reserve(self, intent: StepIntent) -> Reservation:
        """What this attempt could cost, computed before the barrier so a refusal costs nothing."""
        if intent.kind is StepKind.TOOL:
            return reserve_tool()
        if intent.kind not in (StepKind.MODEL, StepKind.COMPACT) or self.provider is None:
            return Reservation()
        req = ModelRequest.model_validate(intent.args)
        return reserve_model(await self.provider.count_tokens(req), req.max_tokens)

    async def _refuse(self, intent: StepIntent, exc: Exception, *, first: bool = True) -> None:
        """A pre-dispatch refusal: attempt_no 0, never retryable, no attempt and so no bill.

        The step's INTENT commits with the refusal when this is the step's first pass, so the
        journal folds — a STEP_FAILED with no STEP_INTENDED before it is a step the projection
        cannot place. A re-attempt already has its intent and appends only the refusal.
        """
        async with self.journal.append(self.lease) as tx:
            intent_seq = await tx.append(_intended(intent)) if first else None
            await tx.append(
                StepFailedEvent(
                    step_index=intent.step_index, attempt_no=0, error=str(exc), retryable=False
                ),
                causation_seq=intent_seq,
            )
        raise StepFailed(intent.step_index, str(exc), retryable=False)

    # --- live path (§5.10 transaction shapes) --------------------------------
    async def _park_for_approval(self, intent: StepIntent) -> Any:
        """One transaction, then days of nothing.

        INTENT, STARTED, APPROVAL_REQUESTED, RUN_WAITING and the release commit together — the
        release guarded by `runnable_at IS NULL` (§5.4 (4)). A crash anywhere in here leaves either
        no step at all or a parked, released one — never a half-requested approval, and never a
        second `approval_id` for one gate (§7.3.1, §7.5). A signal that raced it rolls the whole
        request back; the boundary is drained and the request made again with a fresh id, which is
        safe precisely because nothing of the first one was ever committed.
        """
        from uuid import uuid4

        args = dict(intent.args or {})
        payload = dict(args.get("payload") or {})
        expires_in = args.get("expires_in")
        binds = args.get("binds_effect_key")
        hooks.at("before:intent_commit", **_where(intent))
        while True:
            try:
                async with self.journal.append(self.lease) as tx:
                    now = await tx.now()
                    # `0` is a deadline that is already due, not the absence of one.
                    expires_at = now + timedelta(seconds=float(expires_in)) if expires_in is not None else None
                    intent_seq = await tx.append(_intended(intent))
                    await tx.append(
                        StepAttemptStarted(
                            step_index=intent.step_index,
                            attempt_no=1,
                            lease_epoch=self.lease.epoch,
                            started_at=now,
                        ),
                        causation_seq=intent_seq,
                    )
                    await tx.append(
                        ApprovalRequested(
                            step_index=intent.step_index,
                            approval_id=uuid4(),
                            payload=payload,
                            expires_at=expires_at,
                            binds_effect_key=binds,
                        ),
                        causation_seq=intent_seq,
                    )
                    await tx.append(
                        RunWaiting(reason="approval", wake_at=expires_at, step_index=intent.step_index),
                        causation_seq=intent_seq,
                    )
                    await tx.release_park(phase="WAITING_APPROVAL", wake_at=expires_at)
                break
            except WakeRaced:
                await self._refold()
                await self._drain_inbox(intent.step_index, force=True)
        # After the commit, as on every other live path: a fault at `after:intent_commit` means
        # the intent is durable, and one fired inside the transaction would have rolled it back.
        hooks.at("after:intent_commit", **_where(intent))
        hooks.at("after:attempt_commit", attempt_no=1, **_where(intent))
        # The wait: durable, released, and this process still running but holding nothing. A
        # crash here must cost the run nothing at all — the signal that wakes it is its only need.
        hooks.at("during:approval_wait", step_index=intent.step_index, wake_at=expires_at)
        raise Parked("approval", wake_at=expires_at)

    async def _gate(self, intent: StepIntent) -> None:
        """S7, on the runtime side: a bound effect may only start under a GRANTED approval.

        Read before `STARTED`, so a refusal costs no attempt and therefore no reachable effect —
        `attempt_no=0` is the pre-dispatch marker that keeps the write-ahead rule exact. The effects
        row goes `DENIED` in the same transaction, which is what stops a later pass treating the
        step as never-tried and starting it (§7.5).
        """
        if intent.effect_key is None:
            return
        approval = self.state.approval_for(intent.effect_key)
        if approval is None or approval.state == "GRANTED":
            return
        error = {"REJECTED": "ApprovalRejected", "EXPIRED": "ApprovalExpired"}.get(
            approval.state, "ApprovalPending"
        )
        await self._deny(intent, error)

    async def _check_binding(self, intent: StepIntent) -> None:
        """§7.5, §24.2: a bound approval authorises one call — `(tool, args)` at index i+1 — and
        whatever the program issues at i+1 instead fails with `ApprovalBindingError` rather than
        running ungated. Without this a redeploy that changed the tool's args, or a program that
        called something else first, would carry out an effect nobody approved: `_gate` finds no
        approval bound to the new key and lets it through.

        Refused like every pre-dispatch refusal — INTENT + STEP_FAILED{attempt_no=0} in one
        transaction, and a TOOL's effects row DENIED — so replay raises the same failure."""
        bound = self.state.approval_at(intent.step_index - 1)
        if bound is None or bound.binds_effect_key is None:
            return
        if intent.kind is StepKind.TOOL and intent.effect_key == bound.binds_effect_key:
            return
        error = (
            f"ApprovalBindingError: approval {bound.approval_id} at step {bound.step_index} binds "
            f"{bound.binds_effect_key}; step {intent.step_index} issued {intent.kind} {intent.name}"
            + (f" with key {intent.effect_key}" if intent.effect_key else "")
        )
        if intent.kind is StepKind.TOOL and intent.effect_key is not None:
            await self._deny(intent, error)
        await self._refuse(intent, ApprovalBindingError(error))

    async def _deny(self, intent: StepIntent, error: str) -> None:
        """A TOOL refused before its first attempt: INTENT, a DENIED effects row, STEP_FAILED{0}."""
        async with self.journal.append(self.lease) as tx:
            intent_seq = await tx.append(_intended(intent))
            await tx.write_effect(
                EffectRow(
                    effect_key=intent.effect_key,
                    run_id=self.lease.run_id,
                    run_root_id=self.run_root_id,
                    step_index=intent.step_index,
                    tool=intent.name,
                    effect_class=str(intent.effect_class or ""),
                    status="DENIED",
                    intent_seq=intent_seq,
                )
            )
            await tx.append(
                StepFailedEvent(
                    step_index=intent.step_index, attempt_no=0, error=error, retryable=False
                ),
                causation_seq=intent_seq,
            )
        raise StepFailed(intent.step_index, error, retryable=False)

    # --- delegation (§7.6, §17) -----------------------------------------------------
    async def _spawn_children(self, intent: StepIntent) -> Any:
        """DELEGATE, live: one transaction, then a park (§7.6.1, §5.10).

        INTENT, STARTED, one CHILD_SPAWNED per contract, each child's `runs` row + RUN_CREATED +
        `delegations` row, and RUN_WAITING{children} commit together. A crash anywhere inside
        leaves either no step or N children that all exist — never a parent that says it spawned
        a child the store has no row for, and never a child whose parent does not know it.
        """
        contracts = [Delegation.model_validate(c) for c in intent.args["contracts"]]
        try:
            validate(
                contracts,
                parent_tools=self.tools,
                parent_remaining_tokens=self._remaining_tokens(),
                parent_depth=self.depth,
            )
            for c in contracts:
                self._child_version(c.program)  # an unknown child program is a contract error
        except ContractInvalid as exc:
            await self._refuse(intent, exc)
        hooks.at("before:intent_commit", **_where(intent))
        hooks.at("before:child_spawn", children=len(contracts), **_where(intent))
        while True:
            try:
                async with self.journal.append(self.lease) as tx:
                    now = await tx.now()
                    intent_seq = await tx.append(_intended(intent))
                    await tx.append(
                        StepAttemptStarted(
                            step_index=intent.step_index,
                            attempt_no=1,
                            lease_epoch=self.lease.epoch,
                            started_at=now,
                        ),
                        causation_seq=intent_seq,
                    )
                    # Fan-out is bounded: `max_children_in_flight` now, the rest as slots free (§17.5).
                    for ordinal, c in enumerate(contracts[:MAX_CHILDREN_IN_FLIGHT]):
                        await self._spawn_one(tx, intent.step_index, ordinal, 0, c, causation_seq=intent_seq)
                    await tx.append(
                        RunWaiting(reason="children", wake_at=None, step_index=intent.step_index),
                        causation_seq=intent_seq,
                    )
                    await tx.release_park(phase="WAITING_CHILDREN", wake_at=None)
                break
            except WakeRaced:
                # Nothing of the spawn committed — no child exists — but `_spawn_one` advanced the
                # in-memory fold. Re-read it, drain what raced, and spawn again.
                await self._refold()
                await self._drain_inbox(intent.step_index, force=True)
        hooks.at("after:intent_commit", **_where(intent))
        hooks.at("after:attempt_commit", attempt_no=1, **_where(intent))
        # The wait on children: durable, released, and this process holding nothing.
        hooks.at("during:child_wait", children=len(contracts), **_where(intent))
        raise Parked("children")

    async def _spawn_one(
        self, tx: Any, step_index: int, ordinal: int, retry_no: int, contract: Delegation, *, causation_seq: int
    ) -> None:
        """CHILD_SPAWNED, plus the child's birth in the same transaction (§7.6.1)."""
        child_id = uuid7()
        did = UUID(delegation_id(self.lease.run_id, step_index, ordinal, retry_no))
        journaled = contract.as_journaled()
        version = self._child_version(contract.program)
        slice_ = dict(contract.budget_slice)
        seq = await tx.append(
            ChildSpawned(
                step_index=step_index,
                child_run_id=child_id,
                delegation_id=did,
                child_ordinal=ordinal,
                retry_no=retry_no,
                contract=journaled,
                budget_reserved=slice_,
            ),
            causation_seq=causation_seq,
        )
        args = {"task": contract.task, **contract.args}
        await tx.create_child(
            RunRow(
                run_id=child_id,
                # Its own root (§5.4: `run_root_id = run_id` unless a FORK; §17.6: a retried child
                # has new effect keys). Sharing the parent's would give a retried child, and two
                # siblings making the same call, the same key — refused as a duplicate at INTENT.
                # `trace_id` is what joins the tree.
                run_root_id=child_id,
                program=contract.program,
                program_version=version,
                keel_version=KEEL_VERSION,
                phase="CREATED",
                trace_id=self.lease.trace_id,
                args=args,
                budget=slice_,
                model_config=dict(self.model_config),
                parent_run_id=self.lease.run_id,
            ),
            RunCreated(
                program=contract.program,
                program_version=version,
                args=args,
                budget=slice_,
                model_config=dict(self.model_config),
                parent_run_id=self.lease.run_id,
                delegation_id=did,
            ),
            DelegationRow(
                delegation_id=did,
                parent_run_id=self.lease.run_id,
                parent_step_index=step_index,
                child_run_id=child_id,
                role=row_role(contract.role),
                contract=journaled,
                budget_reserved=slice_,
                spawned_seq=seq,
                child_ordinal=ordinal,
                retry_no=retry_no,
            ),
        )
        # The engine's own fold, advanced in place, exactly as `_apply` would.
        self.state.children[child_id] = ChildState(
            child_run_id=child_id,
            delegation_id=did,
            step_index=step_index,
            child_ordinal=ordinal,
            retry_no=retry_no,
            contract=journaled,
            budget_reserved=slice_,
        )
        self.state.charged.reserve_child(child_id, slice_)

    async def _settle_child(self, tx: Any, row: Any, seq: int) -> str | None:
        """The parent's verdict on a `child_result` (§17.8): validated against the contract's
        `result_schema` here, by the parent, so the two journals can disagree only in the direction
        that matters — a child that says COMPLETED and a parent that says ContractViolation."""
        payload = row.payload or {}
        try:
            child_id = UUID(str(payload.get("child_run_id")))
        except ValueError:
            child_id = None
        child = self.state.children.get(child_id) if child_id is not None else None
        if child is None or child.terminal:
            await tx.append(
                SignalIgnored(
                    signal_id=row.signal_id,
                    signal_type=row.type,
                    reason="unknown_child" if child is None else "child_terminal",
                ),
                causation_seq=seq,
            )
            return None
        contract = child.contract
        status = payload.get("status")
        usage = dict(payload.get("usage") or {})
        error: str | None = None
        detail: Any = None
        applied: str | None = None
        if status == "completed":
            ok, why = json_schema_ok(contract.get("result_schema"), payload.get("result"))
            if ok:
                out_seq = await tx.append(
                    ChildCompleted(child_run_id=child_id, result=payload.get("result"), usage_settled=usage),
                    causation_seq=seq,
                )
                child.state, child.result = "COMPLETED", payload.get("result")
            else:
                error, detail = "ContractViolation", why
        elif status == "cancelled":
            # A cancelled child stays charged at its full slice (§17.4): what it spent after the
            # cancel is not knowable from outside its own journal, and a bound has to bound. In the
            # ledger's own unit — `tokens_charged` — or the settlement adds nothing at all.
            slice_tokens = int(child.budget_reserved.get("max_tokens") or 0)
            reported = int(usage.get("tokens_charged") or 0)
            usage = {**usage, "tokens_charged": max(slice_tokens, reported)}
            error, detail = "ChildCancelled", payload.get("error")
        else:
            error, detail = str(payload.get("error") or "ChildFailed"), None
        if error is not None:
            policy = str(contract.get("on_failure") or "escalate")
            # Settle the failed child *before* admitting its replacement: §17.6 re-reserves the
            # same slice against what remains, and what remains includes this child's refund.
            self.state.charged.settle_child(child_id, usage)
            can_retry = (
                policy == "retry"
                and error != "ChildCancelled"
                # §17.7: nothing new is started under a parent that is cancelling.
                and self.state.cancel_acknowledged_at != child.step_index
                and not self._fatal(child.step_index)
                and child.retry_no < int(contract.get("max_retries") or 0)
                and self._admit_slice(child.budget_reserved)
            )
            applied = "retry" if can_retry else ("escalate" if policy == "retry" else policy)
            out_seq = await tx.append(
                ChildFailed(
                    child_run_id=child_id,
                    error=error,
                    policy_applied=applied,  # type: ignore[arg-type]
                    usage_settled=usage,
                    detail=detail,
                ),
                causation_seq=seq,
            )
            child.state = "CANCELLED" if error == "ChildCancelled" else "FAILED"
            child.error, child.policy_applied = error, applied
        else:
            self.state.charged.settle_child(child_id, usage)
        child.usage_settled = usage
        await tx.settle_delegation(
            child.delegation_id, status=child.state, usage_settled=usage, settled_seq=out_seq
        )
        if applied == "retry":
            # §17.6: a *new* child under the same contract; its EXTERNAL effects get new keys,
            # which is why `validate` refused retry over assume_failed tools.
            await self._spawn_one(
                tx, child.step_index, child.child_ordinal, child.retry_no + 1,
                Delegation.model_validate(contract), causation_seq=out_seq,
            )
        if applied == "fail_parent":
            # §17.6/§17.7: the parent will fail, so the subtree is cancelled first — asked now, in
            # this transaction, and forced after `cancel_grace` by the same wake that forces a
            # cancelled parent's children.
            await self._cancel_open_children(tx, child.step_index, causation_seq=out_seq, reason="sibling_failed")
        await self._fill_slots(tx, child.step_index, causation_seq=out_seq)
        return await self._maybe_settle_delegate(tx, child.step_index)

    def _fatal(self, step_index: int) -> bool:
        """A child of this step failed under `fail_parent`: the step will fail once the subtree is
        terminal. Derived from the fold alone, so every epoch — and every replay — agrees."""
        return any(
            c.state in ("FAILED", "CANCELLED") and c.policy_applied == "fail_parent"
            for c in self.state.children_of(step_index)
        )

    async def _cancel_open_children(self, tx: Any, step_index: int, *, causation_seq: int, reason: str) -> None:
        for c in self.state.children_of(step_index):
            if c.terminal or c.state == "CANCELLING":
                continue
            await tx.insert_signal(
                cancel_signal(
                    c.child_run_id,
                    client_key=f"cancel:{self.lease.run_id}:{causation_seq}",
                    by=f"parent:{self.lease.run_id}",
                    reason=reason,
                )
            )
            c.state = "CANCELLING"

    async def _fill_slots(self, tx: Any, step_index: int, *, causation_seq: int) -> None:
        """`delegate_many` past `max_children_in_flight` waits for a slot rather than failing
        (§17.5): the next unspawned ordinal starts as a terminal child frees one."""
        contracts = self._contracts_of(step_index)
        if contracts is None or self.state.cancel_acknowledged_at == step_index or self._fatal(step_index):
            return
        spawned = {c.child_ordinal for c in self.state.children_of(step_index)}
        in_flight = sum(1 for c in self.state.children_of(step_index) if not c.terminal)
        for ordinal in range(len(contracts)):
            if in_flight >= MAX_CHILDREN_IN_FLIGHT:
                return
            if ordinal in spawned:
                continue
            await self._spawn_one(
                tx, step_index, ordinal, 0, Delegation.model_validate(contracts[ordinal]),
                causation_seq=causation_seq,
            )
            in_flight += 1

    async def _maybe_settle_delegate(self, tx: Any, step_index: int) -> str | None:
        """The DELEGATE step settles when every ordinal's latest child is terminal — one outcome,
        the list of child results, which is all the program ever sees of them (§17.3)."""
        step = self.state.steps.get(step_index)
        if step is None or step.settled:
            return None
        contracts = self._contracts_of(step_index)
        latest = self._latest_children(step_index)
        if not latest or not all(c.terminal for c in latest):
            return None
        if (
            contracts is not None and len(latest) < len(contracts)
            and self.state.cancel_acknowledged_at != step_index and not self._fatal(step_index)
        ):
            return None  # ordinals still waiting for a slot
        if self.state.cancel_acknowledged_at == step_index:
            # §7.6.2: the acknowledged step closes with STEP_CANCELLED once the last child is
            # terminal, in whichever epoch observes it; RUN_CANCELLED follows from the worker.
            seq = await tx.append(StepCancelled(step_index=step_index, attempt_no=1))
            step.state, step.outcome_seq, step.outcome_epoch = CANCELLED, seq, self.lease.epoch
            await tx.set_run(phase="RUNNING", wake_at=None)
            return "cancel"
        fatal = [c for c in latest if c.state != "COMPLETED" and c.policy_applied == "fail_parent"]
        if fatal:
            error = f"ChildFailed: {fatal[0].error}"
            seq = await tx.append(
                StepFailedEvent(step_index=step_index, attempt_no=1, error=error, retryable=False)
            )
            step.state, step.error, step.retryable = FAILED, error, False
        else:
            result = [_child_result(c) for c in latest]
            seq = await tx.append(StepCompleted(step_index=step_index, attempt_no=1, result=result))
            step.state, step.result = COMPLETED, result
        step.outcome_seq, step.outcome_epoch = seq, self.lease.epoch
        await tx.set_run(phase="RUNNING", wake_at=None)
        return None

    async def _wait_children(self, intent: StepIntent, journaled: Any) -> bool:
        """Woken with the step still open: re-park, for the price of one row. True when parked;
        False when a signal raced the release and the caller must drain and decide again.

        With the subtree being cancelled — the parent's own cancel, or a `fail_parent` failure —
        the wake is also the moment to force (§7.6.2, §17.7): every child still open is offered to
        the store's takeover predicate, which refuses until the child has had `cancel_grace` to
        acknowledge on its own. A takeover commits the child's `child_result` into this inbox, so
        the caller's next drain settles the step.
        """
        i = intent.step_index
        stopping = self.state.cancel_acknowledged_at == i or self._fatal(i)
        if stopping:
            forced = False
            for c in [c for c in self.state.children_of(i) if not c.terminal]:
                outcome = await force_cancel(
                    self.journal,
                    c.child_run_id,
                    worker_id=self.lease.worker_id,
                    ttl_s=self.lease.ttl_seconds,
                    forced_by=f"parent:{self.lease.run_id}",
                    cancel_grace_s=self.cancel_grace_s,
                )
                forced = forced or outcome == "cancelled"
            if forced:
                return False  # a child_result is waiting in this inbox: drain it first
        parked = await self._commit_park(
            "children", i, phase="WAITING_CHILDREN", wake_in=self.cancel_grace_s if stopping else None
        )
        if parked:
            hooks.at("during:child_wait", step_index=i, wake_at=self.state.wake_at)
        return parked

    def _latest_children(self, step_index: int) -> list[ChildState]:
        """One child per ordinal — the highest retry — in ordinal order."""
        latest: dict[int, ChildState] = {}
        for c in self.state.children_of(step_index):
            if c.child_ordinal not in latest or c.retry_no > latest[c.child_ordinal].retry_no:
                latest[c.child_ordinal] = c
        return [latest[k] for k in sorted(latest)]

    def _contracts_of(self, step_index: int) -> list[dict[str, Any]] | None:
        w = self._waiting_intent
        if w is None or w.step_index != step_index or not w.args:
            return None
        return list(w.args.get("contracts") or [])

    def _remaining_tokens(self) -> int | None:
        """What the parent may still promise. Ordinals of the open DELEGATE step not yet spawned —
        waiting for a slot — were admitted at the INTENT commit against the whole fan-out, so their
        slices are spoken for: counting only spawned children would let a retry spend them twice
        (§17.4, Σ reservations ≤ remaining)."""
        limits = self.state.budget if isinstance(self.state.budget, dict) else {}
        cap = limits.get("max_tokens")
        if cap is None:
            return None
        promised = 0
        w = self._waiting_intent
        if w is not None and not self._fatal(w.step_index) and self.state.cancel_acknowledged_at != w.step_index:
            spawned = {c.child_ordinal for c in self.state.children_of(w.step_index)}
            promised = sum(
                int((c.get("budget_slice") or {}).get("max_tokens") or 0)
                for ordinal, c in enumerate(self._contracts_of(w.step_index) or [])
                if ordinal not in spawned
            )
        return int(cap) - self.state.charged.tokens_charged - promised

    def _admit_slice(self, slice_: dict[str, Any]) -> bool:
        remaining = self._remaining_tokens()
        return remaining is None or int(slice_.get("max_tokens") or 0) <= remaining

    def _child_version(self, program: str) -> str:
        if self.resolve_program is None:
            raise ContractInvalid("this engine cannot resolve child programs")
        try:
            return str(self.resolve_program(program).version)
        except KeelError as exc:
            raise ContractInvalid(str(exc)) from exc

    async def _live(self, intent: StepIntent) -> Any:
        await self._check_binding(intent)
        if intent.kind is StepKind.APPROVAL:
            return await self._park_for_approval(intent)
        if intent.kind is StepKind.DELEGATE:
            return await self._spawn_children(intent)
        if intent.kind is StepKind.SLEEP:
            return await self._park_for_sleep(intent)
        if intent.kind is StepKind.TOOL:
            await self._gate(intent)
        tool = self._tool_of(intent)
        timeout = self._timeout_of(intent, tool)
        eff_class = intent.effect_class
        reservation = await self._reserve(intent)
        try:
            admit(self.state.budget, self.state.charged, reservation)
        except BudgetExceeded as exc:
            await self._refuse(intent, exc)
        hooks.at("before:intent_commit", **_where(intent))
        async with self.journal.append(self.lease) as tx:
            intent_seq = await tx.append(_intended(intent))
            now = await tx.now()
            started_local = self._worker_now()
            deadline = now + timedelta(seconds=timeout) if eff_class and eff_class != EffectClass.PURE else None
            if intent.kind is StepKind.TOOL:
                await tx.write_effect(
                    EffectRow(
                        effect_key=intent.effect_key or "",
                        run_id=self.lease.run_id,
                        run_root_id=self.run_root_id,
                        step_index=intent.step_index,
                        tool=intent.name,
                        effect_class=str(eff_class),
                        status="INTENDED",
                        intent_seq=intent_seq,
                        modifiers=tuple(str(m) for m in intent.modifiers),
                    )
                )
            started_seq = await tx.append(
                StepAttemptStarted(
                    step_index=intent.step_index,
                    attempt_no=1,
                    lease_epoch=self.lease.epoch,
                    started_at=now,
                    attempt_deadline=deadline,
                    reservation=reservation.tokens or None,
                ),
                causation_seq=intent_seq,
            )
            if intent.kind is StepKind.TOOL:
                await tx.update_effect(
                    intent.effect_key or "",
                    status="STARTED",
                    started_seq=started_seq,
                    attempt_no=1,
                    attempt_deadline=deadline,
                )
            if deadline is not None:
                await tx.set_run(attempt_deadline=deadline)
        # INTENT and the first STARTED share one transaction, so both boundaries close together.
        # A crash *between* them is unreachable by construction, and that is exactly what the
        # INTENDED/RUNNING split in the recovery table relies on — the two names exist so a spec
        # can say which side of the commit it means, not because there is a gap between them.
        hooks.at("after:intent_commit", **_where(intent))
        hooks.at("after:attempt_commit", attempt_no=1, **_where(intent))
        self.state.charged.start(intent.step_index, 1, reservation.tokens or None, str(intent.kind))
        # ---- write-ahead barrier passed: the effect may now begin ----
        return await self._dispatch(intent, 1, started_seq, deadline, timeout, started_local)

    def _timeout_of(self, intent: StepIntent, tool: Any) -> float:
        if intent.kind is StepKind.TOOL:
            return getattr(tool, "timeout", DEFAULT_MODEL_TIMEOUT_S)
        return self.model_timeout_s

    async def _start_attempt(self, intent: StepIntent, attempt_no: int, *, close: Any = None) -> Any:
        """Close the previous attempt and open the next one in ONE transaction (§8.3).

        One transaction because the pair is the invariant: a crash between "that attempt is
        over" and "this attempt has begun" would leave the step settled with work still to do,
        and the successor would read a terminal outcome that was never terminal."""
        tool = self._tool_of(intent)
        timeout = self._timeout_of(intent, tool)
        eff_class = intent.effect_class
        reservation = await self._reserve(intent)
        try:
            admit(self.state.budget, self.state.charged, reservation)
        except BudgetExceeded as exc:
            await self._refuse(intent, exc, first=False)
        hooks.at("before:attempt_commit", attempt_no=attempt_no, **_where(intent))
        async with self.journal.append(self.lease) as tx:
            if close is not None:
                await tx.append(close)
            now = await tx.now()
            started_local = self._worker_now()
            deadline = now + timedelta(seconds=timeout) if eff_class and eff_class != EffectClass.PURE else None
            started_seq = await tx.append(
                StepAttemptStarted(
                    step_index=intent.step_index,
                    attempt_no=attempt_no,
                    lease_epoch=self.lease.epoch,
                    started_at=now,
                    attempt_deadline=deadline,
                    reservation=reservation.tokens or None,
                )
            )
            if intent.kind is StepKind.TOOL:
                await tx.update_effect(
                    intent.effect_key or "",
                    status="STARTED",
                    started_seq=started_seq,
                    attempt_no=attempt_no,
                    attempt_deadline=deadline,
                )
            if deadline is not None:
                await tx.set_run(attempt_deadline=deadline)
        # A re-attempt writes no INTENT — the step already has one — so only the attempt boundary
        # belongs here. Firing `after:intent_commit` again would let a spec aimed at "the intent"
        # fire on attempt three, which is a different window wearing the same name.
        hooks.at("after:attempt_commit", attempt_no=attempt_no, **_where(intent))
        self.state.charged.start(
            intent.step_index, attempt_no, reservation.tokens or None, str(intent.kind)
        )
        return await self._dispatch(intent, attempt_no, started_seq, deadline, timeout, started_local)

    async def _dispatch(
        self,
        intent: StepIntent,
        attempt_no: int,
        started_seq: int,
        deadline: datetime | None,
        timeout: float,
        started_local: datetime,
    ) -> Any:
        eff_class = intent.effect_class
        if eff_class is not None and eff_class != EffectClass.PURE:
            await self._pre_dispatch_gate(timeout)
        sctx = StepCtx(
            run_id=self.lease.run_id,
            run_root_id=self.run_root_id,
            attempt_no=attempt_no,
            clock=self.clock,
            deadline=deadline,
            effect_key=intent.effect_key,
            provider=self.provider,
            tools=self.tools,
        )
        executor = EXECUTORS[intent.kind]
        try:
            remaining = timeout if deadline is None else _remaining(started_local, timeout, self.clock)
            # The write-ahead barrier is behind us: STARTED is durable, so a crash here is the
            # window the whole recovery table exists for.
            hooks.at("before:effect_exec", attempt_no=attempt_no, **_where(intent))
            async with _waits(self.clock).timeout(remaining):
                outcome: StepOutcome = await executor.execute(intent, sctx)
            hooks.at("after:effect_exec", attempt_no=attempt_no, **_where(intent))
        except TimeoutError:
            # An EXTERNAL timeout is ambiguity, never failure: the request left the process and the
            # receiver's state is unknown — window W3 with the worker still alive (§8.5).
            outcome = (
                Ambiguous("timeout")
                if eff_class == EffectClass.EXTERNAL
                else Failed("timeout", retryable=True, unknown=True)
            )
        except UnknownOutcome as exc:
            # "Applied, then failed to answer" is the classic case, and it is indistinguishable
            # from "never applied" — so it is disposed exactly like a timeout (§11.5).
            outcome = (
                Ambiguous(f"error_response: {exc}")
                if eff_class == EffectClass.EXTERNAL
                else Failed(f"error_response: {exc}", retryable=True, unknown=True)
            )
        except Rejected as exc:
            # The receiver spoke plainly. Retrying a refusal only wastes an attempt.
            outcome = Failed(f"rejected: {exc}", retryable=False)
        except Exception as exc:  # noqa: BLE001 - a tool's own error is an outcome, not a crash
            outcome = Failed(f"{type(exc).__name__}: {exc}", retryable=False)
        return await self._commit_outcome(intent, attempt_no, started_seq, outcome)

    async def _pre_dispatch_gate(self, timeout: float) -> None:
        """require lease_valid_until - now >= tool.timeout; re-heartbeat, or abandon without
        executing (§8.4). Measured on the monotonic clock armed at heartbeat send time, so worker
        wall-clock skew is a non-fault for Keel."""
        loop = asyncio.get_running_loop()
        if self.lease.valid_until_mono - loop.time() >= timeout:
            return
        if await self.journal.heartbeat(self.lease, timedelta(seconds=self.lease.ttl_seconds)):
            if self.lease.valid_until_mono - loop.time() >= timeout:
                return
        raise Abandon("pre-dispatch lease margin too short")

    async def _commit_outcome(
        self, intent: StepIntent, attempt_no: int, started_seq: int, outcome: StepOutcome
    ) -> Any:
        is_tool = intent.kind is StepKind.TOOL
        key = intent.effect_key or ""
        # The retry decision is made *before* the outcome commits, so it is journaled with it: a
        # STEP_FAILED carrying `next_attempt_at` is a failure the runtime will retry, and a successor
        # that finds it retries rather than failing the run (§8.7, §11.5 `provider_outage`).
        policy = self.model_retry if intent.kind is StepKind.MODEL else self.retry
        retrying = isinstance(outcome, Failed) and outcome.retryable and policy.may_retry(attempt_no)
        if (
            isinstance(outcome, Failed) and outcome.unknown and not retrying
            and intent.effect_class == EffectClass.IDEMPOTENT
        ):
            # §9.1 (amended): the key makes a retry safe, and a retry is what turns "maybe applied"
            # into a known outcome. With none left, a clean FAILED would hide an effect the receiver
            # may hold, so the step is what it is — unknown — and the run waits for a human.
            return await self._key_window_expired(intent, attempt_no, started_seq, outcome.error)
        wait_s = 0.0
        if isinstance(outcome, (Completed, Failed)):
            self._breaker_saw(intent, ok=isinstance(outcome, Completed))
        if retrying:
            wait_s = max(
                policy.backoff_s(attempt_no),
                self._breaker_wait_s(intent),
            )
        next_attempt_at = None
        try:
            hooks.at("before:outcome_commit", attempt_no=attempt_no, **_where(intent))
            async with self.journal.append(self.lease) as tx:
                if retrying:
                    next_attempt_at = await tx.now() + timedelta(seconds=wait_s)
                if isinstance(outcome, Completed):
                    seq = await tx.append(
                        StepCompleted(
                            step_index=intent.step_index,
                            attempt_no=attempt_no,
                            result=outcome.result,
                            usage=outcome.usage,
                            provider_meta=outcome.provider_meta,
                        ),
                        causation_seq=started_seq,
                    )
                    if is_tool:
                        await tx.update_effect(
                            key, status="COMMITTED", outcome_seq=seq, external_ref=outcome.external_ref
                        )
                elif isinstance(outcome, Failed):
                    seq = await tx.append(
                        StepFailedEvent(
                            step_index=intent.step_index,
                            attempt_no=attempt_no,
                            error=outcome.error,
                            retryable=outcome.retryable,
                            next_attempt_at=next_attempt_at,
                        ),
                        causation_seq=started_seq,
                    )
                    if is_tool:
                        # A retry is coming. After an unknown outcome the receiver may already hold
                        # an IDEMPOTENT effect, so the row says AMBIGUOUS, not ABSENT, until the next
                        # attempt starts under the same key (§7.4, amended). Nothing reads it as
                        # outstanding: the reaper looks at STARTED rows only.
                        unknown = outcome.unknown and intent.effect_class == EffectClass.IDEMPOTENT
                        await tx.update_effect(key, status="AMBIGUOUS" if unknown else "ABSENT", outcome_seq=seq)
                else:
                    seq = await tx.append(
                        StepAmbiguous(
                            step_index=intent.step_index,
                            attempt_no=attempt_no,
                            cause=outcome.cause,
                        ),
                        causation_seq=started_seq,
                    )
                    if is_tool:
                        await tx.update_effect(key, status="AMBIGUOUS", outcome_seq=seq)
                if intent.effect_class not in (None, EffectClass.PURE):
                    await tx.set_run(attempt_deadline=None)
        except Fenced as exc:
            # The zombie's outcome append is rejected: the journal never records that effect (§8.4).
            raise Abandon("fenced at outcome commit") from exc
        # Durable. A crash from here on loses nothing but the in-memory return trip, which is the
        # difference between this boundary and the one before it.
        hooks.at("after:outcome_commit", attempt_no=attempt_no, **_where(intent))
        if isinstance(outcome, Completed):
            self.state.charged.settle(intent.step_index, attempt_no, outcome.usage)
            return outcome.result
        if isinstance(outcome, Failed):
            if retrying:
                # An EXTERNAL timeout never reaches here — it is AMBIGUOUS, because retrying a
                # request that left the process is exactly how systems duplicate effects (§8.5).
                if wait_s < PARK_BACKOFF_AFTER_S:
                    await _waits(self.clock).sleep(wait_s)  # inside the lease, with the heartbeat still running
                    return await self._start_attempt(intent, attempt_no + 1)
                return await self._retry_after_backoff(intent, attempt_no, next_attempt_at)
            raise StepFailed(intent.step_index, outcome.error, retryable=outcome.retryable)
        return await self._resolve(intent, attempt_no)

    async def _retry_after_backoff(self, intent: StepIntent, attempt_no: int, due: Any) -> Any:
        """A retry the journal already decided on: start it when `next_attempt_at` has passed and
        the provider's breaker lets an attempt through, and until then park at zero compute —
        `RUN_WAITING{retry_backoff}` with its release, woken by the timer sweep (§7.2.1, §11.5).
        Signals are drained first, so a cancel or pause sent during an outage is honoured."""
        while True:
            await self._drain_inbox(intent.step_index, force=self._paused)
            async with self.journal.append(self.lease) as tx:  # the fence alone: a heartbeat
                now = await tx.now()
            wake_at = max(due, now + timedelta(seconds=self._breaker_wait_s(intent)))
            if now >= wake_at:
                return await self._start_attempt(intent, attempt_no + 1)
            if await self._commit_park("retry_backoff", intent.step_index, phase="SLEEPING", wake_at=wake_at):
                raise Parked("retry_backoff", wake_at=wake_at)

    def _provider_key(self) -> str:
        return str(getattr(self.provider, "name", None) or "default")

    def _breaker_saw(self, intent: StepIntent, *, ok: bool) -> None:
        if self.breaker is None or intent.kind not in (StepKind.MODEL, StepKind.COMPACT):
            return
        if ok:
            self.breaker.success(self._provider_key())
        else:
            self.breaker.failure(self._provider_key(), self._worker_now())

    def _breaker_wait_s(self, intent: StepIntent) -> float:
        """How long the breaker holds the next MODEL attempt back. The breaker keeps the worker's
        clock; only this delta crosses into the store's, so the two clocks are never compared."""
        if self.breaker is None or intent.kind not in (StepKind.MODEL, StepKind.COMPACT):
            return 0.0
        now = self._worker_now()
        until = self.breaker.blocked_until(self._provider_key(), now)
        return max(0.0, (until - now).total_seconds()) if until is not None else 0.0

    def _worker_now(self) -> datetime:
        return self.clock.now() if self.clock is not None else datetime.now(UTC)

    # --- the journal-state recovery table (§8.3) -----------------------------
    async def _recover_open(self, intent: StepIntent, journaled: Any) -> Any:
        self.replayed_steps += 1
        if not self.allow_live:
            # Every branch below this line either re-attempts or resolves, and both are writes.
            # §10.9: VERIFY stops and reports rather than resolving, because resolution is a
            # decision about the world and a read-only pass has no standing to make one.
            raise StopReplay("in_flight_" + journaled.state.lower(), intent.step_index)
        cls = intent.effect_class
        state = journaled.state
        if journaled.kind in WAITING_KINDS and state == RUNNING:
            # A parked step, not an abandoned attempt. Its normal life *is* STARTED-without-outcome
            # — for days — so re-attempting it would mint a second `approval_id` and break S7's
            # "exactly one GRANTED approval per gated effect" (§7.3.1). The only thing that settles
            # it is a decision arriving through the inbox, so: drain, and park again if nothing
            # decided it.
            return await self._settle_waiting(intent, journaled)
        if state == INTENDED:
            # INTENT present, no STARTED for the current attempt: the effect provably never began.
            return await self._start_attempt(intent, journaled.attempts + 1)
        if state == RUNNING:
            # STARTED(n) with no outcome. The worker never knows where it died; the successor
            # decides from journal state alone.
            n = journaled.attempts
            if cls == EffectClass.EXTERNAL:
                async with self.journal.append(self.lease) as tx:
                    seq = await tx.append(
                        StepAmbiguous(step_index=intent.step_index, attempt_no=n, cause="crash")
                    )
                    await tx.update_effect(intent.effect_key or "", status="AMBIGUOUS", outcome_seq=seq)
                    await tx.set_run(attempt_deadline=None)
                return await self._resolve(intent, n)
            # PURE / MODEL re-run; IDEMPOTENT re-runs under the SAME effect_key, which the key
            # derivation guarantees: it is (run_root_id, step_index, tool, canonical_args), none of
            # which an attempt changes, so a receiver that honours the key applies it once (§8.3).
            #
            # This is recovery, not retry: a FAILED outcome still ends the run, because the MVP
            # runs one attempt and an unmeasured retry policy is a guess (day 4, §27.5). But an
            # attempt a crash abandoned has no outcome to retry from, and refusing to re-run it
            # would fail every run the IDEMPOTENT band exists to measure.
            return await self._start_attempt(
                intent,
                n + 1,
                close=StepFailedEvent(
                    step_index=intent.step_index,
                    attempt_no=n,
                    error="attempt_abandoned",
                    retryable=True,
                ),
            )
        if state == AMBIGUOUS:
            return await self._resolve(intent, journaled.attempts)
        if state == FAILED:
            if journaled.retryable and journaled.next_attempt_at is not None:
                # The retry was decided and journaled with the failure; a successor honours the
                # journal's decision rather than re-deciding it under whatever policy it now has.
                return await self._retry_after_backoff(intent, journaled.attempts, journaled.next_attempt_at)
            raise StepFailed(intent.step_index, journaled.error or "failed", retryable=journaled.retryable)
        raise Suspended("unrecoverable_step_state", {"step_index": intent.step_index, "state": state})

    async def _key_window_expired(self, intent: StepIntent, attempt_no: int, started_seq: int, error: str) -> Any:
        """An IDEMPOTENT attempt whose outcome is unknown, with no attempt left to resolve it under
        the same key: AMBIGUOUS, then RESOLVED_UNKNOWN by `key_window_expired`, one transaction —
        the EXTERNAL `escalate` path, so replay, VERIFY, C3 and the human's decision are one path."""
        async with self.journal.append(self.lease) as tx:
            await tx.append(
                StepAmbiguous(step_index=intent.step_index, attempt_no=attempt_no, cause=error),
                causation_seq=started_seq,
            )
            seq = await tx.append(
                StepResolved(
                    step_index=intent.step_index,
                    attempt_no=attempt_no,
                    resolution="RESOLVED_UNKNOWN",
                    method="key_window_expired",
                    evidence={"reason": "no attempt left to resolve an unknown outcome under the same key"},
                )
            )
            await tx.update_effect(intent.effect_key or "", status="RESOLVED_UNKNOWN", outcome_seq=seq)
            await tx.set_run(attempt_deadline=None)
        hooks.at("after:outcome_commit", attempt_no=attempt_no, **_where(intent))
        raise Suspended("key_window_expired", {"step_index": intent.step_index})

    async def _resolve(self, intent: StepIntent, attempt_no: int) -> Any:
        """The tool's declared resolution. MVP ships `escalate` (the default) and, from day 2,
        `probe`; `assume_failed` / `assume_succeeded` are v1 opinion-carrying resolutions (§27.5)."""
        tool = self._tool_of(intent)
        resolution = getattr(tool, "resolution", "escalate")
        probe = getattr(tool, "probe", None)
        if resolution == "probe" and probe is not None:
            outcome = await self._probe(intent, probe, attempt_no)
            if outcome is not _UNRESOLVED:
                return outcome
        async with self.journal.append(self.lease) as tx:
            seq = await tx.append(
                StepResolved(
                    step_index=intent.step_index,
                    attempt_no=attempt_no,
                    resolution="RESOLVED_UNKNOWN",
                    method="escalate",
                    evidence={"reason": "no probe declared" if probe is None else "probe UNKNOWN"},
                )
            )
            await tx.update_effect(intent.effect_key or "", status="RESOLVED_UNKNOWN", outcome_seq=seq)
        raise Suspended("resolved_unknown", {"step_index": intent.step_index})

    async def _probe(self, intent: StepIntent, probe: Any, attempt_no: int) -> Any:
        """Ask the receiver. Three answers, and three different things to do (§7.4).

        # ponytail: `events_resolved_once` is UNIQUE on (run_id, step_index, method), so a step
        # may carry one probe resolution. A second becomes reachable only when timeouts start
        # producing ambiguity (day 4); that is the phase that should decide whether the guard
        # grows an attempt_no.
        """
        sctx = StepCtx(
            run_id=self.lease.run_id,
            run_root_id=self.run_root_id,
            attempt_no=attempt_no,
            clock=self.clock,
            effect_key=intent.effect_key,
            tools=self.tools,
        )
        result = await probe(intent.effect_key, intent.args, sctx)
        if result.verdict == "UNKNOWN":
            return _UNRESOLVED
        if result.verdict == "ABSENT":
            return await self._reattempt_after_absent(intent, attempt_no, result)
        value = result.result
        if value is None:
            # The worker was killed before it received the response; anything not read back from
            # the receiver would be invented. The sentinel is the one honest option (§23.4).
            value = {
                "__keel_resolved__": "COMMITTED",
                "effect_key": intent.effect_key,
                "evidence": result.evidence,
            }
        async with self.journal.append(self.lease) as tx:
            seq = await tx.append(
                StepResolved(
                    step_index=intent.step_index,
                    attempt_no=attempt_no,
                    resolution="RESOLVED_COMPLETED",
                    method="probe",
                    evidence={"evidence": result.evidence, "result": value},
                )
            )
            await tx.update_effect(
                intent.effect_key or "",
                status="RESOLVED_COMMITTED",
                outcome_seq=seq,
                resolution="probe",
                external_ref=result.external_ref,
            )
        return value

    async def _reattempt_after_absent(self, intent: StepIntent, attempt_no: int, result: Any) -> Any:
        """ABSENT is neither a failure nor a guess: the receiver is saying the effect never
        landed, which is the recovery table's "provably nothing happened" case one level down.
        So the step takes §7.4's at-least-once edge, RESOLVED_ABSENT -> STARTED(n+1), under the
        same effect_key — the trace §11.2 predicts for `pause_past_ttl@before:tool_call`, and
        the reason T1 is a recovered cell rather than a failed one.

        The resolution and the re-attempt commit together, or a crash between them would leave
        the successor reading a settled RESOLVED_FAILED and failing a run whose effect provably
        never happened."""
        return await self._start_attempt(
            intent,
            attempt_no + 1,
            close=StepResolved(
                step_index=intent.step_index,
                attempt_no=attempt_no,
                resolution="RESOLVED_FAILED",
                method="probe",
                evidence={"evidence": result.evidence, "verdict": "ABSENT"},
            ),
        )

    def _tool_of(self, intent: StepIntent) -> Any:
        if intent.kind is not StepKind.TOOL or self.tools is None:
            return None
        return self.tools.get(intent.name)


_SYSTEM_CLOCK = SystemClock()


def _waits(clock: Any) -> Any:
    """The clock every wait goes through (§12.2). An engine built without one — VERIFY's, which
    never waits — gets the system clock rather than a second code path, and so does a caller's own
    clock that tells the time but cannot wait (`Keel(clock=)` took `now()` alone before the seam)."""
    return clock if clock is not None and hasattr(clock, "timeout") else _SYSTEM_CLOCK


def _remaining(started_local: datetime, timeout: float, clock: Any = None) -> float:
    """Count down from the STARTED commit, not from dispatch (§5.10): the time between the commit
    and the send is spent from the attempt's budget. The journaled `attempt_deadline` is on the
    store's clock and is never compared with the worker's; only time elapsed on the worker's own
    clock since it read the store's is subtracted. Comparing the two clocks directly made every
    call time out on arrival once Docker's VM clock fell a second behind the host's."""
    now = clock.now() if clock is not None else datetime.now(UTC)
    return max(0.001, timeout - (now - started_local).total_seconds())


def _where(intent: StepIntent) -> dict[str, Any]:
    """What a hook is told about the step it fired inside.

    The *name* travels beside the index on purpose. A step index is an ordinal in one runtime's
    traffic, and a spec written in ordinals is the thing §11.3 forbids; carrying `kind` and `name`
    lets a hook spec say `tool:create_issue` in exactly the vocabulary the shim already uses. The
    index comes too, because a white-box table may legitimately want to address one occurrence.
    """
    return {
        "step_index": intent.step_index,
        "kind": str(intent.kind).lower(),
        "name": intent.name,
    }


def _intended(intent: StepIntent) -> StepIntended:
    return StepIntended(
        step_index=intent.step_index,
        kind=str(intent.kind),
        name=intent.name,
        args_hash=intent.args_hash,
        args=intent.args,
        request_hash=intent.request_hash,
        effect_key=intent.effect_key,
        effect_class=str(intent.effect_class) if intent.effect_class else None,
        modifiers=tuple(str(m) for m in intent.modifiers),
        program_version=intent.program_version,
    )


def _value_of(step: Any) -> Any:
    if step.state in ("COMPLETED", "RESOLVED_COMPLETED"):
        return step.result
    raise StepFailed(step.step_index, step.error or step.state, retryable=step.retryable)


def _child_result(c: ChildState) -> dict[str, Any]:
    """What a DELEGATE step's outcome carries per child — `ChildResult`'s fields, as JSON."""
    return {
        "child_run_id": str(c.child_run_id),
        "status": c.state.lower(),
        "result": c.result,
        "error": c.error,
        "usage_settled": dict(c.usage_settled or {}),
    }


# --- runtime-owned executors -------------------------------------------------
class _ModelExecutor:
    kind = StepKind.MODEL

    async def execute(self, intent: StepIntent, sctx: StepCtx) -> StepOutcome:
        req = ModelRequest.model_validate(intent.args)
        resp = await sctx.provider.complete(req)
        return Completed(
            result=resp.model_dump(mode="json"),
            usage=resp.usage.model_dump(),
            provider_meta=resp.provider_meta,
        )


class _NowExecutor:
    kind = StepKind.NOW

    async def execute(self, intent: StepIntent, sctx: StepCtx) -> StepOutcome:
        return Completed(result=sctx.clock.now().isoformat())


class _RandomExecutor:
    kind = StepKind.RANDOM

    async def execute(self, intent: StepIntent, sctx: StepCtx) -> StepOutcome:
        return Completed(result=_random.random())


register(_ModelExecutor())
register(_NowExecutor())
register(_RandomExecutor())
