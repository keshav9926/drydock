"""Per-trial databases cloned from a template (§21.3 item 11).

`CREATE DATABASE trial_x TEMPLATE keel_template` costs tens to hundreds of milliseconds and gives
each trial its own tables on one Postgres, which is what makes matrix v0 affordable: 1 200 trials
serial is hours; six clones in parallel is well under one.

Deliberately keel-free. Each adapter owns its SUT's dependency (§13.3), so *what* is in the
template — Keel's migrations, DBOS's schema, nothing at all — is the adapter's business; this
module only clones and drops.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

import psycopg

_SAFE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def with_database(dsn: str, name: str) -> str:
    """The same DSN pointed at another database."""
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _ident(name: str) -> str:
    if not _SAFE.match(name):
        raise ValueError(f"unsafe database name {name!r}")
    return name


async def create_from_template(dsn: str, name: str, *, template: str, drop_first: bool = True) -> str:
    """Clone `template` into `name` and return the DSN that reaches it.

    `CREATE DATABASE` cannot run inside a transaction and refuses while anything else is connected
    to the template, so the template is never the database a trial runs against.
    """
    name, template = _ident(name), _ident(template)
    async with await psycopg.AsyncConnection.connect(_admin(dsn), autocommit=True) as conn:
        if drop_first:
            await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    return with_database(dsn, name)


async def drop(dsn: str, name: str) -> None:
    async with await psycopg.AsyncConnection.connect(_admin(dsn), autocommit=True) as conn:
        await conn.execute(f'DROP DATABASE IF EXISTS "{_ident(name)}" WITH (FORCE)')


async def ensure_template(dsn: str, template: str) -> str:
    """Create the (empty) template database if it does not exist; the caller migrates it."""
    template = _ident(template)
    async with await psycopg.AsyncConnection.connect(_admin(dsn), autocommit=True) as conn:
        cur = await conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (template,))
        if await cur.fetchone() is None:
            await conn.execute(f'CREATE DATABASE "{template}"')
    return with_database(dsn, template)


@asynccontextmanager
async def trial_database(dsn: str, name: str, *, template: str) -> AsyncIterator[str]:
    """One trial's database, dropped on the way out whether or not the trial passed."""
    trial_dsn = await create_from_template(dsn, name, template=template)
    try:
        yield trial_dsn
    finally:
        await drop(dsn, name)


def _admin(dsn: str) -> str:
    """CREATE/DROP DATABASE must be issued from a connection to some *other* database."""
    return with_database(dsn, "postgres")
