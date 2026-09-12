"""PostgresJournal — the four control-plane statements, and the fenced append transaction (§5.4).

This module is the one the human reads the diff on. Every control-plane write is a single
conditional UPDATE whose WHERE re-checks the state it assumes; under READ COMMITTED a row-locking
UPDATE that waits on a concurrent writer re-evaluates its WHERE against the committed row, which is
why two reapers, reaper-vs-heartbeat and heartbeat-vs-acquire races all resolve to "one wins, the
other sees 0 rows".
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from keel.core.errors import DuplicateEffectKey, Fenced
from keel.core.ids import EffectKey, RunId
from keel.events import Envelope, Event
from keel.events.registry import CURRENT, body_from_payload, payload_of
from keel.events.schema import TERMINAL_TYPES
from keel.journal.blobs import externalise, internalise
from keel.journal.protocol import EffectRow, Lease, RecoveryRow, ReplayRow, RunRow

SQL_DIR = Path(__file__).parent / "sql"

_RUN_SETTABLE = frozenset(
    {"phase", "attempt_deadline", "paused_at", "model_config", "program_version", "wake_at"}
)


class PostgresBlobStore:
    """Blobs are written in their own transaction, before the fenced append that references
    them — never inside it (§5.3), so a crash can only orphan a blob."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def put(self, data: bytes, *, media_type: str = "application/json") -> str:
        import hashlib

        blob_id = hashlib.sha256(data).hexdigest()
        async with self._pool.connection() as conn:
            await conn.execute(
                "INSERT INTO blobs (blob_id, size_bytes, media_type, content) VALUES (%s,%s,%s,%s)"
                " ON CONFLICT (blob_id) DO NOTHING",
                (blob_id, len(data), media_type, data),
            )
        return blob_id

    async def get(self, blob_id: str) -> bytes:
        async with self._pool.connection() as conn:
            cur = await conn.execute("SELECT content FROM blobs WHERE blob_id = %s", (blob_id,))
            row = await cur.fetchone()
        if row is None:
            raise KeyError(blob_id)
        return bytes(row[0])


class _PgAppendTx:
    def __init__(self, journal: "PostgresJournal", lease: Lease, conn: psycopg.AsyncConnection) -> None:
        self._j = journal
        self._lease = lease
        self._conn = conn
        self.start_seq = lease.next_seq

    async def now(self) -> datetime:
        """Postgres `now()` = transaction_timestamp: the append transaction's start time, which is
        exactly why S4 holds (STARTED.ts <= commit < dispatch < World receipt, §5.3)."""
        cur = await self._conn.execute("SELECT now()")
        return (await cur.fetchone())[0]

    async def append(self, body: Any, *, causation_seq: int | None = None) -> int:
        seq = self._lease.next_seq
        payload, blob_ids = await externalise(payload_of(body), self._j.blobs)
        await self._conn.execute(
            "INSERT INTO events (run_id, seq, type, schema_version, lease_epoch, program_version,"
            " causation_seq, trace_id, step_index, attempt_no, payload, blob_ids)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                self._lease.run_id,
                seq,
                body.type,
                CURRENT[body.type],
                self._lease.epoch,
                self._lease.program_version,
                causation_seq,
                self._lease.trace_id,
                getattr(body, "step_index", None),
                getattr(body, "attempt_no", None),
                Jsonb(payload),
                list(blob_ids),
            ),
        )
        if body.type in TERMINAL_TYPES:
            await self._conn.execute(
                "UPDATE runs SET terminal_at = now(), updated_at = now() WHERE run_id = %s",
                (self._lease.run_id,),
            )
        self._lease.next_seq += 1
        return seq

    async def write_effect(self, row: EffectRow) -> None:
        try:
            await self._conn.execute(
                "INSERT INTO effects (effect_key, run_id, run_root_id, step_index, tool, class,"
                " modifiers, status, attempt_no, intent_seq, started_seq, outcome_seq,"
                " attempt_deadline, resolution, external_ref, synthetic)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    row.effect_key,
                    row.run_id,
                    row.run_root_id,
                    row.step_index,
                    row.tool,
                    row.effect_class,
                    list(row.modifiers),
                    row.status,
                    row.attempt_no,
                    row.intent_seq,
                    row.started_seq,
                    row.outcome_seq,
                    row.attempt_deadline,
                    row.resolution,
                    row.external_ref,
                    row.synthetic,
                ),
            )
        except psycopg.errors.UniqueViolation as exc:  # loud, never a silent skip (§5.5)
            raise DuplicateEffectKey(row.effect_key) from exc

    async def update_effect(self, effect_key: EffectKey, **fields: Any) -> None:
        cols = ", ".join(f"{k} = %s" for k in fields)
        await self._conn.execute(
            f"UPDATE effects SET {cols}, updated_at = now() WHERE effect_key = %s",
            (*fields.values(), effect_key),
        )

    async def set_run(self, **fields: Any) -> None:
        bad = set(fields) - _RUN_SETTABLE
        if bad:
            raise ValueError(f"not a holder-writable runs column: {sorted(bad)}")
        values: list[Any] = []
        parts: list[str] = []
        for k, v in fields.items():
            parts.append(f"{k} = %s")
            values.append(Jsonb(v) if k == "model_config" else v)
        await self._conn.execute(
            f"UPDATE runs SET {', '.join(parts)}, updated_at = now()"
            " WHERE run_id = %s AND lease_epoch = %s",
            (*values, self._lease.run_id, self._lease.epoch),
        )


