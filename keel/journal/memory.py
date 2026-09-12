"""MemoryJournal — the same semantics as Postgres, in dicts (§23.1).

It exists so the property suite, the hook-mode conformance cells and every fast test can run the
*real* runtime against a fake store. That means it must enforce the same epoch check, the same
natural-key guards and the same claim/orphan predicates; a MemoryJournal that is merely permissive
would make the property suite prove nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from keel.core.clock import Clock, SystemClock
from keel.core.errors import AmbiguousRunRef, DuplicateEffectKey, Fenced, IllegalTransition
from keel.core.ids import EffectKey, RunId
from keel.events import Envelope, Event
from keel.events.registry import CURRENT, body_from_payload, payload_of
from keel.journal.blobs import MemoryBlobStore, externalise, internalise
from keel.journal.protocol import (
    REPLAY_RESULTS,
    EffectRow,
    Lease,
    RecoveryRow,
    ReplayRow,
    RunRow,
)

_TERMINAL = {"RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED"}
# The `recoveries.outcome` CHECK, mirrored. Postgres and this backend can disagree in exactly two
# places — the four control-plane statements and the CHECK constraints — so this one is copied
# rather than trusted: a permissive memory backend makes every fast test a lie.
_RECOVERY_OUTCOMES = frozenset(
    {"LIVE", "WAITING", "TERMINAL", "SUSPENDED", "FENCED", "RELEASED", "CRASHED", "FORCED_CANCEL"}
)


class _MemoryAppendTx:
    def __init__(self, journal: "MemoryJournal", lease: Lease) -> None:
        self._j = journal
        self._lease = lease
        self._events: list[Event] = []
        self._effects: list[EffectRow] = []
        self._effect_updates: list[tuple[EffectKey, dict[str, Any]]] = []
        self._run_fields: dict[str, Any] = {}
        self._start_seq = lease.next_seq

    async def now(self) -> datetime:
        return self._j.clock.now()

    async def append(self, body: Any, *, causation_seq: int | None = None) -> int:
        seq = self._lease.next_seq
        payload, blob_ids = await externalise(payload_of(body), self._j.blobs)
        # Re-validate through the registry so an in-memory append takes the same load path as a
        # Postgres one; a body that cannot round-trip is a writer bug, caught here.
        body = body_from_payload(body.type, CURRENT[body.type], payload)
        env = Envelope(
            run_id=self._lease.run_id,
            seq=seq,
            ts=self._j.clock.now(),
            schema_version=CURRENT[body.type],
            lease_epoch=self._lease.epoch,
            program_version=self._lease.program_version,
            trace_id=self._lease.trace_id,
            causation_seq=causation_seq,
            blob_ids=blob_ids,
        )
        self._events.append(Event(env=env, body=body))
        self._lease.next_seq += 1
        return seq

    async def write_effect(self, row: EffectRow) -> None:
        self._effects.append(row)

    async def update_effect(self, effect_key: EffectKey, **fields: Any) -> None:
        self._effect_updates.append((effect_key, fields))

    async def set_run(self, **fields: Any) -> None:
        self._run_fields.update(fields)

    # --- commit / rollback ---------------------------------------------------
    def _commit(self) -> None:
        j = self._j
        run = j._runs[self._lease.run_id]
        log = j._events[self._lease.run_id]
        for ev in self._events:
            j._check_guards(log, ev)
            log.append(ev)
            if ev.type in _TERMINAL:
                run.terminal_at = ev.ts
        for row in self._effects:
            if row.effect_key in j._effects:
                raise DuplicateEffectKey(row.effect_key)
            j._effects[row.effect_key] = row
        for key, fields in self._effect_updates:
            row = j._effects[key]
            for k, v in fields.items():
                setattr(row, k, v)
        for k, v in self._run_fields.items():
            setattr(run, k, v)

    def _rollback(self) -> None:
        self._lease.next_seq = self._start_seq


class MemoryJournal:
    def __init__(self, clock: Clock | None = None) -> None:
        self.clock: Clock = clock or SystemClock()
        self.blobs = MemoryBlobStore()
        self._runs: dict[RunId, RunRow] = {}
        self._events: dict[RunId, list[Event]] = {}
        self._effects: dict[EffectKey, EffectRow] = {}
        self._recoveries: dict[tuple[RunId, int], RecoveryRow] = {}
        self._replays: list[ReplayRow] = []
        self._programs: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    # --- guards mirroring the partial unique indexes of §5.3 -----------------
    @staticmethod
    def _check_guards(log: list[Event], ev: Event) -> None:
        t, si, an = ev.type, ev.step_index, ev.attempt_no
        for old in log:
            if old.seq == ev.seq:
                raise IllegalTransition(f"duplicate seq {ev.seq}")
            if t == "STEP_INTENDED" and old.type == t and old.step_index == si:
                raise IllegalTransition(f"second STEP_INTENDED for step {si}")
            if t == "STEP_ATTEMPT_STARTED" and old.type == t and (old.step_index, old.attempt_no) == (si, an):
                raise IllegalTransition(f"second STARTED for step {si} attempt {an}")
            if (
                t in {"STEP_COMPLETED", "STEP_FAILED", "STEP_AMBIGUOUS"}
                and old.type in {"STEP_COMPLETED", "STEP_FAILED", "STEP_AMBIGUOUS"}
                and (old.step_index, old.attempt_no) == (si, an)
            ):
                raise IllegalTransition(f"second outcome for step {si} attempt {an}")
            if t == "RECOVERY_STARTED" and old.type == t and old.lease_epoch == ev.lease_epoch:
                raise IllegalTransition(f"second RECOVERY_STARTED for epoch {ev.lease_epoch}")
            if t in _TERMINAL and old.type in _TERMINAL:
                raise IllegalTransition("second terminal event")

    # --- lifecycle -----------------------------------------------------------
    async def migrate(self) -> None:
        return None

    async def register_program(self, **fields: Any) -> None:
        self._programs[(fields["program"], fields["program_version"])] = fields

    async def program_registered(self, program: str, program_version: str) -> bool:
        return (program, program_version) in self._programs

    async def create_run(self, row: RunRow, created: Any, *, runnable_at: datetime | None) -> None:
        if row.run_id in self._runs:
            return  # run_id given -> idempotent start (§24.1)
        row.runnable_at = runnable_at
        row.runnable_reason = "START" if runnable_at else None
        row.created_at = self.clock.now()
        self._runs[row.run_id] = row
        payload, blob_ids = await externalise(payload_of(created), self.blobs)
        env = Envelope(
            run_id=row.run_id,
            seq=1,
            ts=self.clock.now(),
            schema_version=CURRENT["RUN_CREATED"],
            lease_epoch=0,
            program_version=row.program_version,
            trace_id=row.trace_id,
            blob_ids=blob_ids,
        )
        body = body_from_payload("RUN_CREATED", CURRENT["RUN_CREATED"], payload)
        self._events[row.run_id] = [Event(env=env, body=body)]

    # --- the four control-plane statements (§5.4) ---------------------------
    async def claim(self, worker_id: str, ttl: timedelta) -> Lease | None:
        async with self._lock:
            now = self.clock.now()
            for run in sorted(
                (r for r in self._runs.values() if r.runnable_at is not None),
                key=lambda r: r.runnable_at,  # type: ignore[arg-type,return-value]
            ):
                if run.runnable_at > now or run.terminal_at is not None:
                    continue
                if run.paused_at is not None:
                    continue
                if run.lease_expires_at is not None and run.lease_expires_at >= now:
                    continue
                if run.attempt_deadline is not None and run.attempt_deadline >= now:
                    continue
                was_lapsed = run.lease_expires_at is not None
                cause = "ORPHANED" if was_lapsed else (run.runnable_reason or "START")
                return self._take(run, worker_id, ttl, cause)  # type: ignore[arg-type]
            return None

    async def acquire(self, run_id: RunId, worker_id: str, ttl: timedelta) -> Lease | None:
        async with self._lock:
            run = self._runs.get(run_id)
            now = self.clock.now()
            if run is None:
                return None
            if run.lease_expires_at is not None and run.lease_expires_at >= now:
                return None
            if run.attempt_deadline is not None and run.attempt_deadline >= now:
                return None
            return self._take(run, worker_id, ttl, "RESUME")

    def _take(self, run: RunRow, worker_id: str, ttl: timedelta, cause: str) -> Lease:
        now = self.clock.now()
        run.lease_epoch += 1
        run.lease_owner = worker_id
        run.lease_expires_at = now + ttl
        run.runnable_at = None
        run.wake_at = None
        run.orphaned_at = None
        log = self._events.get(run.run_id, [])
        from_seq = log[-1].seq if log else 0
        self._recoveries[(run.run_id, run.lease_epoch)] = RecoveryRow(
            run_id=run.run_id,
            lease_epoch=run.lease_epoch,
            worker_id=worker_id,
            cause=cause,  # type: ignore[arg-type]
            from_seq=from_seq,
            acquired_at=now,
        )
        return Lease(
            run_id=run.run_id,
            epoch=run.lease_epoch,
            worker_id=worker_id,
            expires_at=run.lease_expires_at,
            next_seq=from_seq + 1,
            program_version=run.program_version,
            trace_id=run.trace_id,
            cause=cause,  # type: ignore[arg-type]
            ttl_seconds=ttl.total_seconds(),
            valid_until_mono=asyncio.get_running_loop().time() + ttl.total_seconds(),
        )

    def _fence(self, lease: Lease) -> None:
        """UPDATE runs SET lease_expires_at = now() + ttl, orphaned_at = NULL
        WHERE run_id = $1 AND lease_epoch = $2 AND lease_expires_at IS NOT NULL. 0 rows => Fenced."""
        run = self._runs.get(lease.run_id)
        if run is None or run.lease_epoch != lease.epoch or run.lease_expires_at is None:
            raise Fenced(f"run {lease.run_id} epoch {lease.epoch}")
        run.lease_expires_at = self.clock.now() + timedelta(seconds=lease.ttl_seconds)
        run.orphaned_at = None
        lease.expires_at = run.lease_expires_at
        lease.valid_until_mono = asyncio.get_running_loop().time() + lease.ttl_seconds

    @asynccontextmanager
    async def append(self, lease: Lease):
        async with self._lock:
            self._fence(lease)  # first statement of every append transaction
            tx = _MemoryAppendTx(self, lease)
            try:
                yield tx
            except BaseException:
                tx._rollback()
                raise
            tx._commit()

    async def heartbeat(self, lease: Lease, ttl: timedelta | None = None) -> bool:
        async with self._lock:
            if ttl is not None:
                lease.ttl_seconds = ttl.total_seconds()
            try:
                self._fence(lease)
            except Fenced:
                return False
            return True

    async def release(
        self,
        lease: Lease,
        *,
        runnable_at: datetime | None = None,
        wake_at: datetime | None = None,
        phase: str | None = None,
        runnable_reason: str | None = None,
    ) -> None:
        async with self._lock:
            run = self._runs.get(lease.run_id)
            if run is None or run.lease_epoch != lease.epoch or run.lease_expires_at is None:
                return
            run.lease_expires_at = None
            run.runnable_at = runnable_at
            run.runnable_reason = runnable_reason
            run.wake_at = wake_at
            if phase:
                run.phase = phase

    async def reap(self) -> list[RunId]:
        """now() > max(lease_expires_at, attempt_deadline) — one predicate, no successor-side wait."""
        async with self._lock:
            now = self.clock.now()
            orphaned: list[RunId] = []
            for run in self._runs.values():
                if run.terminal_at is not None or run.lease_expires_at is None:
                    continue
                if run.lease_expires_at >= now:
                    continue
                if run.attempt_deadline is not None and run.attempt_deadline >= now:
                    continue
                run.orphaned_at = now
                run.runnable_at = now
                run.runnable_reason = "ORPHANED"
                orphaned.append(run.run_id)
            return orphaned

    async def mark_runnable(self, run_id: RunId, reason: str = "RESUME") -> bool:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.terminal_at is not None:
                return False
            run.runnable_at = self.clock.now()
            run.runnable_reason = reason
            return True

    # --- reads ---------------------------------------------------------------
    async def read(self, run_id: RunId, *, from_seq: int = 0) -> list[Event]:
        out = []
        for ev in self._events.get(run_id, []):
            if ev.seq <= from_seq:
                continue
            payload = await internalise(payload_of(ev.body), self.blobs)
            body = body_from_payload(ev.type, ev.env.schema_version, payload)
            out.append(Event(env=ev.env, body=body))
        return out

    async def tail(self, run_id: RunId, *, from_seq: int = 0) -> AsyncIterator[Event]:
        seen = from_seq
        while True:
            for ev in await self.read(run_id, from_seq=seen):
                seen = ev.seq
                yield ev
            await asyncio.sleep(0.1)

    async def run_row(self, run_id: RunId) -> RunRow | None:
        return self._runs.get(run_id)

    async def list_runs(self, *, phase: str | None = None, limit: int = 50) -> list[RunRow]:
        rows = [r for r in self._runs.values() if phase is None or r.phase == phase]
        rows.sort(key=lambda r: r.created_at or datetime.min, reverse=True)
        return rows[:limit]

    async def effects(self, run_id: RunId) -> list[EffectRow]:
        rows = [e for e in self._effects.values() if e.run_id == run_id]
        rows.sort(key=lambda e: e.step_index)
        return rows

    async def recoveries(self, run_id: RunId) -> list[RecoveryRow]:
        rows = [r for r in self._recoveries.values() if r.run_id == run_id]
        rows.sort(key=lambda r: r.lease_epoch)
        return rows

    async def set_recovery(self, run_id: RunId, lease_epoch: int, **fields: Any) -> None:
        if fields.get("outcome") is not None and fields["outcome"] not in _RECOVERY_OUTCOMES:
            raise IllegalTransition(f"unknown recovery outcome {fields['outcome']!r}")
        row = self._recoveries.get((run_id, lease_epoch))
        if row is None:
            return
        for k, v in fields.items():
            setattr(row, k, v)

    async def record_replay(self, row: ReplayRow) -> None:
        if row.result is not None and row.result not in REPLAY_RESULTS:
            raise IllegalTransition(f"unknown replay result {row.result!r}")
        self._replays.append(row)

    async def replays(self, run_id: RunId) -> list[ReplayRow]:
        return [r for r in self._replays if r.run_id == run_id]

    async def resolve_run_id(self, prefix: str) -> RunId | None:
        matches = [r for r in self._runs if str(r).startswith(prefix)]
        if len(matches) > 1:
            raise AmbiguousRunRef(prefix, len(matches))
        return matches[0] if matches else None

    async def close(self) -> None:
        return None


def memory_run_row(
    *,
    run_id: RunId,
    program: str,
    program_version: str,
    keel_version: str,
    args: Any,
    budget: Mapping[str, Any],
    model_config: Mapping[str, Any],
    trace_id: UUID | None = None,
) -> RunRow:
    return RunRow(
        run_id=run_id,
        run_root_id=run_id,
        program=program,
        program_version=program_version,
        keel_version=keel_version,
        phase="CREATED",
        trace_id=trace_id or run_id,
        args=args,
        budget=dict(budget),
        model_config=dict(model_config),
    )
