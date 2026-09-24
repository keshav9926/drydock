"""What was built after the v1 tag, against a real Postgres — where the MemoryJournal could disagree.

- A deadline's refusal is raised *inside* the STARTED transaction; on Postgres that must roll back
  the INTENT and the effects row with it, leaving only the refusal.
- A waiting run's `runs.wake_at` is capped at the deadline while RUN_WAITING keeps the step's own.
- `max_usd`: the rate a MODEL attempt journals survives a round trip through jsonb and folds back.
- §6.5: a STEP_COMPLETED stored at v2 reads back at v2, one stored at v1 is upcast at load, and a run
  holding a row newer than the worker is handed back with a backoff measured by the *store's* clock
  (`release` caps a timestamp at `now()`, so the delay has to be an interval — the bug this pins).

    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import contextlib
import os
from datetime import timedelta
from typing import Any

import pytest

from keel import Budget, Keel, program
from keel.journal.postgres import PostgresJournal
from keel.providers.scripted import Decision, ScriptedProvider
from keel.runtime.worker import SCHEMA_BACKOFF_S
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


@program(name="pg_asker", version="1.0")
async def asker(ctx: Any, args: dict[str, Any]) -> str:
    return (await ctx.model([{"role": "user", "content": "q"}], name="ask")).text


@program(name="pg_napper", version="1.0")
async def napper(ctx: Any, args: dict[str, Any]) -> None:
    await ctx.sleep(100)


def _keel(journal: PostgresJournal) -> Keel:
    return Keel(journal=journal, provider=ScriptedProvider([Decision(text="a")] * 3), programs=[asker, napper])


async def _work(k: Keel, worker_id: str = "w") -> Any:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is not None:
        with contextlib.suppress(BaseException):
            await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
    return lease


async def _sql(journal: PostgresJournal, query: str, *args: Any) -> list[tuple]:
    pool = await journal._ready()
    async with pool.connection() as conn:
        cur = await conn.execute(query, args)
        return await cur.fetchall() if cur.description else []


async def test_a_refusal_past_the_deadline_rolls_the_attempt_back(journal: PostgresJournal) -> None:
    k = _keel(journal)
    handle = await k.start(asker, {}, budget=Budget(deadline_at="2000-01-01T00:00:00Z"))
    await _work(k)
    events = await k.events(handle.run_id)
    state = fold(events)
    assert (state.phase, state.error) == ("FAILED", "DeadlineExceeded")
    assert [e.type for e in events if e.type.startswith("STEP_")] == ["STEP_INTENDED", "STEP_FAILED"]
    assert not await journal.effects(handle.run_id)


async def test_a_parked_run_wakes_at_its_deadline(journal: PostgresJournal) -> None:
    k = _keel(journal)
    handle = await k.start(napper, {}, budget=Budget(max_wall_clock=timedelta(seconds=30)))
    await _work(k)
    events = await k.events(handle.run_id)
    created, waiting = events[0], [e for e in events if e.type == "RUN_WAITING"][-1]
    row = await journal.run_row(handle.run_id)
    assert row.wake_at == created.ts + timedelta(seconds=30), "the runs row: least(wake_at, deadline_at)"
    assert waiting.body.wake_at > row.wake_at + timedelta(seconds=60), "RUN_WAITING keeps the sleep's own"


async def test_the_journaled_rate_and_the_v2_usage_survive_the_store(journal: PostgresJournal) -> None:
    k = _keel(journal)
    result = await k.run(asker, {}, budget=Budget(max_usd=1.0))
    assert result.phase == "COMPLETED"
    events = await k.events(result.run_id)
    [started] = [e for e in events if e.type == "STEP_ATTEMPT_STARTED"]
    [completed] = [e for e in events if e.type == "STEP_COMPLETED"]
    assert started.body.price is not None and started.body.reservation_usd > 0
    assert completed.env.schema_version == 2 and "cache_read_tokens" in completed.body.usage
    assert 0 < fold(events).charged.usd_charged <= started.body.reservation_usd

    # A row written by a v1 worker: no cache_read_tokens, schema_version 1. Read back upcast, not rewritten.
    await _sql(journal, "UPDATE events SET schema_version = 1, payload = jsonb_set(payload, '{usage}',"
                        " (payload->'usage') - 'cache_read_tokens') WHERE run_id = %s AND seq = %s",
               result.run_id, completed.seq)
    [again] = [e for e in await k.events(result.run_id) if e.type == "STEP_COMPLETED"]
    assert again.env.schema_version == 1 and again.body.usage["cache_read_tokens"] == 0
    assert fold(await k.events(result.run_id)).charged.usd_charged == fold(events).charged.usd_charged


async def test_a_row_newer_than_the_worker_is_handed_back_with_a_store_clock_backoff(journal: PostgresJournal) -> None:
    k = _keel(journal)
    handle = await k.start(asker, {})
    await _sql(journal, "UPDATE events SET schema_version = 99 WHERE run_id = %s AND seq = 1", handle.run_id)
    lease = await _work(k, "old")
    assert lease is not None and lease.run_id == handle.run_id
    [(runnable_in, held)] = await _sql(
        journal, "SELECT extract(epoch FROM runnable_at - now()), lease_expires_at IS NOT NULL FROM runs WHERE run_id = %s",
        handle.run_id)
    assert not held and SCHEMA_BACKOFF_S - 5 < float(runnable_in) <= SCHEMA_BACKOFF_S
    [(outcome, started_seq)] = await _sql(
        journal, "SELECT outcome, started_seq FROM recoveries WHERE run_id = %s", handle.run_id)
    assert (outcome, started_seq) == ("RELEASED", None), "nothing journaled by a worker that could not read"
    assert await journal.claim("old", timedelta(seconds=TTL)) is None, "the backoff holds on the real store"
