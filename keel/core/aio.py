"""Event-loop selection.

psycopg's async mode cannot run on Windows' default ProactorEventLoop. Keel is a Postgres runtime,
so every entry point that opens a connection selects a compatible loop here rather than leaving a
platform trap in each caller.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any

WINDOWS = sys.platform == "win32"


def loop_factory():
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def install_policy() -> None:
    """For frameworks that own the loop (pytest-asyncio) and cannot take a factory."""
    if WINDOWS:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    if WINDOWS:
        return asyncio.run(coro, loop_factory=loop_factory)
    return asyncio.run(coro)
