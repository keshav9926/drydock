"""The reaper: one predicate, evaluated server-side (§8.4), plus the two sweeps a parked run and a
stray child need because nothing else is looking at them.

A run with an open non-PURE attempt is ORPHANED only when `now() > max(lease_expires_at,
attempt_deadline)`. The successor cannot start before the deadline that bounded the zombie's
request. There is no successor-side wait and no second predicate.

As a reaper it is never a writer of the journal: `ORPHANED` is the assertion that *no one* holds
the lease, and a reaper that appended an event would be a second writer racing the zombie it just
declared dead (§6.6). The liveness sweep (§17.7) is the one place it writes, and it writes as a
*holder*: a stray child is cancelled through its inbox and, after `cancel_grace`, its lease is
taken over — an acquisition like any other, with the fence doing what it always does.
"""

from __future__ import annotations

import asyncio
import logging

from keel.core.ids import RunId
from keel.journal.protocol import JournalBackend
from keel.runtime.delegation import cancel_signal
from keel.runtime.takeover import DEFAULT_CANCEL_GRACE_S, force_cancel

DEFAULT_PERIOD = 1.0
log = logging.getLogger("keel.reaper")


class Reaper:
    def __init__(
        self,
        journal: JournalBackend,
        *,
        period: float = DEFAULT_PERIOD,
        worker_id: str = "reaper",
        lease_ttl: float = 30.0,
        cancel_grace: float = DEFAULT_CANCEL_GRACE_S,
    ) -> None:
        self.journal = journal
        self.period = period
        self.worker_id = worker_id
        self.lease_ttl = lease_ttl
        self.cancel_grace = cancel_grace
        self._stop = False

    async def sweep(self) -> list[RunId]:
        return await self.journal.reap()

    async def timers(self) -> int:
        """The other half of the zero-tick park: a run with `runnable_at IS NULL` is polled by
        nothing, so something has to notice that its `wake_at` has passed. Idempotent by
        `client_key`, so every worker can run it and two firing at once produce one row (§5.6)."""
        return await self.journal.sweep_timers()

    async def strays(self) -> int:
        """§17.7's liveness rule: a child cannot outlive its parent's terminal state. Each stray
        is told first — one `cancel` row, keyed so every tick and every reaper produce the same
        row — and forced once the store's predicate says the grace has passed. S8 measures what a
        stray did in between. Returns how many were closed this tick."""
        closed = 0
        for child in await self.journal.stray_children():
            await self.journal.insert_signal(
                cancel_signal(
                    child.run_id,
                    client_key=f"cancel:reaper:{child.run_id}",
                    by="reaper",
                    reason="parent_terminal",
                )
            )
            outcome = await force_cancel(
                self.journal,
                child.run_id,
                worker_id=self.worker_id,
                ttl_s=self.lease_ttl,
                forced_by="reaper",
                cancel_grace_s=self.cancel_grace,
            )
            closed += outcome == "cancelled"
        return closed

    async def run_forever(self) -> None:
        """Each sweep isolated: one that raises — a lost race, a store blip — is logged and the
        loop goes on. A reaper task that died silently would stop orphaning lapsed leases, firing
        expiry timers and closing strays on this process for good, and nothing would say why."""
        while not self._stop:
            for sweep in (self.sweep, self.timers, self.strays):
                try:
                    await sweep()
                except Exception:  # noqa: BLE001 - the loop outlives any one tick
                    log.exception("reaper %s: %s failed; continuing", self.worker_id, sweep.__name__)
            await asyncio.sleep(self.period)

    def stop(self) -> None:
        self._stop = True
