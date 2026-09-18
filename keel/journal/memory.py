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
from keel.core.errors import AmbiguousRunRef, DuplicateEffectKey, Fenced, IllegalTransition, WakeRaced
from keel.core.ids import EffectKey, RunId, uuid7
from keel.events import Envelope, Event
from keel.events.registry import CURRENT, body_from_payload, payload_of
from keel.journal.blobs import MemoryBlobStore, externalise, internalise
from keel.journal.protocol import (
    REPLAY_RESULTS,
    SIGNAL_TYPES,
    DelegationRow,
    EffectRow,
    Lease,
    RecoveryRow,
    ReplayRow,
    RunRow,
    SignalRow,
)

_TERMINAL = {"RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED"}
# The `recoveries.outcome` CHECK, mirrored. Postgres and this backend can disagree in exactly two
# places — the four control-plane statements and the CHECK constraints — so this one is copied
# rather than trusted: a permissive memory backend makes every fast test a lie.
_RECOVERY_OUTCOMES = frozenset(
    {"LIVE", "WAITING", "TERMINAL", "SUSPENDED", "FENCED", "RELEASED", "CRASHED", "FORCED_CANCEL"}
)
#: `effects_resolution_check` (0004), for the same reason. `None` is "not set by this update".
_EFFECT_RESOLUTIONS = frozenset({None, "probe", "assume_failed", "assume_succeeded", "escalate", "human"})


