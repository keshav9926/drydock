"""STREAMS against a real Postgres (§9.3, §10.7): STEP_CHUNK rows under the fence, and a crash mid-stream.

`tests/unit/test_streams.py` proves the modifier on the MemoryJournal. This proves what the backends
could disagree on: a chunk is its own fenced transaction beside the step's partial unique indexes, a
successor's re-attempt of the same step keeps the dead attempt's chunks, and the budget folds them.

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
from keel.providers.scripted import Decision, ScriptedProvider
from keel.replay.verify import verify
from keel.runtime import hooks
from keel.state.fold import fold

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = 2.0
ANSWER = " ".join(f"word{i:04d}" for i in range(360))  # ~900 tokens: four STEP_CHUNK batches


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


@program(name="pg_streamer", version="1.0")
async def pg_streamer(ctx: Any, args: dict[str, Any]) -> str:
    return (await ctx.model([{"role": "user", "content": "explain"}], name="answer", max_tokens=2048,
                            stream=True)).text


async def test_a_crash_mid_stream_on_postgres_is_a_new_attempt_with_the_dead_chunks_kept(journal) -> None:
    k = Keel(journal=journal, provider=ScriptedProvider([Decision(text=ANSWER)]), programs=[pg_streamer])
    await k.upsert_programs()
    handle = await k.start(pg_streamer, {})

    def crash_at_second_batch(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "during:stream" and detail["chunk"] == 2 and detail["attempt_no"] == 1:
            raise hooks.Crash("power cut mid-stream")

    hooks.install(crash_at_second_batch)
    try:
        lease = await journal.claim("w1", timedelta(seconds=TTL))
        with contextlib.suppress(BaseException):
            await k.worker(worker_id="w1", lease_ttl=TTL).execute(lease)
    finally:
        hooks.reset()
    dead = [e for e in await k.events(handle.run_id) if e.type == "STEP_CHUNK"]
    assert [(e.body.attempt_no, e.body.chunk_no) for e in dead] == [(1, 1), (1, 2)], "durable before the cut"

    await asyncio.sleep(TTL + 0.5)
    await journal.reap()
    successor = await journal.acquire(handle.run_id, "w2", timedelta(seconds=TTL))
    assert successor is not None
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(successor)

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED" and state.result == ANSWER
    assert [e.body.error for e in events if e.type == "STEP_FAILED"] == ["attempt_abandoned"]
    assert {e.body.attempt_no for e in events if e.type == "STEP_CHUNK"} == {1, 2}
    reservation = next(e.body.reservation for e in events if e.type == "STEP_ATTEMPT_STARTED")
    usage = next(e.body.usage for e in events if e.type == "STEP_COMPLETED")
    assert state.charged.tokens_charged == reservation + sum(usage.values()), "the dead attempt stays charged"
    assert (await verify(journal, handle.run_id, pg_streamer)).ok
