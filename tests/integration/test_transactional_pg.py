"""TRANSACTIONAL against a real Postgres (§9.1) — where `tctx.db` is the journal's own connection.

The memory tests prove the engine's shape; these prove what only a server can: that the tool's
INSERT and STEP_COMPLETED are one commit, that a timeout cancels the query *on the server* and rolls
the write back, that an error is classified by whether the connection survived rather than by its
class, that a tool cannot hand back a broken transaction or leave anything on the connection for
anyone else, and that a holder frozen inside the transaction — between statements or in the middle
of one — does not keep the run's row locked: Postgres ends the transaction itself (`AppendTx.tool_db`'s
bound), and the successor writes once.

    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from keel import Keel, program
from keel.core.errors import StoreUnavailable
from keel.core.protocols import EffectClass
from keel.effects.registry import tool
from keel.journal.postgres import PostgresJournal
from keel.runtime import hooks
from keel.runtime.retry import RetryPolicy
from keel.runtime.steps import TOOL_TX_GRACE_S
from keel.state.fold import fold

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = 2.0
TIMEOUT = 1.0
RETRY = RetryPolicy(max_attempts=2, base_s=0.01)


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
        await conn.execute("DROP TABLE IF EXISTS txn_orders, txn_unique")
        await conn.execute("CREATE TABLE txn_orders (id text NOT NULL, attempt int NOT NULL)")
        await conn.execute("CREATE TABLE txn_unique (id text UNIQUE DEFERRABLE INITIALLY DEFERRED)")
    yield j
    async with pool.connection() as conn:
        await conn.execute("DROP TABLE IF EXISTS txn_orders, txn_unique")
    await j.close()


@pytest.fixture(autouse=True)
def _no_hook_leaks():
    hooks.reset()
    yield
    hooks.reset()


def orders_tool(plan: dict[int, Any] | None = None, *, timeout: float = TIMEOUT) -> tuple[Any, list[int]]:
    """`save_order`: one INSERT on `tctx.db`, then whatever `plan` says that attempt does — a callable
    run on the connection, or a blocking sleep that stops the whole process as SIGSTOP would."""
    plan = dict(plan or {})
    ran: list[int] = []

    @tool(effect=EffectClass.TRANSACTIONAL, timeout=timeout, name="save_order")
    async def save_order(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
        ran.append(tctx.attempt_no)
        await tctx.db.execute("INSERT INTO txn_orders (id, attempt) VALUES (%s, %s)", (args["id"], tctx.attempt_no))
        then = plan.get(tctx.attempt_no)
        if then is not None:
            await then(tctx)
        return {"id": args["id"], "external_ref": f"txn_orders/{args['id']}"}

    return save_order, ran


@program(name="pg_place_order", version="1.0")
async def place_order(ctx: Any, args: dict[str, Any]) -> Any:
    return await ctx.tool("save_order", id="o1")


async def _rows(journal: PostgresJournal) -> list[tuple]:
    """Read from a connection of its own: what is *committed*, never what a transaction staged."""
    pool = await journal._ready()
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT id, attempt FROM txn_orders ORDER BY attempt")
        return await cur.fetchall()


async def _work(k: Keel, worker_id: str, lease: Any, **kw: Any) -> None:
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL, **kw).execute(lease)


async def _take_over(k: Keel, run_id: Any) -> None:
    for _ in range(80):  # past max(lease_expires_at, attempt_deadline), on the store's clock
        if await k.journal.reap() == [run_id]:
            break
        await asyncio.sleep(0.1)
    successor = await k.journal.acquire(run_id, "w2", timedelta(seconds=TTL))
    assert successor is not None
    await _work(k, "w2", successor)


async def test_the_insert_and_its_outcome_are_one_commit(journal: PostgresJournal) -> None:
    save_order, ran = orders_tool()
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    result = await k.run(place_order, {})
    assert result.phase == "COMPLETED" and ran == [1]
    assert await _rows(journal) == [("o1", 1)]
    [effect] = await journal.effects(result.run_id)
    assert (effect.effect_class, effect.status, effect.external_ref) == ("TRANSACTIONAL", "COMMITTED", "txn_orders/o1")
    pool = await journal._ready()
    async with pool.connection() as conn:
        cur = await conn.execute("SHOW statement_timeout")
        assert (await cur.fetchone())[0] == "0", "the bound was SET LOCAL: it never reaches the pool"


async def test_a_crash_inside_the_transaction_leaves_no_row_and_the_successor_writes_once(
    journal: PostgresJournal,
) -> None:
    save_order, ran = orders_tool()
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})

    def crash(at: str, detail: dict[str, Any]) -> None:
        if at == "before:outcome_commit" and detail.get("name") == "save_order" and ran == [1]:
            raise hooks.Crash("power cut with the INSERT written and not committed")

    hooks.install(crash)
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)))
    hooks.reset()
    assert ran == [1] and await _rows(journal) == [], "the INSERT went with the transaction"
    assert fold(await k.events(handle.run_id)).steps[0].state == "RUNNING"

    await _take_over(k, handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert ran == [1, 2] and await _rows(journal) == [("o1", 2)]


async def test_a_timeout_cancels_the_query_on_the_server_and_rolls_the_insert_back(
    journal: PostgresJournal,
) -> None:
    async def stall(tctx: Any) -> None:
        await tctx.db.execute("SELECT pg_sleep(30)")

    save_order, ran = orders_tool({1: stall}, timeout=0.5)
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})
    started = time.monotonic()
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    assert time.monotonic() - started < 5, "ended at the timeout, not when pg_sleep(30) finished"

    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED" and ran == [1, 2]
    [failed] = [e for e in events if e.type == "STEP_FAILED"]
    assert (failed.attempt_no, failed.body.error, failed.body.retryable) == (1, "timeout", True)
    assert await _rows(journal) == [("o1", 2)]
    pool = await journal._ready()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND query LIKE 'SELECT pg_sleep(30)%%'"
        )
        assert (await cur.fetchone())[0] == 0, "the cancel reached the server; nothing is still sleeping"


async def test_a_serialization_failure_is_journaled_retryable_and_retried(journal: PostgresJournal) -> None:
    """psycopg raises SQLSTATE class 40 as an `OperationalError`, which the append would read as the store
    going away. On a live connection it is the tool's outcome — Postgres' own *retry this transaction*."""

    async def conflict(tctx: Any) -> None:
        await tctx.db.execute("DO $$ BEGIN RAISE EXCEPTION 'could not serialize' USING ERRCODE = '40001'; END $$")

    save_order, ran = orders_tool({1: conflict})
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED" and ran == [1, 2]
    [failed] = [e for e in events if e.type == "STEP_FAILED"]
    assert (failed.attempt_no, failed.body.retryable) == (1, True)
    assert failed.body.error.startswith("SerializationFailure")
    assert await _rows(journal) == [("o1", 2)]


async def test_an_ordinary_sql_error_fails_the_step_and_leaves_no_row(journal: PostgresJournal) -> None:
    async def divide(tctx: Any) -> None:
        await tctx.db.execute("SELECT 1 / 0")

    save_order, ran = orders_tool({1: divide})
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "FAILED" and ran == [1]
    [failed] = [e for e in events if e.type == "STEP_FAILED"]
    assert failed.body.error.startswith("DivisionByZero") and not failed.body.retryable
    assert await _rows(journal) == []
    [effect] = await journal.effects(handle.run_id)
    assert effect.status == "ABSENT"


async def test_a_connection_the_server_ends_mid_tool_is_an_outage_not_a_failure(journal: PostgresJournal) -> None:
    """The tool's connection is the journal's. If the server ends it, nothing was committed and nothing
    can be journaled on it: the holder abandons — no STEP_FAILED — and the successor writes once."""

    async def killed(tctx: Any) -> None:
        await tctx.db.execute("SELECT pg_terminate_backend(pg_backend_pid())")

    save_order, ran = orders_tool({1: killed})
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)))
    events = await k.events(handle.run_id)
    assert fold(events).steps[0].state == "RUNNING" and not [e for e in events if e.type == "STEP_FAILED"]
    assert await _rows(journal) == []

    await _take_over(k, handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert ran == [1, 2] and await _rows(journal) == [("o1", 2)]


BOUND = TIMEOUT + TOOL_TX_GRACE_S  # what `tool_db` sets for an attempt with all its time left


def _probe_the_lock(after_s: float, run_ids: list[Any], probe: dict[str, Any]) -> None:
    """From another thread — the holder's whole process is stopped — try for the run's row lock."""
    time.sleep(after_s)
    with psycopg.connect(DSN, autocommit=False) as conn:
        conn.execute("SET LOCAL lock_timeout = '500ms'")
        try:
            conn.execute("SELECT 1 FROM runs WHERE run_id = %s FOR UPDATE", (run_ids[0],))
            probe["locked_by_the_holder"] = False
        except psycopg.errors.LockNotAvailable:
            probe["locked_by_the_holder"] = True
        conn.rollback()


async def _frozen_holder(
    journal: PostgresJournal, freeze: Any, run_ids: list[Any], **work: Any
) -> tuple[Keel, Any, list[int]]:
    save_order, ran = orders_tool({1: freeze})
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})
    run_ids.append(handle.run_id)
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)), **work)
    return k, handle, ran


async def _the_successor_writes_once(k: Keel, journal: PostgresJournal, handle: Any, ran: list[int]) -> None:
    assert await _rows(journal) == [], "the frozen holder's INSERT went with its transaction"
    assert fold(await k.events(handle.run_id)).steps[0].state == "RUNNING", "abandoned: no outcome journaled"
    await _take_over(k, handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert ran == [1, 2] and await _rows(journal) == [("o1", 2)]


async def test_postgres_ends_the_transaction_of_a_holder_frozen_inside_it(journal: PostgresJournal) -> None:
    """The holder stops — the whole process, event loop and heartbeat included — with its INSERT
    written and the run's row locked by the fence. Only the server can end that transaction, and it
    does once it has sat idle for `timeout + TOOL_TX_GRACE_S`: a second connection can take the row lock
    while the holder is still stopped. The holder wakes into a dead connection and abandons — on Linux
    the engine's own next statement reads it as 25P03, an `InternalError` — and the successor writes once."""
    run_ids: list[Any] = []
    probe: dict[str, Any] = {}

    async def freeze(tctx: Any) -> None:
        threading.Thread(target=_probe_the_lock, args=(BOUND + 0.6, run_ids, probe), daemon=True).start()
        time.sleep(BOUND + 1.5)  # blocks the loop: nothing of this process runs, as under SIGSTOP

    k, handle, ran = await _frozen_holder(journal, freeze, run_ids)
    assert probe == {"locked_by_the_holder": False}, "the server ended the frozen holder's transaction"
    await _the_successor_writes_once(k, journal, handle, ran)


