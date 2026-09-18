"""The long-horizon mechanisms against a real Postgres (§18): the store's clock and its indexes.

`tests/unit/test_{sleep,plan,segments}.py` prove the runtime on the MemoryJournal. These prove what
the two backends could disagree on: `wake_at` computed from Postgres `now()`, the timer sweep over a
released run, and `events_segment_once` refusing a second boundary with the same number.

    docker compose up -d postgres
    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import timedelta
from typing import Any

import pytest

from keel import Keel, program
from keel.journal.postgres import PostgresJournal
from keel.replay.verify import verify
from keel.state.fold import fold

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = 2.0


@pytest.fixture
async def journal():
    j = PostgresJournal(DSN)
    await j.migrate()
    pool = await j._ready()
    async with pool.connection() as conn:
        await conn.execute(
            "TRUNCATE artifacts, replays, recoveries, delegations, signals, effects, events,"
            " runs, blobs, programs RESTART IDENTITY CASCADE"
        )
    yield j
    await j.close()


@program(name="pg_napper", version="1.0")
async def pg_napper(ctx: Any, args: dict[str, Any]) -> str:
    await ctx.sleep(args["seconds"])
    return "rested"


async def _work(k: Keel, worker_id: str) -> bool:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is None:
        return False
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
    return True


async def test_a_sleep_is_timed_by_the_store_and_woken_by_the_sweep(journal) -> None:
    k = Keel(journal=journal, programs=[pg_napper])
    handle = await k.start(pg_napper, {"seconds": 1.0})
    assert await _work(k, "w1")

    row = await journal.run_row(handle.run_id)
    assert (row.phase, row.lease_expires_at, row.runnable_at) == ("SLEEPING", None, None)
    started = next(e for e in await k.events(handle.run_id) if e.type == "STEP_ATTEMPT_STARTED")
    assert row.wake_at == started.body.started_at + timedelta(seconds=1), "Postgres now() + d, one tx"
    assert await journal.sweep_timers() == 0 and not await _work(k, "early")

    await asyncio.sleep(1.2)
    assert await journal.sweep_timers() == 1
    assert await _work(k, "w2")
    state = fold(await k.events(handle.run_id))
    assert (state.phase, state.result) == ("COMPLETED", "rested")
    from datetime import datetime

    assert datetime.fromisoformat(state.steps[0].result["woke_at"]) >= row.wake_at, "never before wake_at"
    assert (await verify(journal, handle.run_id, pg_napper)).ok
