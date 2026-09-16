"""Clock protocol. ctx.now() reads through it; hook-mode tests inject FakeClock (§23.1).

Journaled timestamps are always Postgres `now()`, never a worker clock (§5.3). This clock is for
the worker's own local reasoning: heartbeat timers, the pre-dispatch margin, test time travel.

`sleep` and `timeout` are the seam §12.2 names: the attempt timeout, the heartbeat period and an
in-process retry backoff all wait through the clock, so a simulated clock can make every timing
decision an explicit rule instead of a race with the wall clock. Nothing is monkeypatched to get
there — the runtime asks its clock, and the real clocks answer with `asyncio`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> Awaitable[Any]: ...
    def timeout(self, seconds: float) -> AbstractAsyncContextManager[Any]: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> Awaitable[Any]:
        return asyncio.sleep(seconds)

    def timeout(self, seconds: float) -> AbstractAsyncContextManager[Any]:
        return asyncio.timeout(seconds)


class FakeClock:
    """Deterministic clock for property and conformance tests.

    `now()` moves only through `advance`. Waits stay on the event loop's real clock: the hook-mode
    cells hold a real World response and need a real timeout to end it. The property sim's clock
    (`tests/property/sim.py`) is the one that drives waits by `advance` too.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)
        self._mono = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._mono += seconds

    def sleep(self, seconds: float) -> Awaitable[Any]:
        return asyncio.sleep(seconds)

    def timeout(self, seconds: float) -> AbstractAsyncContextManager[Any]:
        return asyncio.timeout(seconds)
