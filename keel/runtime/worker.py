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
from datetime import timedelta
from collections.abc import Callable
from typing import Any

from keel.core.errors import Fenced, NondeterminismDetected, StepFailed
from keel.core.ids import RunId
from keel.events import (
    RecoveryCompleted,
    RecoveryStarted,
    RunCompleted,
    RunFailed,
    RunSuspended,
)
from keel.journal.protocol import JournalBackend, Lease
from keel.runtime.ctx import Ctx
from keel.runtime.steps import Abandon, StepEngine, Suspended
from keel.state.fold import fold

DEFAULT_LEASE_TTL = 30.0
HEARTBEAT_DIVISOR = 3  # heartbeat period <= ttl/3 (§8.7)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


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
        started_seq = None
        async with journal.append(lease) as tx:
            started_seq = await tx.append(
                RecoveryStarted(
                    lease_epoch=lease.epoch,
                    cause=lease.cause,
                    from_seq=lease.next_seq - 1,
                    from_segment=0,
                )
            )
        await journal.set_recovery(lease.run_id, lease.epoch, started_seq=started_seq)

        events = await journal.read(lease.run_id)
        state = fold(events)
        if state.terminal:
            await journal.release(lease, phase=state.phase)
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="TERMINAL")
            return

        row = await journal.run_row(lease.run_id)
        program = self.resolve(state.program or row.program)
        engine = StepEngine(
            journal,
            lease,
            state,
            run_root_id=row.run_root_id,
            provider=self.provider,
            tools=self.tools,
            clock=self.clock,
        )
        ctx = Ctx(
            engine,
            run_id=lease.run_id,
            run_root_id=row.run_root_id,
            args=state.args,
            program_version=lease.program_version,
            tools=self.tools,
        )
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
        except Abandon:
            # Append nothing, release nothing: the lease lapses and the successor disposes the open
            # step from journal state alone (§8.2). This is the one path that leaves a run held.
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
        except (Fenced, Abandon):
            await journal.set_recovery(lease.run_id, lease.epoch, outcome="FENCED")
            return
        await journal.release(lease, phase=phase)
        await journal.set_recovery(
            lease.run_id, lease.epoch, outcome="SUSPENDED" if phase == "SUSPENDED" else "TERMINAL"
        )

    async def _heartbeat(self, lease: Lease) -> None:
        """The fence statement alone, on a timer. A fenced heartbeat means someone else owns the
        run: stop, and let the successor decide from the journal."""
        period = max(0.05, self.lease_ttl / HEARTBEAT_DIVISOR)
        while True:
            await asyncio.sleep(period)
            if not await self.journal.heartbeat(lease, timedelta(seconds=self.lease_ttl)):
                return

    # --- drain (SIGTERM) -----------------------------------------------------
    def _install_drain_handler(self) -> None:
        def _drain(*_: Any) -> None:
            self.draining = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(ValueError, OSError, AttributeError):
                signal.signal(sig, _drain)
