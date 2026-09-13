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

from keel.core.errors import Cancelled, Fenced, StepFailed, Rejected, UnknownOutcome
from keel.core.errors import NondeterminismDetected
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
from keel.events import (
    ApprovalDecided,
    ApprovalRequested,
    CancelAcknowledged,
    RecoveryCompleted,
    RunPaused,
    RunWaiting,
    SignalIgnored,
    SignalReceived,
    StepAmbiguous,
    StepAttemptStarted,
    StepCompleted,
    StepFailed as StepFailedEvent,
    StepIntended,
    StepResolved,
)
from keel.journal.protocol import EffectRow, JournalBackend, Lease
from keel.providers.protocol import ModelRequest
from keel.runtime import hooks
from keel.runtime.budget import BudgetExceeded, Reservation, admit, reserve_model, reserve_tool
from keel.runtime.retry import NO_RETRY, RetryPolicy
from keel.state.fold import (
    AMBIGUOUS,
    COMPLETED,
    FAILED,
    INTENDED,
    RESOLVED_UNKNOWN,
    RUNNING,
    WAITING_KINDS,
    RunState,
)

EXECUTORS: dict[StepKind, StepExecutor] = {}

#: A model call with no bound is an unbounded wait, which is the weak behaviour the `model_timeout`
#: cell exists to catch — so MODEL steps get a deadline like everything else. Generous by default
#: and pinned small in the benchmark, where a trial cannot afford to wait a minute to learn nothing.
DEFAULT_MODEL_TIMEOUT_S = 60.0

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
    """A `pause` signal was drained. RUN_PAUSED is already committed; the worker releases the lease
    with `runnable_at = NULL`, so the run costs nothing until a `resume` signal wakes it (§4.10)."""


