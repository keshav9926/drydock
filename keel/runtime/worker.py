"""The worker: claim, hold one lease per run, heartbeat with the fence statement, re-execute the
program from the journal, and release (§4.2, §5.5).

Every lease acquisition — start, wake, orphan takeover, manual resume — is the same memoized
re-execution. Recovery is not a special path.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import time
from datetime import UTC, datetime, timedelta
from collections.abc import Callable
from typing import Any

from keel.core.errors import Cancelled, Fenced, NondeterminismDetected, StepFailed
from keel.core.ids import RunId
from keel.events import (
    RecoveryCompleted,
    RecoveryStarted,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunSuspended,
)
from keel.journal.protocol import JournalBackend, Lease, RunRow
from keel.core.errors import StoreUnavailable
from keel.runtime import hooks
from keel.runtime.ctx import Ctx
from keel.runtime.breaker import CircuitBreaker
from keel.runtime.delegation import MAX_DELEGATION_DEPTH, child_result_signal, usage_of
from keel.runtime.retry import NO_RETRY, RetryPolicy
from keel.runtime.steps import Abandon, Drain, Parked, Paused, StepEngine, Suspended, _waits
from keel.runtime.takeover import DEFAULT_CANCEL_GRACE_S
from keel.state.fold import fold

DEFAULT_LEASE_TTL = 30.0
HEARTBEAT_DIVISOR = 3  # heartbeat period <= ttl/3 (§8.7)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def _depth(journal: JournalBackend, row: RunRow) -> int:
    """How many parents above this run — the control-plane rows only, never a journal (§17.3).
    Bounded, so a cycle nobody should be able to write cannot make a worker walk for ever."""
    depth = 0
    parent = row.parent_run_id
    while parent is not None and depth <= MAX_DELEGATION_DEPTH:
        depth += 1
        up = await journal.run_row(parent)
        parent = up.parent_run_id if up is not None else None
    return depth


class Worker:
    def __init__(
        self,
        journal: JournalBackend,
        *,
        resolve: Callable[[str], Any],
        provider: Any = None,
        tools: Any = None,
        clock: Any = None,
        worker_id: str | None = None,
        lease_ttl: float = DEFAULT_LEASE_TTL,
        shutdown_grace: float = 10.0,
        poll: float = 1.0,
        retry: RetryPolicy = NO_RETRY,
        model_retry: RetryPolicy | None = None,
        model_timeout_s: float = 60.0,
        cancel_grace: float = DEFAULT_CANCEL_GRACE_S,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.journal = journal
        self.resolve = resolve
        self.provider = provider
        self.tools = tools
        self.clock = clock
        self.worker_id = worker_id or default_worker_id()
        self.lease_ttl = lease_ttl
        self.shutdown_grace = shutdown_grace
        self.poll = poll
        self.retry = retry
        self.model_retry = model_retry
        self.model_timeout_s = model_timeout_s
        self.cancel_grace = cancel_grace
        #: One per process, per provider, shared by every lease this worker holds (§8): an outage
        #: seen by one run holds back the next attempt of every run on the same provider.
        self.breaker = breaker if breaker is not None else CircuitBreaker()
        self.draining = False
        # `lease_ttl` must exceed the largest registered non-PURE tool.timeout, or the pre-dispatch
        # gate could never clear and every attempt would abandon with STARTED open (§8.4).
        if tools is not None:
            tools.check_lease_ttl(lease_ttl)

    # --- loops ---------------------------------------------------------------
    async def run_forever(self) -> None:
        self._install_drain_handler()
        while not self.draining:
            did = await self._claim_once()
            if not did:
                await asyncio.sleep(self.poll)

    async def run_until_idle(self, *, run_id: RunId | None = None, timeout: float | None = 30.0) -> None:
        """The in-process worker behind `Keel.run` and `keel run --inline`."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if not await self._claim_once():
                return
            if run_id is not None:
                row = await self.journal.run_row(run_id)
                if row is not None and row.terminal_at is not None:
                    return
                if row is not None and row.phase == "SUSPENDED":
                    return
            if deadline is not None and time.monotonic() > deadline:
                return

    async def _claim_once(self) -> bool:
        lease = await self.journal.claim(self.worker_id, timedelta(seconds=self.lease_ttl))
        if lease is None:
            return False
        await self.execute(lease)
        return True

    # --- one lease -----------------------------------------------------------
    async def execute(self, lease: Lease) -> None:
        journal = self.journal
        row = await journal.run_row(lease.run_id)
        cause = lease.cause
        if cause != "ORPHANED" and row is not None and row.phase in ("PAUSED", "SUSPENDED"):
            # §7.2.1: the cause is fixed at the first append, and it decides whether a suspension
            # lifts — so peek the inbox before writing it. A pending `resume` makes this a RESUME;
            # anything else woke a run that stays paused or suspended.
            pending = await journal.pending_signals(lease.run_id)
            cause = "RESUME" if any(s.type == "resume" for s in pending) else "WAKE"
        try:
            async with journal.append(lease) as tx:
                started_seq = await tx.append(
                    RecoveryStarted(
                        lease_epoch=lease.epoch,
                        cause=cause,
                        from_seq=lease.next_seq - 1,
                        from_segment=0,
                    )
                )
        except (Fenced, StoreUnavailable) as exc:
            # A takeover can move the epoch between the claim and this first append (§7.6.2). That
            # is a race this run lost, not a reason for the worker to stop serving every other run.
            outcome = "FENCED" if isinstance(exc, Fenced) else "CRASHED"
            await journal.set_recovery(lease.run_id, lease.epoch, outcome=outcome)
            return
        await journal.set_recovery(lease.run_id, lease.epoch, started_seq=started_seq, cause=cause)

        events = await journal.read(lease.run_id)
        state = fold(events)
        if state.terminal:
            await self._release(lease, phase=state.phase)
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="TERMINAL")
            return

        program = self.resolve(state.program or row.program)
        detail = state.suspended_detail if isinstance(state.suspended_detail, dict) else {}
        suspended_at = int(detail.get("step_index", state.next_step_index))
        engine = StepEngine(
            journal,
            lease,
            state,
            run_root_id=row.run_root_id,
            provider=self.provider,
            tools=self.tools,
            clock=self.clock,
            should_drain=lambda: self.draining,
            retry=self.retry,
            model_retry=self.model_retry,
            model_timeout_s=self.model_timeout_s,
            parent_run_id=row.parent_run_id,
            depth=await _depth(journal, row),
            model_config=row.model_config,
            resolve_program=self.resolve,
            cancel_grace_s=self.cancel_grace,
            breaker=self.breaker,
        )
        ctx = Ctx(
            engine,
            run_id=lease.run_id,
            run_root_id=row.run_root_id,
            args=state.args,
            program_version=lease.program_version,
            tools=self.tools,
        )
        if state.phase == "SUSPENDED":
            # Woken without a `resume`: drain, act on `cancel`, and park again — never re-execute,
            # which would only suspend again and leave the waking row unconsumed (§7.2.1).
            async def program(ctx: Any, args: Any, _at: int = suspended_at) -> Any:
                await engine.hold_suspended(_at)
        elif cause == "RESUME" and row is not None and row.phase == "SUSPENDED":
            # Lifted: consume the inbox before replaying, or a run that suspends again on the same
            # step would be claimed for ever by the `resume` that lifted it.
            async def program(ctx: Any, args: Any, _real: Any = program, _at: int = suspended_at) -> Any:
                await engine.drain_before_resuming(_at)
                return await _real(ctx, args)

        heart = asyncio.create_task(self._heartbeat(lease))
        t0 = time.monotonic()
        try:
            await self._run_program(program, ctx, engine, lease, state)
        finally:
            heart.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heart
        await journal.set_recovery(
            lease.run_id, lease.epoch, replay_ms=int((time.monotonic() - t0) * 1000)
        )

    async def _run_program(self, program: Any, ctx: Ctx, engine: StepEngine, lease: Lease, state: Any) -> None:
        journal = self.journal
        try:
            result = await program(ctx, ctx.args)
        except Suspended as exc:
            await self._finish(engine, lease, RunSuspended(reason=exc.reason, detail=exc.detail), "SUSPENDED")
            return
        except NondeterminismDetected as exc:
            await self._finish(
                engine,
                lease,
                RunSuspended(
                    reason="nondeterminism",
                    detail={"step_index": exc.step_index, "journaled": list(exc.journaled), "issued": list(exc.issued)},
                ),
                "SUSPENDED",
            )
            return
        except StepFailed as exc:
            await self._finish(engine, lease, RunFailed(error=exc.error, step_index=exc.step_index), "FAILED")
            return
        except Cancelled as exc:
            # CANCEL_ACKNOWLEDGED is already durable — the drain committed it before raising, so a
            # crash between the two leaves a run that a successor will acknowledge at the same
            # index rather than one that forgot it was asked to stop.
            await self._finish(engine, lease, RunCancelled(reason=str(exc)), "CANCELLED")
            return
        except Parked as parked:
            # RUN_WAITING and the release committed together (§5.4 (4)): no lease, no
            # `runnable_at`, only `wake_at`. That pair is the zero-compute wait — nothing holds the
            # run and nothing polls it, so a week of waiting costs one row and one timer sweep.
            outcome = "SUSPENDED" if parked.reason == "suspended" else "WAITING"
            await journal.set_recovery(lease.run_id, lease.epoch, outcome=outcome)
            return
        except Paused:
            # RUN_PAUSED, `paused_at` and the release committed together (§16.6): zero compute and
            # zero ticks until a `resume` or `cancel` makes the claim consider it again.
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="SUSPENDED")
            return
        except Drain:
            # SIGTERM: hand the run back rather than hold it until the lease lapses. Nothing is
            # appended — `runnable_at = now()` and a NULL lease are the entire handover, and the
            # successor's RECOVERY_STARTED{cause=DRAIN} records that it happened (§5).
            now = self.clock.now() if self.clock is not None else datetime.now(UTC)
            await self._release(lease, runnable_at=now, runnable_reason="DRAIN")
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="RELEASED")
            return
        except (Abandon, StoreUnavailable):
            # Append nothing, release nothing: the lease lapses and the successor disposes the open
            # step from journal state alone (§8.2). This is the one path that leaves a run held.
            #
            # `StoreUnavailable` shares it deliberately. The `except Exception` below is right
            # about a *program* bug — that is a run failure and belongs in the journal — and wrong
            # about an outage arriving through the same door: recording RUN_FAILED because the
            # store blinked turns a transient problem into permanent loss, and orphans any effect
            # that already landed. A worker that cannot write must not write a verdict.
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="CRASHED")
            return
        except Fenced:
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="FENCED")
            return
        except Exception as exc:  # noqa: BLE001 - a program bug is a run failure, not a worker crash
            await self._finish(
                engine, lease, RunFailed(error=f"{type(exc).__name__}: {exc}"), "FAILED"
            )
            return
        await self._finish(engine, lease, RunCompleted(result=result), "COMPLETED")

    async def _finish(self, engine: StepEngine, lease: Lease, body: Any, phase: str) -> None:
        journal = self.journal
        try:
            if not engine.recovery_completed:
                # A run that reached its terminal event with every step memoized still owes a
                # RECOVERY_COMPLETED: replayed_steps is what L1 and the latency join read (§5.7).
                live_from = engine.state.next_step_index
                async with journal.append(lease) as tx:
                    await tx.append(
                        RecoveryCompleted(
                            live_from_step=live_from, replayed_steps=live_from, elapsed_ms=0
                        )
                    )
                engine.recovery_completed = True
            async with journal.append(lease) as tx:
                await tx.append(body)
                await tx.set_run(phase=phase)
                if engine.parent_run_id is not None and phase in ("COMPLETED", "FAILED", "CANCELLED"):
                    # The outbox in the other direction (§5.10): a child's terminal event and its
                    # parent's `child_result` row commit together, so a child cannot become
                    # terminal and die before notifying — the L1 hole a same-database design
                    # closes for free, and the reason delegation needs no supervisor.
                    await tx.insert_signal(
                        child_result_signal(
                            engine.parent_run_id,
                            lease.run_id,
                            status=phase.lower(),
                            result=getattr(body, "result", None),
                            error=getattr(body, "error", None) or getattr(body, "reason", None),
                            usage=usage_of(engine.state),
                        )
                    )
        except (Fenced, Abandon):
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="FENCED")
            return
        except StoreUnavailable:
            # The same rule as `_run_program`'s: a worker that cannot write must not write a
            # verdict, and must not die for it either — the lease lapses and a successor finishes.
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="CRASHED")
            return
        await self._release(lease, phase=phase)
        await journal.set_recovery(
            lease.run_id, lease.epoch, outcome="SUSPENDED" if phase == "SUSPENDED" else "TERMINAL"
        )

    async def _release(self, lease: Lease, **fields: Any) -> None:
        """Every voluntary release, so `before:lease_release` is one boundary rather than four.

        A crash here leaves a lease nobody holds and nobody has released — indistinguishable from a
        crash to every observer, which is the point: a graceful shutdown that dies mid-release must
        degrade to the ordinary orphan path rather than to a stuck run.
        """
        hooks.at("before:lease_release", run_id=str(lease.run_id), epoch=lease.epoch)
        await self.journal.release(lease, **fields)

    async def _heartbeat(self, lease: Lease) -> None:
        """The fence statement alone, on a timer. A fenced heartbeat means someone else owns the
        run: stop, and let the successor decide from the journal."""
        period = max(0.05, self.lease_ttl / HEARTBEAT_DIVISOR)
        while True:
            await _waits(self.clock).sleep(period)
            # A kill here is how a *live* worker becomes a zombie: the lease is still valid for up
            # to one TTL, and the run is not reclaimable until it lapses. The reaper predicate is
            # what bounds that window, and this is where a fault gets to test the bound.
            hooks.at("before:lease_heartbeat", run_id=str(lease.run_id), epoch=lease.epoch)
            if not await self.journal.heartbeat(lease, timedelta(seconds=self.lease_ttl)):
                return

    # --- drain (SIGTERM) -----------------------------------------------------
    def _install_drain_handler(self) -> None:
        def _drain(*_: Any) -> None:
            self.draining = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(ValueError, OSError, AttributeError):
                signal.signal(sig, _drain)