async def test_postgres_cancels_the_statement_of_a_holder_frozen_inside_it(journal: PostgresJournal) -> None:
    """Frozen *while a statement runs*, the transaction is not idle, so the idle bound cannot start:
    `statement_timeout` cancels the statement at the bound, the aborted transaction then idles, and the
    idle bound ends the session one bound later. The row lock is free within two bounds — where
    `pg_sleep(30)` alone would hold it for thirty seconds.

    What the holder reads on waking is a race: its statement's cancellation, a timeout it journals as a
    retryable failure and retries itself, or the session's end, an outage it abandons to a successor.
    Both are this class working: nothing of the first attempt commits, and exactly one row lands."""
    run_ids: list[Any] = []
    probe: dict[str, Any] = {}

    async def freeze_mid_statement(tctx: Any) -> None:
        threading.Thread(target=_probe_the_lock, args=(2 * BOUND + 0.8, run_ids, probe), daemon=True).start()
        asyncio.get_running_loop().call_later(0.2, time.sleep, 2 * BOUND + 1.5)  # stops 0.2 s into the query
        await tctx.db.execute("SELECT pg_sleep(30)")

    k, handle, ran = await _frozen_holder(journal, freeze_mid_statement, run_ids, retry=RETRY)
    assert probe == {"locked_by_the_holder": False}, "the server cancelled the statement, then ended the session"
    if fold(await k.events(handle.run_id)).phase != "COMPLETED":
        await _take_over(k, handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert ran == [1, 2] and await _rows(journal) == [("o1", 2)]


async def test_an_error_on_a_connection_the_server_ended_is_an_outage_whatever_its_class(
    journal: PostgresJournal,
) -> None:
    """The append reads the connection, not the error's class. Linux reports a session ended for idling
    as 25P03, an `InternalError` — no `OperationalError` — so this ends the session, lets psycopg find
    out, and raises that class from inside an append, on any platform."""
    k = Keel(journal=journal, programs=[place_order])
    await k.start(place_order, {})
    lease = await journal.claim("w1", timedelta(seconds=TTL))
    with pytest.raises(StoreUnavailable):
        async with journal.append(lease) as tx:
            pid = (await (await tx._conn.execute("SELECT pg_backend_pid()")).fetchone())[0]
            async with await psycopg.AsyncConnection.connect(DSN, autocommit=True) as other:
                await other.execute("SELECT pg_terminate_backend(%s)", (pid,))
            with contextlib.suppress(psycopg.OperationalError):
                await tx._conn.execute("SELECT 1")
            assert tx._conn.broken
            raise psycopg.errors.IdleInTransactionSessionTimeout("as Linux reports a session ended for idling")


# --- what a tool may not do to the transaction it is lent ----------------------------------------
async def test_an_error_the_tool_swallowed_still_fails_its_step(journal: PostgresJournal) -> None:
    """Caught without a savepoint, a SQL error still aborts the transaction, and the tool returning
    normally does not heal it: the step fails, naming the contract, before the journal's own statements
    can trip over the aborted transaction. Caught inside a savepoint, as `ToolCtx.db` says, it costs nothing."""

    async def swallow(tctx: Any) -> None:
        with contextlib.suppress(psycopg.errors.DivisionByZero):
            await tctx.db.execute("SELECT 1 / 0")

    async def savepoint(tctx: Any) -> None:
        with contextlib.suppress(psycopg.errors.DivisionByZero):
            async with tctx.db.transaction():
                await tctx.db.execute("SELECT 1 / 0")

    careless, ran = orders_tool({1: swallow})
    k = Keel(journal=journal, tools=[careless], programs=[place_order])
    handle = await k.start(place_order, {})
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "FAILED" and ran == [1]
    [failed] = [e for e in events if e.type == "STEP_FAILED"]
    assert failed.body.error.startswith("ContractViolation") and not failed.body.retryable
    assert await _rows(journal) == []

    careful, ran = orders_tool({1: savepoint})
    k = Keel(journal=journal, tools=[careful], programs=[place_order])
    result = await k.run(place_order, {})
    assert result.phase == "COMPLETED" and await _rows(journal) == [("o1", 1)]


async def test_a_deferred_constraint_fails_the_step_not_the_commit(journal: PostgresJournal) -> None:
    """A violation deferred to COMMIT would surface in the journal's statement, as the journal's error.
    The tool's constraints are checked when it returns, so the violation is the step's failure."""

    async def twice(tctx: Any) -> None:
        await tctx.db.execute("INSERT INTO txn_unique (id) VALUES ('dup'), ('dup')")

    save_order, ran = orders_tool({1: twice})
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "FAILED" and ran == [1]
    [failed] = [e for e in events if e.type == "STEP_FAILED"]
    assert failed.body.error.startswith("UniqueViolation") and not failed.body.retryable
    assert await _rows(journal) == []
    [effect] = await journal.effects(handle.run_id)
    assert effect.status == "ABSENT"


async def test_a_tool_that_commits_its_own_transaction_fails_its_step(journal: PostgresJournal) -> None:
    """A `COMMIT` the tool runs commits its INSERT outside the outcome — the one thing the class cannot
    take back. The step fails, naming the contract, rather than journaling a completion that was not
    atomic; the row the tool committed is what a broken contract leaves behind, and the test says so."""

    async def commit(tctx: Any) -> None:
        await tctx.db.execute("COMMIT")

    save_order, ran = orders_tool({1: commit})
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    handle = await k.start(place_order, {})
    await _work(k, "w1", await journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "FAILED" and ran == [1]
    [failed] = [e for e in events if e.type == "STEP_FAILED"]
    assert failed.body.error.startswith("ContractViolation") and not failed.body.retryable
    assert await _rows(journal) == [("o1", 1)]


async def test_what_a_tool_does_to_its_connection_never_reaches_the_pool(journal: PostgresJournal) -> None:
    """The connection a tool is lent is its own, closed with the transaction. A row factory or a session
    SET left on a pooled one would reach the next borrower — whose fence reads `row[0]`."""

    async def meddle(tctx: Any) -> None:
        tctx.db.row_factory = dict_row
        await tctx.db.execute("SET application_name = 'meddled'")

    save_order, _ = orders_tool({1: meddle})
    k = Keel(journal=journal, tools=[save_order], programs=[place_order])
    first, second = await k.run(place_order, {}), await k.run(place_order, {})
    assert first.phase == second.phase == "COMPLETED"
    pool = await journal._ready()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT current_setting('application_name'),"
            " (SELECT count(*) FROM pg_stat_activity WHERE application_name = 'meddled')"
        )
        setting, meddled = await cur.fetchone()
    assert setting != "meddled" and meddled == 0