class Parked(Exception):
    """The run is waiting on something that is not compute, and RUN_WAITING is already committed.

    The worker releases the lease with `lease_expires_at = NULL` *and* `runnable_at = NULL`, keeping
    only `wake_at`. Both NULLs matter: the first is what makes the wait cost no compute, the second
    is what makes it cost no *ticks* — no worker holds the run and no scheduler polls it. Days pass
    for the price of one row (§4.2).
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
        model_timeout_s: float = DEFAULT_MODEL_TIMEOUT_S,
        allow_live: bool = True,
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
        self.model_timeout_s = model_timeout_s
        #: VERIFY (§10.9). One flag rather than a second loop: a separate replayer would drift from
        #: this one, and the drift would be invisible — VERIFY would keep passing while the thing
        #: it is supposed to be checking had changed underneath it.
        self.allow_live = allow_live
        self.live_from_step: int | None = None
        self.replayed_steps = 0
        self.recovery_completed = False

    # --- public entry --------------------------------------------------------
    async def execute(self, intent: StepIntent) -> Any:
        # A cancel acknowledged at this index is raised here on every pass, live or replay. On the
        # original pass the drain below has just appended CANCEL_ACKNOWLEDGED; on every later one
        # the journal says where it landed, and raising at exactly that index is what makes a
        # cancelled run reproducible rather than a run that stopped somewhere near there (§4.10).
        if self.state.cancel_acknowledged_at == intent.step_index:
            raise Cancelled(f"cancelled at step {intent.step_index}")
        journaled = self.state.step(intent.step_index)
        if journaled is not None:
            if journaled.identity() != intent.identity():
                raise NondeterminismDetected(
                    intent.step_index, journaled.identity(), intent.identity()
                )
            if journaled.settled:
                self.replayed_steps += 1
                return _value_of(journaled)
            if journaled.state == RESOLVED_UNKNOWN:
                raise Suspended("resolved_unknown", {"step_index": intent.step_index})
            return await self._recover_open(intent, journaled)
        # The one boundary where stopping is free: everything behind is journaled, nothing ahead
        # has been attempted. An in-flight step is never interrupted — it is already bounded by
        # `asyncio.timeout(tool.timeout)`, which is what `shutdown_grace` must exceed.
        if self.should_drain is not None and self.should_drain():
            raise Drain(f"draining at step {intent.step_index}")
        await self._drain_inbox(intent.step_index)
        await self._reach_live(intent.step_index)
        return await self._live(intent)

    # --- the inbox drain (§4.3, §4.10) ---------------------------------------
    async def _drain_inbox(self, step_index: int, waiting: Any = None) -> None:
        """Apply every unconsumed signal, at the boundary before the step they precede.

        At *every* step boundary, not only at acquisition. Without that, a cancel sent to a held
        run in the middle of a forty-step loop would not be seen until the run parked or ended,
        "acknowledged at the next step boundary" would be false, and a busy child could not honour
        its parent's `cancel_grace`. The cost is one indexed read of
        `signals(run_id) WHERE consumed_seq IS NULL`.

        Only on the live path. A memoized step re-reads a decision already journaled, and draining
        there would let a signal that arrived *after* the original pass change what a replay does —
        the journal would stop being the whole history of the run.
        """
        if not self.allow_live or not hasattr(self.journal, "pending_signals"):
            return
        pending = await self.journal.pending_signals(self.lease.run_id)
        if not pending:
            return

        cancel = pause = False
        async with self.journal.append(self.lease) as tx:
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
                pause = pause or applied == "pause"
        # Cancel outranks pause: a run that has been told to stop for good does not first stop for
        # a while. Both are raised after the commit, so the journal is already durable when the
        # program is told.
        if cancel:
            raise Cancelled(f"cancelled at step {step_index}")
        if pause:
            raise Paused(f"paused at step {step_index}")

    async def _decide_approval(self, tx: Any, row: Any, seq: int, waiting: Any, now: Any) -> None:
        """`approve` / `reject` / `timer`, against the open approval. §7.5's rules, in order.

        The ordering rule is the subtle one, and it is deliberately not "first row wins". Expiry is
        judged by the store's clock at drain time and **outranks seq order**: an `approve` drained
        after `expires_at` is ignored and the approval expires, whether or not the timer row has
        arrived. Otherwise a decision made in time but drained late — a worker that died and took
        four seconds to be replaced — would be honoured on the wrong side of a deadline somebody
        else is relying on.
        """
        approval = self.state.approval_at(waiting.step_index) if waiting is not None else None
        if approval is None:
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=row.type, reason="unknown_approval"),
                causation_seq=seq,
            )
            return None
        if approval.terminal:
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=row.type, reason="approval_terminal"),
                causation_seq=seq,
            )
            return None

        expired = approval.expires_at is not None and now is not None and now >= approval.expires_at
        if row.type == "timer" and not expired:
            # A timer that fired early, or one that raced a decision. Consumed, not acted on.
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=row.type, reason="not_yet_expired"),
                causation_seq=seq,
            )
            return None
        if expired and row.type != "timer":
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=row.type, reason="expired"),
                causation_seq=seq,
            )
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
        await tx.append(
            StepCompleted(
                step_index=approval.step_index,
                attempt_no=1,
                result={"decision": decision, "by": by, "decided_at": str(now) if now else None},
            ),
            causation_seq=decided_seq,
        )
        await tx.set_run(phase="RUNNING", wake_at=None)
        # The engine's own fold is advanced in place: the rest of this drain, and the step that
        # follows it, read `state` rather than re-reading the journal.
        approval.state = {"granted": "GRANTED", "rejected": "REJECTED", "expired": "EXPIRED"}[decision]
        approval.by = by
        step = self.state.steps.get(approval.step_index)
        if step is not None:
            step.state = COMPLETED
            step.result = {"decision": decision, "by": by}
        return None

    async def _settle_waiting(self, intent: StepIntent, journaled: Any) -> Any:
        """A parked step, woken. Drain; if a decision arrived the step is settled and its value is
        returned, and if not the run parks again for the price of one row."""
        await self._drain_inbox(intent.step_index, waiting=journaled)
        settled = self.state.step(intent.step_index)
        if settled is not None and settled.settled:
            return _value_of(settled)
        approval = self.state.approval_at(intent.step_index)
        wake_at = approval.expires_at if approval else None
        # Park *again*, with its own RUN_WAITING. The acquisition already appended
        # RECOVERY_STARTED, which moves the run to RUNNING — so without this the fold would report
        # a parked run as running for ever after its first spurious wake, and `keel runs` would
        # show a queue of work nobody is doing. A re-park is a real transition and is journaled.
        async with self.journal.append(self.lease) as tx:
            await tx.append(
                RunWaiting(reason="approval", wake_at=wake_at, step_index=intent.step_index)
            )
            await tx.set_run(phase="WAITING_APPROVAL", wake_at=wake_at)
        raise Parked("approval", wake_at=wake_at)

    async def _apply_signal(
        self, tx: Any, row: Any, seq: int, step_index: int, waiting: Any = None, now: Any = None
    ) -> str | None:
        """What the run does about one signal, judged from its state *now* rather than at insert.

        This is the half that makes an at-least-once inbox safe: a second `cancel` for a run already
        cancelling, or a `resume` for a run that is not paused, is consumed and journaled as
        SIGNAL_IGNORED with the reason. Nothing is refused at the API; everything is decided here.
        """
        kind = row.type
        if kind in ("approve", "reject", "timer"):
            return await self._decide_approval(tx, row, seq, waiting, now)
        if kind == "cancel":
            if self.state.cancel_acknowledged_at is not None:
                await tx.append(
                    SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason="already_cancelling"),
                    causation_seq=seq,
                )
                return None
            await tx.append(CancelAcknowledged(step_index=step_index), causation_seq=seq)
            self.state.cancel_acknowledged_at = step_index
            return "cancel"
        if kind == "pause":
            await tx.append(RunPaused(step_index=step_index), causation_seq=seq)
            await tx.set_run(phase="PAUSED")
            return "pause"
        if kind == "resume":
            # A resume for a run that is already running is the ordinary shape of a retried click,
            # not an error: the signal is what woke the worker, and the worker is already here.
            await tx.append(
                SignalIgnored(signal_id=row.signal_id, signal_type=kind, reason="not_paused"),
                causation_seq=seq,
            )
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

    async def _refuse(self, intent: StepIntent, exc: BudgetExceeded) -> None:
        """A pre-dispatch refusal: attempt_no 0, never retryable, no attempt and so no bill."""
        async with self.journal.append(self.lease) as tx:
            await tx.append(
                StepFailedEvent(
                    step_index=intent.step_index, attempt_no=0, error=str(exc), retryable=False
                )
            )
        raise StepFailed(intent.step_index, str(exc), retryable=False)

    # --- live path (§5.10 transaction shapes) --------------------------------
    async def _park_for_approval(self, intent: StepIntent) -> Any:
        """One transaction, then days of nothing.

        INTENT, STARTED, APPROVAL_REQUESTED and RUN_WAITING commit together, and the same
        transaction NULLs both `lease_expires_at` and `runnable_at`. A crash anywhere in here
        leaves either no step at all or a parked one — never a half-requested approval, and never
        a second `approval_id` for one gate (§7.3.1, §7.5).
        """
        from uuid import uuid4

        payload = dict(intent.args or {})
        expires_in = payload.pop("expires_in", None)
        binds = payload.pop("binds_effect_key", None)
        approval_id = uuid4()
        hooks.at("before:intent_commit", **_where(intent))
        async with self.journal.append(self.lease) as tx:
            now = await tx.now()
            expires_at = now + timedelta(seconds=float(expires_in)) if expires_in else None
            intent_seq = await tx.append(_intended(intent))
            hooks.at("after:intent_commit", **_where(intent))
            await tx.append(
                StepAttemptStarted(
                    step_index=intent.step_index,
                    attempt_no=1,
                    lease_epoch=self.lease.epoch,
                    started_at=now,
                ),
                causation_seq=intent_seq,
            )
            hooks.at("after:attempt_commit", attempt_no=1, **_where(intent))
            await tx.append(
                ApprovalRequested(
                    step_index=intent.step_index,
                    approval_id=approval_id,
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
            await tx.set_run(phase="WAITING_APPROVAL", wake_at=expires_at)
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

    async def _live(self, intent: StepIntent) -> Any:
        if intent.kind is StepKind.APPROVAL:
            return await self._park_for_approval(intent)
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
        return await self._dispatch(intent, 1, started_seq, deadline, timeout)

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
            await self._refuse(intent, exc)
        hooks.at("before:attempt_commit", attempt_no=attempt_no, **_where(intent))
        async with self.journal.append(self.lease) as tx:
            if close is not None:
                await tx.append(close)
            now = await tx.now()
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
        return await self._dispatch(intent, attempt_no, started_seq, deadline, timeout)

    async def _dispatch(
        self,
        intent: StepIntent,
        attempt_no: int,
        started_seq: int,
        deadline: datetime | None,
        timeout: float,
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
            remaining = _remaining(deadline, timeout, self.clock)
            # The write-ahead barrier is behind us: STARTED is durable, so a crash here is the
            # window the whole recovery table exists for.
            hooks.at("before:effect_exec", attempt_no=attempt_no, **_where(intent))
            async with asyncio.timeout(remaining):
                outcome: StepOutcome = await executor.execute(intent, sctx)
            hooks.at("after:effect_exec", attempt_no=attempt_no, **_where(intent))
        except TimeoutError:
            # An EXTERNAL timeout is ambiguity, never failure: the request left the process and the
            # receiver's state is unknown — window W3 with the worker still alive (§8.5).
            outcome = (
                Ambiguous("timeout")
                if eff_class == EffectClass.EXTERNAL
                else Failed("timeout", retryable=True)
            )
        except UnknownOutcome as exc:
            # "Applied, then failed to answer" is the classic case, and it is indistinguishable
            # from "never applied" — so it is disposed exactly like a timeout (§11.5).
            outcome = (
                Ambiguous(f"error_response: {exc}")
                if eff_class == EffectClass.EXTERNAL
                else Failed(f"error_response: {exc}", retryable=True)
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
        try:
            hooks.at("before:outcome_commit", attempt_no=attempt_no, **_where(intent))
            async with self.journal.append(self.lease) as tx:
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
                        ),
                        causation_seq=started_seq,
                    )
                    if is_tool:
                        await tx.update_effect(key, status="ABSENT", outcome_seq=seq)
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
            if outcome.retryable and self.retry.may_retry(attempt_no):
                # An EXTERNAL timeout never reaches here — it is AMBIGUOUS, because retrying a
                # request that left the process is exactly how systems duplicate effects (§8.5).
                delay = self.retry.backoff_s(attempt_no, lease_ttl_s=self.lease.ttl_seconds)
                await asyncio.sleep(delay)  # inside the lease, with the heartbeat still running
                return await self._start_attempt(intent, attempt_no + 1)
            raise StepFailed(intent.step_index, outcome.error, retryable=outcome.retryable)
        return await self._resolve(intent, attempt_no)

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
            raise StepFailed(intent.step_index, journaled.error or "failed", retryable=journaled.retryable)
        raise Suspended("unrecoverable_step_state", {"step_index": intent.step_index, "state": state})

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


def _remaining(deadline: datetime | None, timeout: float, clock: Any = None) -> float:
    """Count down to the *journaled* attempt_deadline, not to a fresh timeout measured from
    dispatch (§5.10). Read through the run's own clock, so the residual is clock-read skew between
    the worker and Postgres and nothing more."""
    if deadline is None:
        return timeout
    now = clock.now() if clock is not None else datetime.now(UTC)
    return max(0.001, (deadline - now).total_seconds())


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
