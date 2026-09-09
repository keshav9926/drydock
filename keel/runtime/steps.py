"""The step executor: INTENT -> STARTED barrier -> execute -> outcome, and the per-class recovery
table (§8.3). This is the module the whole thesis rests on.

`runtime` imports no sibling package. TOOL steps are executed by an executor that `keel.effects`
registers into `EXECUTORS` at import time; MODEL/NOW/RANDOM are runtime-owned because they need
nothing but the provider (§23.2).
"""

from __future__ import annotations

import asyncio
import random as _random
from datetime import UTC, datetime, timedelta
from typing import Any

from keel.core.errors import Fenced, StepFailed
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
    RecoveryCompleted,
    StepAmbiguous,
    StepAttemptStarted,
    StepCompleted,
    StepFailed as StepFailedEvent,
    StepIntended,
    StepResolved,
)
from keel.journal.protocol import EffectRow, JournalBackend, Lease
from keel.providers.protocol import ModelRequest
from keel.state.fold import AMBIGUOUS, FAILED, INTENDED, RESOLVED_UNKNOWN, RUNNING, RunState

EXECUTORS: dict[StepKind, StepExecutor] = {}

# MVP: one attempt. An unmeasured retry is a guess; retry policy is day 4 (§27.5).
MAX_ATTEMPTS = 1


def register(executor: StepExecutor) -> StepExecutor:
    EXECUTORS[executor.kind] = executor
    return executor


class Abandon(Exception):
    """Leave the run without journaling anything: the pre-dispatch gate refused, or the fence went
    away mid-attempt. The successor disposes the open step from journal state alone (§8.2)."""


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
    ) -> None:
        self.journal = journal
        self.lease = lease
        self.state = state
        self.run_root_id = run_root_id
        self.provider = provider
        self.tools = tools
        self.clock = clock
        self.live_from_step: int | None = None
        self.replayed_steps = 0
        self.recovery_completed = False

    # --- public entry --------------------------------------------------------
    async def execute(self, intent: StepIntent) -> Any:
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
        await self._reach_live(intent.step_index)
        return await self._live(intent)

    async def _reach_live(self, step_index: int) -> None:
        """RECOVERY_COMPLETED is appended on reaching the first un-journaled step (§5.5)."""
        if self.recovery_completed:
            return
        self.live_from_step = step_index
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

    # --- live path (§5.10 transaction shapes) --------------------------------
    async def _live(self, intent: StepIntent) -> Any:
        tool = self._tool_of(intent)
        timeout = getattr(tool, "timeout", 60.0)
        eff_class = intent.effect_class
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
        # ---- write-ahead barrier passed: the effect may now begin ----
        return await self._dispatch(intent, 1, started_seq, deadline, timeout)

    async def _start_attempt(
        self, intent: StepIntent, attempt_no: int, *, close: tuple[int, str] | None = None
    ) -> Any:
        """Close an abandoned attempt and open the next one in ONE transaction (§8.3)."""
        tool = self._tool_of(intent)
        timeout = getattr(tool, "timeout", 60.0)
        eff_class = intent.effect_class
        async with self.journal.append(self.lease) as tx:
            if close is not None:
                await tx.append(
                    StepFailedEvent(
                        step_index=intent.step_index,
                        attempt_no=close[0],
                        error=close[1],
                        retryable=True,
                    )
                )
            now = await tx.now()
            deadline = now + timedelta(seconds=timeout) if eff_class and eff_class != EffectClass.PURE else None
            started_seq = await tx.append(
                StepAttemptStarted(
                    step_index=intent.step_index,
                    attempt_no=attempt_no,
                    lease_epoch=self.lease.epoch,
                    started_at=now,
                    attempt_deadline=deadline,
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
            async with asyncio.timeout(remaining):
                outcome: StepOutcome = await executor.execute(intent, sctx)
        except TimeoutError:
            # An EXTERNAL timeout is ambiguity, never failure: the request left the process and the
            # receiver's state is unknown — window W3 with the worker still alive (§8.5).
            outcome = (
                Ambiguous("timeout")
                if eff_class == EffectClass.EXTERNAL
                else Failed("timeout", retryable=True)
            )
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
        if isinstance(outcome, Completed):
            return outcome.result
        if isinstance(outcome, Failed):
            raise StepFailed(intent.step_index, outcome.error, retryable=outcome.retryable)
        return await self._resolve(intent, attempt_no)

    # --- the journal-state recovery table (§8.3) -----------------------------
    async def _recover_open(self, intent: StepIntent, journaled: Any) -> Any:
        self.replayed_steps += 1
        cls = intent.effect_class
        state = journaled.state
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
            if n >= MAX_ATTEMPTS:
                # PURE / IDEMPOTENT / MODEL are safe to re-run, but MVP allows one attempt only.
                async with self.journal.append(self.lease) as tx:
                    await tx.append(
                        StepFailedEvent(
                            step_index=intent.step_index,
                            attempt_no=n,
                            error="attempt_abandoned",
                            retryable=True,
                        )
                    )
                    if intent.kind is StepKind.TOOL:
                        await tx.update_effect(intent.effect_key or "", status="ABSENT")
                    await tx.set_run(attempt_deadline=None)
                raise StepFailed(intent.step_index, "attempt_abandoned", retryable=True)
            return await self._start_attempt(
                intent, n + 1, close=(n, "attempt_abandoned")
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
            verdict = await self._probe(intent, probe)
            if verdict is not None:
                return verdict
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

    async def _probe(self, intent: StepIntent, probe: Any) -> Any:
        """Day 2 wires the World oracle behind this; the shape is fixed on day 1 so `escalate` and
        `probe` share one code path."""
        sctx = StepCtx(
            run_id=self.lease.run_id,
            run_root_id=self.run_root_id,
            attempt_no=0,
            clock=self.clock,
            effect_key=intent.effect_key,
            tools=self.tools,
        )
        result = await probe(intent.effect_key, intent.args, sctx)
        if result.verdict == "UNKNOWN":
            return None
        resolution = "RESOLVED_COMPLETED" if result.verdict == "COMMITTED" else "RESOLVED_FAILED"
        value = result.result
        if result.verdict == "COMMITTED" and value is None:
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
                    attempt_no=0,
                    resolution=resolution,
                    method="probe",
                    evidence={"evidence": result.evidence, "result": value},
                )
            )
            await tx.update_effect(
                intent.effect_key or "",
                status="RESOLVED_COMMITTED" if result.verdict == "COMMITTED" else "RESOLVED_ABSENT",
                outcome_seq=seq,
                resolution="probe",
                external_ref=result.external_ref,
            )
        if resolution == "RESOLVED_FAILED":
            raise StepFailed(intent.step_index, result.evidence, retryable=False)
        return value

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