class PostgresJournal:
    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 8) -> None:
        self.dsn = dsn
        self._pool = AsyncConnectionPool(dsn, min_size=min_size, max_size=max_size, open=False)
        self._opened = False
        self.blobs = PostgresBlobStore(self._pool)

    async def _ready(self) -> AsyncConnectionPool:
        if not self._opened:
            await self._pool.open(wait=True, timeout=30)
            self._opened = True
        return self._pool

    async def close(self) -> None:
        if self._opened:
            await self._pool.close()
            self._opened = False

    # --- migrations ----------------------------------------------------------
    async def migrate(self) -> None:
        pool = await self._ready()
        async with pool.connection() as conn:
            for name in ("0001_init.sql", "0002_indexes.sql"):
                await conn.execute((SQL_DIR / name).read_text(encoding="utf8"))

    async def register_program(self, **f: Any) -> None:
        pool = await self._ready()
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO programs (program, program_version, declared_version, code_hash,"
                " entrypoint, keel_version, tools) VALUES (%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (program, program_version) DO UPDATE SET tools = EXCLUDED.tools,"
                " entrypoint = EXCLUDED.entrypoint",
                (
                    f["program"],
                    f["program_version"],
                    f["declared_version"],
                    f["code_hash"],
                    f["entrypoint"],
                    f["keel_version"],
                    Jsonb(dict(f.get("tools") or {})),
                ),
            )

    async def program_registered(self, program: str, program_version: str) -> bool:
        pool = await self._ready()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM programs WHERE program = %s AND program_version = %s",
                (program, program_version),
            )
            return await cur.fetchone() is not None

    # --- creation: the one append with no fence (§23.4) ----------------------
    async def create_run(self, row: RunRow, created: Any, *, runnable_at: datetime | None) -> None:
        pool = await self._ready()
        payload, blob_ids = await externalise(payload_of(created), self.blobs)
        async with pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    "INSERT INTO runs (run_id, run_root_id, program, program_version, keel_version,"
                    " model_config, args, budget, trace_id, phase, runnable_at, runnable_reason)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'CREATED',%s,%s)"
                    " ON CONFLICT (run_id) DO NOTHING",
                    (
                        row.run_id,
                        row.run_root_id,
                        row.program,
                        row.program_version,
                        row.keel_version,
                        Jsonb(dict(row.model_config)),
                        Jsonb(row.args),
                        Jsonb(dict(row.budget)),
                        row.trace_id,
                        runnable_at,
                        "START" if runnable_at else None,
                    ),
                )
                if cur.rowcount == 0:
                    return  # run_id given -> idempotent start (§24.1)
                await conn.execute(
                    "INSERT INTO events (run_id, seq, type, schema_version, lease_epoch,"
                    " program_version, trace_id, payload, blob_ids)"
                    " VALUES (%s, 1, 'RUN_CREATED', %s, 0, %s, %s, %s, %s)",
                    (
                        row.run_id,
                        CURRENT["RUN_CREATED"],
                        row.program_version,
                        row.trace_id,
                        Jsonb(payload),
                        list(blob_ids),
                    ),
                )

    # --- (2a) ACQUIRE, queue pop --------------------------------------------
    async def claim(self, worker_id: str, ttl: timedelta) -> Lease | None:
        pool = await self._ready()
        async with pool.connection() as conn:
            async with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    WITH cand AS (
                      SELECT run_id, runnable_reason,
                             (lease_expires_at IS NOT NULL) AS was_lapsed
                        FROM runs
                       WHERE runnable_at <= now()
                         AND terminal_at IS NULL
                         AND paused_at IS NULL
                         AND (lease_expires_at IS NULL OR lease_expires_at < now())
                         AND (attempt_deadline IS NULL OR attempt_deadline < now())
                       ORDER BY runnable_at
                       LIMIT 1 FOR UPDATE SKIP LOCKED)
                    UPDATE runs r
                       SET lease_epoch = r.lease_epoch + 1, lease_owner = %s,
                           lease_expires_at = now() + %s, runnable_at = NULL, wake_at = NULL,
                           orphaned_at = NULL, updated_at = now()
                      FROM cand
                     WHERE r.run_id = cand.run_id
                       AND r.terminal_at IS NULL
                       AND (r.lease_expires_at IS NULL OR r.lease_expires_at < now())
                    RETURNING r.run_id, r.lease_epoch, r.program_version, r.trace_id,
                              r.lease_expires_at,
                              CASE WHEN cand.was_lapsed THEN 'ORPHANED'
                                   ELSE coalesce(cand.runnable_reason, 'START') END AS cause
                    """,
                    (worker_id, ttl),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return await self._finish_acquire(conn, row, worker_id, ttl)

    # --- (2b) ACQUIRE, targeted maintenance ---------------------------------
    async def acquire(self, run_id: RunId, worker_id: str, ttl: timedelta) -> Lease | None:
        pool = await self._ready()
        async with pool.connection() as conn:
            async with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE runs
                       SET lease_epoch = lease_epoch + 1, lease_owner = %s,
                           lease_expires_at = now() + %s, runnable_at = NULL, wake_at = NULL,
                           orphaned_at = NULL, updated_at = now()
                     WHERE run_id = %s
                       AND (lease_expires_at IS NULL OR lease_expires_at < now())
                       AND (attempt_deadline IS NULL OR attempt_deadline < now())
                    RETURNING run_id, lease_epoch, program_version, trace_id, lease_expires_at,
                              'RESUME' AS cause
                    """,
                    (worker_id, ttl, run_id),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return await self._finish_acquire(conn, row, worker_id, ttl)

    async def _finish_acquire(
        self, conn: psycopg.AsyncConnection, row: Mapping[str, Any], worker_id: str, ttl: timedelta
    ) -> Lease:
        cur = await conn.execute(
            "SELECT coalesce(max(seq), 0) FROM events WHERE run_id = %s", (row["run_id"],)
        )
        head = (await cur.fetchone())[0]
        # The previous epoch died without releasing or being fenced: record it before we overwrite
        # the run's lease columns, so L2 can count recoveries the journal cannot show (§5.7).
        await conn.execute(
            "UPDATE recoveries SET outcome = 'CRASHED' WHERE run_id = %s AND lease_epoch = %s"
            " AND released_at IS NULL AND (outcome IS NULL OR outcome = 'LIVE')",
            (row["run_id"], row["lease_epoch"] - 1),
        )
        await conn.execute(
            "INSERT INTO recoveries (run_id, lease_epoch, worker_id, cause, from_seq)"
            " VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (row["run_id"], row["lease_epoch"], worker_id, row["cause"], head),
        )
        loop_now = asyncio.get_running_loop().time()
        return Lease(
            run_id=row["run_id"],
            epoch=row["lease_epoch"],
            worker_id=worker_id,
            expires_at=row["lease_expires_at"],
            next_seq=head + 1,
            program_version=row["program_version"],
            trace_id=row["trace_id"],
            cause=row["cause"],
            ttl_seconds=ttl.total_seconds(),
            valid_until_mono=loop_now + ttl.total_seconds(),
        )

    # --- (1) FENCE = HEARTBEAT ----------------------------------------------
    @staticmethod
    async def _fence(conn: psycopg.AsyncConnection, lease: Lease) -> bool:
        sent_mono = asyncio.get_running_loop().time()
        cur = await conn.execute(
            "UPDATE runs SET lease_expires_at = now() + %s, orphaned_at = NULL, updated_at = now()"
            " WHERE run_id = %s AND lease_epoch = %s AND lease_expires_at IS NOT NULL"
            " RETURNING lease_expires_at",
            (timedelta(seconds=lease.ttl_seconds), lease.run_id, lease.epoch),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        lease.expires_at = row[0]
        # armed at *send* time, the conservative end of the round trip (§8.4)
        lease.valid_until_mono = sent_mono + lease.ttl_seconds
        return True

    @asynccontextmanager
    async def append(self, lease: Lease):
        pool = await self._ready()
        async with pool.connection() as conn:
            tx = _PgAppendTx(self, lease, conn)
            try:
                async with conn.transaction():
                    if not await self._fence(conn, lease):
                        raise Fenced(f"run {lease.run_id} epoch {lease.epoch}")
                    yield tx
            except BaseException:
                lease.next_seq = tx.start_seq  # the counter is rewound on rollback (§6.3)
                raise

    async def heartbeat(self, lease: Lease, ttl: timedelta | None = None) -> bool:
        pool = await self._ready()
        if ttl is not None:
            lease.ttl_seconds = ttl.total_seconds()
        async with pool.connection() as conn:
            return await self._fence(conn, lease)

    # --- (4) RELEASE ---------------------------------------------------------
    async def release(
        self,
        lease: Lease,
        *,
        runnable_at: datetime | None = None,
        wake_at: datetime | None = None,
        phase: str | None = None,
        runnable_reason: str | None = None,
    ) -> None:
        pool = await self._ready()
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE runs SET lease_expires_at = NULL, runnable_at = %s, wake_at = %s,"
                " phase = coalesce(%s, phase), runnable_reason = %s,"
                " attempt_deadline = NULL, updated_at = now()"
                " WHERE run_id = %s AND lease_epoch = %s AND lease_expires_at IS NOT NULL",
                (runnable_at, wake_at, phase, runnable_reason, lease.run_id, lease.epoch),
            )
            await conn.execute(
                "UPDATE recoveries SET released_at = now() WHERE run_id = %s AND lease_epoch = %s",
                (lease.run_id, lease.epoch),
            )

    # --- (3) ORPHAN ----------------------------------------------------------
    async def reap(self) -> list[RunId]:
        pool = await self._ready()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE runs SET orphaned_at = now(), runnable_at = now(),"
                " runnable_reason = 'ORPHANED', updated_at = now()"
                " WHERE terminal_at IS NULL"
                "   AND lease_expires_at IS NOT NULL AND lease_expires_at < now()"
                "   AND (attempt_deadline IS NULL OR now() > attempt_deadline)"
                " RETURNING run_id"
            )
            return [r[0] for r in await cur.fetchall()]

    async def mark_runnable(self, run_id: RunId, reason: str = "RESUME") -> bool:
        """MVP `keel resume` (§27.2, 4.10). Replaced by the signals inbox at v1."""
        pool = await self._ready()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE runs SET runnable_at = now(), runnable_reason = %s, updated_at = now()"
                " WHERE run_id = %s AND terminal_at IS NULL",
                (reason, run_id),
            )
            return cur.rowcount > 0

    # --- reads ---------------------------------------------------------------
    async def read(self, run_id: RunId, *, from_seq: int = 0) -> list[Event]:
        pool = await self._ready()
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM events WHERE run_id = %s AND seq > %s ORDER BY seq",
                (run_id, from_seq),
            )
            rows = await cur.fetchall()
        return [await self._to_event(r) for r in rows]

    async def _to_event(self, r: Mapping[str, Any]) -> Event:
        payload = await internalise(dict(r["payload"]), self.blobs)
        body = body_from_payload(r["type"], r["schema_version"], payload)
        env = Envelope(
            run_id=r["run_id"],
            seq=r["seq"],
            ts=r["ts"],
            schema_version=r["schema_version"],
            lease_epoch=r["lease_epoch"],
            program_version=r["program_version"],
            trace_id=r["trace_id"],
            causation_seq=r["causation_seq"],
            blob_ids=tuple(r["blob_ids"] or ()),
        )
        return Event(env=env, body=body)

    async def tail(self, run_id: RunId, *, from_seq: int = 0) -> AsyncIterator[Event]:
        seen = from_seq
        while True:
            for ev in await self.read(run_id, from_seq=seen):
                seen = ev.seq
                yield ev
            await asyncio.sleep(1.0)  # LISTEN/NOTIFY is v1; the 1 s poll is the guarantee (§8.7)

    async def run_row(self, run_id: RunId) -> RunRow | None:
        pool = await self._ready()
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT * FROM runs WHERE run_id = %s", (run_id,))
            row = await cur.fetchone()
        return _run_row(row) if row else None

    async def list_runs(self, *, phase: str | None = None, limit: int = 50) -> list[RunRow]:
        pool = await self._ready()
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM runs WHERE (%s::text IS NULL OR phase = %s)"
                " ORDER BY created_at DESC LIMIT %s",
                (phase, phase, limit),
            )
            return [_run_row(r) for r in await cur.fetchall()]

    async def effects(self, run_id: RunId) -> list[EffectRow]:
        pool = await self._ready()
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM effects WHERE run_id = %s ORDER BY step_index", (run_id,)
            )
            return [
                EffectRow(
                    effect_key=r["effect_key"],
                    run_id=r["run_id"],
                    run_root_id=r["run_root_id"],
                    step_index=r["step_index"],
                    tool=r["tool"],
                    effect_class=r["class"],
                    status=r["status"],
                    intent_seq=r["intent_seq"],
                    modifiers=tuple(r["modifiers"] or ()),
                    attempt_no=r["attempt_no"],
                    started_seq=r["started_seq"],
                    outcome_seq=r["outcome_seq"],
                    attempt_deadline=r["attempt_deadline"],
                    resolution=r["resolution"],
                    external_ref=r["external_ref"],
                    synthetic=r["synthetic"],
                )
                for r in await cur.fetchall()
            ]

    async def recoveries(self, run_id: RunId) -> list[RecoveryRow]:
        pool = await self._ready()
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM recoveries WHERE run_id = %s ORDER BY lease_epoch", (run_id,)
            )
            return [
                RecoveryRow(
                    run_id=r["run_id"],
                    lease_epoch=r["lease_epoch"],
                    worker_id=r["worker_id"],
                    cause=r["cause"],
                    from_seq=r["from_seq"],
                    acquired_at=r["acquired_at"],
                    started_seq=r["started_seq"],
                    completed_seq=r["completed_seq"],
                    completed_at=r["completed_at"],
                    live_from_step=r["live_from_step"],
                    replayed_steps=r["replayed_steps"],
                    replay_ms=r["replay_ms"],
                    outcome=r["outcome"],
                    released_at=r["released_at"],
                )
                for r in await cur.fetchall()
            ]

    async def set_recovery(self, run_id: RunId, lease_epoch: int, **fields: Any) -> None:
        if not fields:
            return
        pool = await self._ready()
        cols = ", ".join(f"{k} = %s" for k in fields)
        async with pool.connection() as conn:
            await conn.execute(
                f"UPDATE recoveries SET {cols} WHERE run_id = %s AND lease_epoch = %s",
                (*fields.values(), run_id, lease_epoch),
            )

    async def record_replay(self, row: ReplayRow) -> None:
        """One row, written once, at the end of a pass. VERIFY appends no events, so this is the
        entire durable trace of it (§5.7)."""
        pool = await self._ready()
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO replays (replay_id, run_id, mode, requested_by, program_version, "
                "base_seq, fork_run_id, result, replayed_steps, elapsed_ms, projection_hash, "
                "diff_blob_id, finished_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())",
                (
                    row.replay_id,
                    row.run_id,
                    row.mode,
                    row.requested_by,
                    row.program_version,
                    row.base_seq,
                    row.fork_run_id,
                    row.result,
                    row.replayed_steps,
                    row.elapsed_ms,
                    row.projection_hash,
                    row.diff_blob_id,
                ),
            )

    async def replays(self, run_id: RunId) -> list[ReplayRow]:
        pool = await self._ready()
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM replays WHERE run_id = %s ORDER BY started_at", (run_id,)
            )
            return [ReplayRow(**r) for r in await cur.fetchall()]

    async def resolve_run_id(self, prefix: str) -> RunId | None:
        pool = await self._ready()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT run_id FROM runs WHERE run_id::text LIKE %s LIMIT 2", (prefix + "%",)
            )
            rows = await cur.fetchall()
        return rows[0][0] if len(rows) == 1 else None


def _run_row(r: Mapping[str, Any]) -> RunRow:
    return RunRow(
        run_id=r["run_id"],
        run_root_id=r["run_root_id"],
        program=r["program"],
        program_version=r["program_version"],
        keel_version=r["keel_version"],
        phase=r["phase"],
        trace_id=r["trace_id"],
        args=r["args"],
        budget=r["budget"],
        model_config=r["model_config"],
        lease_owner=r["lease_owner"],
        lease_epoch=r["lease_epoch"],
        lease_expires_at=r["lease_expires_at"],
        runnable_at=r["runnable_at"],
        runnable_reason=r["runnable_reason"],
        wake_at=r["wake_at"],
        orphaned_at=r["orphaned_at"],
        paused_at=r["paused_at"],
        terminal_at=r["terminal_at"],
        attempt_deadline=r["attempt_deadline"],
        created_at=r["created_at"],
    )


__all__ = ["PostgresBlobStore", "PostgresJournal", "UUID"]
