"""Human resolution against a real Postgres (§6.2, §7.2.1, §7.4).

`tests/unit/test_resolve.py` proves the runtime on the MemoryJournal. These prove the three things
the backends could disagree on: `events_resolved_once` admits the human's STEP_RESOLVED beside the
escalate one, and a second probe row for the next attempt (it keys on `attempt_no, method`), the
claim picks up a SUSPENDED run on the `custom` row alone, and the `effects` row moves to
RESOLVED_COMMITTED / RESOLVED_ABSENT in the drain's transaction.

    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import contextlib
import os
from datetime import timedelta
from typing import Any

import pytest

from keel import Keel
from keel.journal.postgres import PostgresJournal
from keel.replay.verify import verify
from keel.state.fold import fold
from tests.unit.test_resolve import CALLS, careful_mailer, mailer, page_oncall, put_doc, send_mail

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
    CALLS.clear()
    yield j
    await j.close()


async def _work(k: Keel, worker_id: str) -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None, "the run was not claimable"
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


@pytest.mark.parametrize(("prog", "tool_name", "outcome", "status", "phase"), [
    (mailer, "send_mail", "completed", "RESOLVED_COMMITTED", "COMPLETED"),
    (mailer, "put_doc", "completed", "RESOLVED_COMMITTED", "COMPLETED"),
    (careful_mailer, "send_mail", "failed", "RESOLVED_ABSENT", "COMPLETED"),
])
async def test_a_resolve_row_alone_lifts_the_suspension(
    journal: PostgresJournal, prog: Any, tool_name: str, outcome: str, status: str, phase: str
) -> None:
    k = Keel(journal=journal, tools=[send_mail, put_doc], programs=[mailer, careful_mailer])
    handle = await k.start(prog, {"tool": tool_name})
    await _work(k, "w1")
    assert fold(await k.events(handle.run_id)).phase == "SUSPENDED"

    assert await k.resolve_step(handle.run_id, 0, outcome, evidence="checked by hand", result={"id": 1})
    await _work(k, "w2")

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == phase
    assert [e.body.cause for e in events if e.type == "RECOVERY_STARTED"][-1] == "RESUME"
    methods = [e.body.method for e in events if e.type == "STEP_RESOLVED"]
    assert methods[-1] == "human" and len(methods) == 2, "escalate once, a human once — one index admits both"
    [row] = await journal.effects(handle.run_id)
    assert (row.status, row.resolution) == (status, "human")
    assert CALLS == [tool_name]
    assert (await verify(journal, handle.run_id, prog, tools=k.tools)).ok


async def test_cancelled_closes_the_step_and_leaves_the_effect_unknown(journal: PostgresJournal) -> None:
    k = Keel(journal=journal, tools=[send_mail, put_doc], programs=[mailer, careful_mailer])
    handle = await k.start(mailer, {"tool": "send_mail"})
    await _work(k, "w1")
    assert await k.resolve_step(handle.run_id, 0, "cancelled")
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "CANCELLED" and state.steps[0].state == "CANCELLED"
    [row] = await journal.effects(handle.run_id)
    assert row.status == "RESOLVED_UNKNOWN"
    assert (await journal.run_row(handle.run_id)).terminal_at is not None


async def test_a_reattempt_that_goes_ambiguous_is_probed_in_its_turn(journal: PostgresJournal) -> None:
    """Two probe rows for one step, attempts 1 and 2. Before 0005 the index keyed on the step, the
    second row was a UniqueViolation, and the run FAILED (the v1 confirmation tier found it)."""
    k = Keel(journal=journal, tools=[page_oncall], programs=[mailer])
    handle = await k.start(mailer, {"tool": "page_oncall"})
    await _work(k, "w1")

    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED", [e.type for e in events]
    resolved = [(e.body.attempt_no, e.body.resolution, e.body.method) for e in events if e.type == "STEP_RESOLVED"]
    assert resolved == [(1, "RESOLVED_FAILED", "probe"), (2, "RESOLVED_COMPLETED", "probe")]
    assert CALLS == ["page_oncall", "page_oncall"]
    assert (await verify(journal, handle.run_id, mailer, tools=k.tools)).ok


async def test_a_database_migrated_before_0005_gets_the_per_attempt_index(journal: PostgresJournal) -> None:
    pool = await journal._ready()
    async with pool.connection() as conn:
        await conn.execute("DROP INDEX events_resolved_once")
        await conn.execute(
            "CREATE UNIQUE INDEX events_resolved_once ON events (run_id, step_index, (payload->>'method'))"
            " WHERE type = 'STEP_RESOLVED'"
        )
    await journal.migrate()
    await journal.migrate()  # and again: every migration is re-run on every start
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'events_resolved_once'")
        [(indexdef,)] = await cur.fetchall()
    assert "attempt_no" in indexdef
