from __future__ import annotations

import pytest

from keel.core import aio


@pytest.fixture(scope="session")
def event_loop_policy():
    """psycopg cannot use Windows' ProactorEventLoop (keel/core/aio.py)."""
    aio.install_policy()
    import asyncio

    return asyncio.get_event_loop_policy()
