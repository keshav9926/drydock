"""Per-trial databases cloned from a template (§21.3 item 11).

Matrix v0 is 1 200 trials. Serial, that is hours; six clones running in parallel on one Postgres is
under one, which is what makes a same-day re-run affordable — so the clone is a day-2 deliverable
rather than a day-3 optimisation.

    docker compose up -d postgres
    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import os

import pytest

from crashproof.runner import database
from keel.journal.postgres import PostgresJournal

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TEMPLATE = "keel_trial_template"


async def test_a_trial_gets_its_own_migrated_database() -> None:
    template_dsn = await database.ensure_template(DSN, TEMPLATE)
    template = PostgresJournal(template_dsn)
    try:
        await template.migrate()  # the adapter owns its SUT's schema; the cloner knows nothing
    finally:
        await template.close()  # CREATE DATABASE ... TEMPLATE refuses while anything is connected

    async with database.trial_database(DSN, "keel_trial_probe", template=TEMPLATE) as trial_dsn:
        assert trial_dsn.endswith("/keel_trial_probe")
        trial = PostgresJournal(trial_dsn)
        try:
            pool = await trial._ready()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
                )
                assert (await cur.fetchone())[0] >= 9, "the clone carries the template's schema"
                cur = await conn.execute("SELECT count(*) FROM runs")
                assert (await cur.fetchone())[0] == 0, "and none of another trial's rows"
        finally:
            await trial.close()

    async with await _connect() as conn:
        cur = await conn.execute("SELECT 1 FROM pg_database WHERE datname = 'keel_trial_probe'")
        assert await cur.fetchone() is None, "a trial database does not outlive its trial"

    await database.drop(DSN, TEMPLATE)


def test_a_database_name_is_never_interpolated_unchecked() -> None:
    """`CREATE DATABASE` cannot take a parameter, so the name is checked rather than bound."""
    for bad in ("trial; DROP DATABASE keel", 'trial"x', "Trial-1", ""):
        with pytest.raises(ValueError):
            database._ident(bad)


async def _connect():
    import psycopg

    return await psycopg.AsyncConnection.connect(database.with_database(DSN, "postgres"), autocommit=True)
