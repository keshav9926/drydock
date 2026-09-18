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

import psycopg
import pytest
from pydantic import BaseModel

from keel import Continue, Keel, program
from keel.journal.postgres import PostgresJournal
from keel.replay.verify import verify
from keel.runtime import hooks
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


class Tally(BaseModel):
    i: int = 0


@program(name="pg_tally", version="1.0", state=Tally)
async def pg_tally(ctx: Any, args: dict[str, Any], state: Tally | None = None) -> Any:
    state = state or Tally()
    if state.i == 0:
        await ctx.plan.init(["tally"])
    while state.i < 4:
        await ctx.random()
        state.i += 1
        if state.i == 2:
            return Continue(state)
    await ctx.plan.complete(ctx.plan.items[0]["id"])
    return state.i


async def test_a_boundary_round_trips_postgres_and_a_second_one_is_refused(journal) -> None:
    """SEGMENT_STARTED's payload (the blob, `compact_seq`) and the snapshot PLAN_UPDATED with no step
    index round-trip the events table; recovery reads from the latest boundary and names it in
    RECOVERY_STARTED; `events_segment_once` refuses a second boundary with the same number."""
    from keel.core.errors import KeelError
    from keel.events import SegmentStarted

    k = Keel(journal=journal, programs=[pg_tally])
    handle = await k.start(pg_tally)

    def die(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:intent_commit" and detail.get("step_index") == 4:
            raise hooks.Crash("killed in segment 1")

    hooks.install(die)
    try:
        assert await _work(k, "w1")
    finally:
        hooks.reset()
    pool = await journal._ready()
    async with pool.connection() as conn:
        await conn.execute("UPDATE runs SET lease_expires_at = now() - interval '1 second' WHERE run_id = %s",
                           (handle.run_id,))
    await journal.reap()
    assert await _work(k, "w2")

    events = await k.events(handle.run_id)
    state = fold(events)
    assert (state.phase, state.result) == ("COMPLETED", 4)
    [seg] = [e for e in events if e.type == "SEGMENT_STARTED"]
    assert (seg.body.segment_no, seg.body.first_step_index, seg.body.state_blob) == (1, 3, {"i": 2})
    snapshot = next(e for e in events if e.seq == seg.seq + 1)
    assert (snapshot.type, snapshot.step_index) == ("PLAN_UPDATED", None)
    assert [e.body.from_segment for e in events if e.type == "RECOVERY_STARTED"] == [0, 1]
    assert (await verify(journal, handle.run_id, pg_tally)).ok

    lease = await journal.acquire(handle.run_id, "w9", timedelta(seconds=TTL))
    with pytest.raises((KeelError, psycopg.errors.UniqueViolation)):
        async with journal.append(lease) as tx:
            await tx.append(SegmentStarted(segment_no=1, first_step_index=99, program_version="x"))
