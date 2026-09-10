"""Event-loop selection for the harness process.

psycopg's async mode cannot run on Windows' default ProactorEventLoop, and the harness opens
connections — the Keel adapter clones a database per trial and reads the journal back at
collection. Keel has the same constraint for the same reason in `keel/core/aio.py`, and neither
imports the other: the harness must be installable and runnable against a runtime that is not
Keel, which is the whole point of the two-module rule the layering test enforces.
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


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    if WINDOWS:
        return asyncio.run(coro, loop_factory=loop_factory)
    return asyncio.run(coro)
