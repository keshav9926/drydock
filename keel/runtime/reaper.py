"""The reaper: one predicate, evaluated server-side (§8.4).

A run with an open non-PURE attempt is ORPHANED only when `now() > max(lease_expires_at,
attempt_deadline)`. The successor cannot start before the deadline that bounded the zombie's
request. There is no successor-side wait and no second predicate.

The reaper is never a writer of the journal: `ORPHANED` is the assertion that *no one* holds the
lease, and a reaper that appended an event would be a second writer racing the zombie it just
declared dead (§6.6).
"""

from __future__ import annotations

import asyncio

from keel.core.ids import RunId
from keel.journal.protocol import JournalBackend

DEFAULT_PERIOD = 1.0


class Reaper:
    def __init__(self, journal: JournalBackend, *, period: float = DEFAULT_PERIOD) -> None:
        self.journal = journal
        self.period = period
        self._stop = False

    async def sweep(self) -> list[RunId]:
        return await self.journal.reap()

    async def run_forever(self) -> None:
        while not self._stop:
            await self.sweep()
            await asyncio.sleep(self.period)

    def stop(self) -> None:
        self._stop = True