class _MemoryAppendTx:
    def __init__(self, journal: "MemoryJournal", lease: Lease) -> None:
        self._j = journal
        self._lease = lease
        self._events: list[Event] = []
        self._effects: list[EffectRow] = []
        self._effect_updates: list[tuple[EffectKey, dict[str, Any]]] = []
        self._run_fields: dict[str, Any] = {}
        self._consumed: list[tuple[Any, int]] = []
        self._signals_out: list[SignalRow] = []
        self._children: list[tuple[RunRow, Any, DelegationRow]] = []
        self._settlements: list[tuple[Any, str, dict[str, Any] | None, int]] = []
        self._wake_cleared = False
        self._release: dict[str, Any] | None = None
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
        if fields.get("resolution") not in _EFFECT_RESOLUTIONS:
            # `effects_resolution_check`, mirrored: a label Postgres refuses must not pass here.
            raise IllegalTransition(f"effects.resolution {fields['resolution']!r} violates the CHECK")
        self._effect_updates.append((effect_key, fields))

    async def set_run(self, **fields: Any) -> None:
        self._run_fields.update(fields)

    async def consume_signal(self, signal_id: Any, seq: int) -> None:
        self._consumed.append((signal_id, seq))

    # --- the wake path (§5.4 (4), (7)) -------------------------------------------
    async def pending_signals(self) -> list[SignalRow]:
        # The append holds the journal lock for its whole life, so no insert can land between this
        # read and the commit — the memory form of "the fence holds the row lock".
        return self._j._pending(self._lease.run_id)

    async def clear_wake(self) -> None:
        self._wake_cleared = True

    async def release_park(self, *, phase: str, wake_at: datetime | None, paused: bool = False) -> None:
        run = self._j._runs[self._lease.run_id]
        if run.runnable_at is not None and not self._wake_cleared:
            raise WakeRaced(f"run {self._lease.run_id}: a signal arrived since the last drain")
        self._release = {"phase": phase, "wake_at": wake_at, "paused": paused}

    # --- delegation (§17): three more things that commit with the append ----------
    async def insert_signal(self, row: SignalRow) -> None:
        _check_type(row)
        self._signals_out.append(row)

    async def create_child(self, row: RunRow, created: Any, delegation: DelegationRow) -> None:
        self._children.append((row, created, delegation))

    async def settle_delegation(
        self, delegation_id: Any, *, status: str, usage_settled: dict[str, Any] | None, settled_seq: int
    ) -> None:
        self._settlements.append((delegation_id, status, usage_settled, settled_seq))

    # --- commit / rollback ---------------------------------------------------
    def _validate(self) -> None:
        """Every guard Postgres would raise on, checked before anything is mutated. A violation in
        Postgres rolls the whole transaction back; here it must leave the store untouched too, or a
        fast test could pass on a half-committed state production never produces."""
        j = self._j
        log = list(j._events[self._lease.run_id])
        for ev in self._events:
            j._check_guards(log, ev)
            log.append(ev)
        keys = set(j._effects)
        for row in self._effects:
            if row.effect_key in keys:
                raise DuplicateEffectKey(row.effect_key)
            keys.add(row.effect_key)
        spawned = {
            (d.parent_run_id, d.parent_step_index, d.child_ordinal, d.retry_no)
            for d in j._delegations.values()
        }
        for _, _, d in self._children:
            key = (d.parent_run_id, d.parent_step_index, d.child_ordinal, d.retry_no)
            if key in spawned:
                raise IllegalTransition(f"delegation {key} already spawned")
            spawned.add(key)

    def _commit(self) -> None:
        self._validate()
        j = self._j
        run = j._runs[self._lease.run_id]
        log = j._events[self._lease.run_id]
        for ev in self._events:
            log.append(ev)
            if ev.type in _TERMINAL:
                run.terminal_at = ev.ts
        for row in self._effects:
            j._effects[row.effect_key] = row
        for key, fields in self._effect_updates:
            row = j._effects[key]
            for k, v in fields.items():
                setattr(row, k, v)
        for signal_id, seq in self._consumed:
            row = j._signals.get(signal_id)
            # `WHERE consumed_seq IS NULL`, in the same transaction as the event that says what was
            # done about it. A second drainer finding it already consumed does nothing, which is
            # the inbox's at-least-once contract holding rather than failing.
            if row is not None and row.consumed_seq is None:
                row.consumed_seq = seq
        for k, v in self._run_fields.items():
            setattr(run, k, v)
        if self._wake_cleared:
            run.runnable_at = None  # §5.4 (7)
        if self._release is not None:
            # §5.4 (4), the last statement: guarded in `release_park`, applied with the event.
            run.lease_expires_at = None
            run.runnable_at = None
            run.runnable_reason = None
            run.attempt_deadline = None
            run.wake_at = self._release["wake_at"]
            run.phase = self._release["phase"]
            if self._release["paused"]:
                run.paused_at = j.clock.now()
        # Delegation: the child's row, its RUN_CREATED at epoch 0 and the contract, in *this*
        # transaction beside the parent's CHILD_SPAWNED (§7.6.1). `delegations` is unique on
        # (parent, step, ordinal, retry), so a re-executed spawn is a loud violation, not a twin —
        # checked in `_validate`, before anything above was touched.
        for child, created, delegation in self._children:
            child.created_at = j.clock.now()
            child.runnable_at = j.clock.now()
            child.runnable_reason = "START"
            j._runs[child.run_id] = child
            payload = payload_of(created)
            env = Envelope(
                run_id=child.run_id, seq=1, ts=j.clock.now(),
                schema_version=CURRENT["RUN_CREATED"], lease_epoch=0,
                program_version=child.program_version, trace_id=child.trace_id, blob_ids=[],
            )
            j._events[child.run_id] = [Event(env=env, body=body_from_payload("RUN_CREATED", CURRENT["RUN_CREATED"], payload))]
            j._delegations[delegation.delegation_id] = delegation
        for delegation_id, status, usage, seq in self._settlements:
            d = j._delegations.get(delegation_id)
            if d is not None:
                d.status, d.usage_settled, d.settled_seq = status, usage, seq
        # A row in *another* run's inbox — the child's terminal event and its parent's
        # `child_result`, or the parent's acknowledgement and its children's `cancel` — commits
        # with this append or not at all (§5.10). Refused for a terminal target and deduplicated by
        # client_key like the API's insert, but no wake bump: the claim reads the inbox (§18.4),
        # and Postgres cannot bump a second runs row here without inverting the lock order.
        for row in self._signals_out:
            j._put_signal(row, wake=False)

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
        self._signals: dict[Any, SignalRow] = {}
        self._delegations: dict[Any, DelegationRow] = {}
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
            if t == "APPROVAL_REQUESTED" and old.type == t and old.step_index == si:
                raise IllegalTransition(f"second APPROVAL_REQUESTED for step {si}")  # events_approval_once
            if t in _TERMINAL and old.type in _TERMINAL:
                raise IllegalTransition("second terminal event")
            if t == "SEGMENT_STARTED" and old.type == t and old.body.segment_no == ev.body.segment_no:
                raise IllegalTransition(f"second SEGMENT_STARTED {ev.body.segment_no}")  # events_segment_once

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
        """§5.4 (2a) with §18.4's inbox clause: a run is a candidate when `runnable_at` is due *or*
        an unconsumed signal is waiting for it, so a wake bump that was lost cannot strand a run;
        a paused run only for a pending `resume` or `cancel` (§16.6)."""
        async with self._lock:
            now = self.clock.now()
            pending: dict[RunId, set[str]] = {}
            for s in self._signals.values():
                if s.consumed_seq is None:
                    pending.setdefault(s.run_id, set()).add(s.type)
            candidates = [
                r for r in self._runs.values()
                if (r.runnable_at is not None and r.runnable_at <= now) or r.run_id in pending
            ]
            for run in sorted(candidates, key=lambda r: (r.runnable_at is None, r.runnable_at or now)):
                if run.terminal_at is not None:
                    continue
                if run.paused_at is not None and not pending.get(run.run_id, set()) & {"resume", "cancel"}:
                    continue
                if run.lease_expires_at is not None and run.lease_expires_at >= now:
                    continue
                if run.attempt_deadline is not None and run.attempt_deadline >= now:
                    continue
                was_lapsed = run.lease_expires_at is not None
                # A run claimed through its inbox alone has no reason recorded: it was woken.
                cause = "ORPHANED" if was_lapsed else (run.runnable_reason or "WAKE")
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
                tx._commit()  # validates before it mutates, so a refusal here rolls back cleanly
            except BaseException:
                tx._rollback()
                raise

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

    # --- inbox (§5.6) --------------------------------------------------------
    async def insert_signal(self, row: SignalRow) -> bool:
        _check_type(row)
        async with self._lock:
            return self._put_signal(row)

    def _put_signal(self, row: SignalRow, *, wake: bool = True) -> bool:
        """The insert, under the lock the caller holds: the API's own, or an append transaction
        committing a row into *another* run's inbox (§5.10) — which does not bump (`wake=False`)."""
        run = self._runs.get(row.run_id)
        if run is None or run.terminal_at is not None:
            # §5.6: a signal addressed to a terminal run is refused before the insert — there
            # is no future holder to drain it, so the row would sit unconsumed for ever.
            return False
        if row.client_key is not None and any(
            r.run_id == row.run_id and r.client_key == row.client_key
            for r in self._signals.values()
        ):
            return False  # `signals_client_key`: the caller's retry, deduplicated
        # Postgres stamps `created_at` with `now()`, which is the *transaction* timestamp, so
        # two separate inserts always differ. A `FakeClock` does not move between them, and the
        # application order `(created_at, signal_id)` would then be decided by the random half
        # of a uuid7 minted in the same millisecond — two approvals racing in a test in an
        # order no real store would produce. Nudging past the last row models `now()`'s
        # resolution, for the same reason `_check_guards` mirrors the unique indexes: a
        # permissive memory backend makes every fast test a lie.
        now = self.clock.now()
        latest = max((r.created_at for r in self._signals.values() if r.created_at), default=None)
        if latest is not None and now <= latest:
            now = latest + timedelta(microseconds=1)
        row.created_at = row.created_at or now
        self._signals[row.signal_id] = row
        # The insert is also the wake (§5.4 (5)): the run becomes claimable, and on a held run the
        # bump is the pending-wake flag its release guard reads. `RESUME` names a manual resume.
        if wake and run.runnable_at is None:  # set only when unset, so a signal never jumps the queue
            run.runnable_reason = "RESUME" if row.type == "resume" else "WAKE"
            run.runnable_at = self.clock.now()
        return True

    def _pending(self, run_id: RunId) -> list[SignalRow]:
        rows = [r for r in self._signals.values() if r.run_id == run_id and r.consumed_seq is None]
        return sorted(rows, key=lambda r: (r.created_at or datetime.min, str(r.signal_id)))

    async def pending_signals(self, run_id: RunId) -> list[SignalRow]:
        async with self._lock:
            return self._pending(run_id)

    async def sweep_timers(self) -> int:
        """§5.4 (6). Only for a released run: a held one drains its own timers, and a row fired
        under a lease would be keyed `timer:<wake_at>` and so block the re-fire after release."""
        due = []
        async with self._lock:
            now = self.clock.now()
            for run in self._runs.values():
                if (
                    run.terminal_at is None and run.lease_expires_at is None
                    and run.wake_at is not None and run.wake_at <= now
                ):
                    due.append((run.run_id, run.wake_at))
        fired = 0
        for run_id, wake_at in due:
            if await self.insert_signal(
                SignalRow(
                    signal_id=uuid7(),
                    run_id=run_id,
                    type="timer",
                    payload={"wake_at": str(wake_at)},
                    client_key=f"timer:{wake_at.isoformat()}",
                    source="scheduler:timer",
                )
            ):
                fired += 1
        return fired

    # --- delegation (§17) ----------------------------------------------------
    async def children(self, parent_run_id: RunId) -> list[RunRow]:
        rows = [r for r in self._runs.values() if r.parent_run_id == parent_run_id]
        rows.sort(key=lambda r: (r.created_at or datetime.min, str(r.run_id)))
        return rows

    async def delegations(self, parent_run_id: RunId) -> list[DelegationRow]:
        rows = [d for d in self._delegations.values() if d.parent_run_id == parent_run_id]
        rows.sort(key=lambda d: (d.parent_step_index, d.child_ordinal, d.retry_no))
        return rows

    async def stray_children(self) -> list[RunRow]:
        return [
            r for r in self._runs.values()
            if r.parent_run_id is not None and r.terminal_at is None
            and (p := self._runs.get(r.parent_run_id)) is not None and p.terminal_at is not None
        ]

    async def takeover(
        self,
        child_run_id: RunId,
        worker_id: str,
        ttl: timedelta,
        *,
        cancel_grace: timedelta,
    ) -> Lease | None:
        """The fifth statement (§7.6.2), under the one lock: the read of the epoch and the move
        cannot straddle a heartbeat here any more than a pinned UPDATE can in Postgres."""
        async with self._lock:
            run = self._runs.get(child_run_id)
            now = self.clock.now()
            if run is None or run.parent_run_id is None or run.terminal_at is not None:
                return None
            if run.attempt_deadline is not None and run.attempt_deadline >= now:
                return None  # an open non-PURE attempt that could still commit (§8.4)
            told = any(
                r.run_id == child_run_id and r.type == "cancel"
                and r.created_at is not None and r.created_at + cancel_grace <= now
                for r in self._signals.values()
            )
            if not told:
                return None  # never asked to stop, or asked too recently to be forced
            return self._take(run, worker_id, ttl, "ORPHANED")

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


def _check_type(row: SignalRow) -> None:
    """The `signals.type` CHECK, mirrored — refused before anything is written."""
    if row.type not in SIGNAL_TYPES:
        raise IllegalTransition(f"unknown signal type {row.type!r}; one of {sorted(SIGNAL_TYPES)}")


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
