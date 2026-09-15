"""JournalBackend, AppendTx, BlobStore, and the two rows that are not events (§23.4).

Two backends behind one protocol: `MemoryJournal` (tests, property-based testing, fast loops) and
`PostgresJournal` (real). No third.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

from keel.core.ids import EffectKey, RunId, SignalId
from keel.events import Event

RecoveryCause = Literal["START", "WAKE", "ORPHANED", "RESUME", "DRAIN"]
EffectStatus = Literal[
    "INTENDED",
    "STARTED",
    "COMMITTED",
    "ABSENT",
    "AMBIGUOUS",
    "RESOLVED_COMMITTED",
    "RESOLVED_ABSENT",
    "RESOLVED_UNKNOWN",
    "CANCELLED",
    "DENIED",
]


@dataclass(slots=True)
class Lease:
    """The right to write. `epoch` is the fencing token; `next_seq` is the in-memory seq counter
    read once at acquisition and rewound on rollback (§5.3)."""

    run_id: RunId
    epoch: int
    worker_id: str
    expires_at: datetime
    next_seq: int
    program_version: str
    trace_id: UUID
    cause: RecoveryCause = "START"
    ttl_seconds: float = 30.0  # every fence renews for this long
    # Monotonic instant the lease is known good until, armed at heartbeat *send* time — the
    # conservative end of the round trip. Worker wall-clock skew is a non-fault for Keel (§8.4).
    valid_until_mono: float = 0.0


@dataclass(slots=True)
class RunRow:
    """The control plane's half of a RunView: lease status plus the phase cache (§5.4)."""

    run_id: RunId
    run_root_id: RunId
    program: str
    program_version: str
    keel_version: str
    phase: str
    trace_id: UUID
    args: Any = None
    budget: Mapping[str, Any] = field(default_factory=dict)
    model_config: Mapping[str, Any] = field(default_factory=dict)
    lease_owner: str | None = None
    lease_epoch: int = 0
    lease_expires_at: datetime | None = None
    runnable_at: datetime | None = None
    runnable_reason: str | None = None
    wake_at: datetime | None = None
    orphaned_at: datetime | None = None
    paused_at: datetime | None = None
    terminal_at: datetime | None = None
    attempt_deadline: datetime | None = None
    created_at: datetime | None = None
    #: Set for a child run. The reaper's liveness rule and the parent's takeover both key on it,
    #: and it is the one thing about a child that its parent may read without a lease (§17.3).
    parent_run_id: RunId | None = None


@dataclass(slots=True)
class DelegationRow:
    """The contract, as a row (§5.5, §17.2). Written only by the parent's holder — at spawn and at
    settlement — so it is a parent-owned projection cache plus contract store; the child never
    touches it. Truth remains the `CHILD_*` events."""

    delegation_id: UUID
    parent_run_id: RunId
    parent_step_index: int
    child_run_id: RunId
    role: str
    contract: dict[str, Any]
    budget_reserved: dict[str, Any]
    status: str = "SPAWNED"  # SPAWNED | COMPLETED | FAILED | CANCELLED
    usage_settled: dict[str, Any] | None = None
    spawned_seq: int = 0
    settled_seq: int | None = None
    child_ordinal: int = 0
    retry_no: int = 0


@dataclass(slots=True)
class EffectRow:
    """The materialised mirror whose primary key turns a double-issued effect into a unique
    violation at INTENT commit — loud, transactional, impossible to skip silently (§5.5)."""

    effect_key: EffectKey
    run_id: RunId
    run_root_id: RunId
    step_index: int
    tool: str
    effect_class: str
    status: EffectStatus
    intent_seq: int
    modifiers: tuple[str, ...] = ()
    attempt_no: int = 0
    started_seq: int | None = None
    outcome_seq: int | None = None
    attempt_deadline: datetime | None = None
    resolution: str | None = None
    external_ref: str | None = None
    synthetic: bool = False


@dataclass(slots=True)
class RecoveryRow:
    run_id: RunId
    lease_epoch: int
    worker_id: str
    cause: RecoveryCause
    from_seq: int
    acquired_at: datetime | None = None
    started_seq: int | None = None
    completed_seq: int | None = None
    completed_at: datetime | None = None
    live_from_step: int | None = None
    replayed_steps: int | None = None
    replay_ms: int | None = None
    outcome: str | None = None
    released_at: datetime | None = None


#: What a `replays` row may say happened. FORK's `SPAWNED` is here because the column is the
#: schema's, not this phase's — the mode is refused at the call, not by omission from the enum.
REPLAY_RESULTS = frozenset(
    {"PASS", "NONDETERMINISM", "PROMPT_DRIFT", "STATE_SCHEMA_MISMATCH", "ERROR", "SPAWNED"}
)


@dataclass(slots=True)
class ReplayRow:
    """The durable record of a pass that wrote nothing else (§5.7).

    VERIFY appends no events by definition, so without this row a verify pass is a log line. CI,
    C1 and `keel replay --verify` all need to be able to ask later what the answer was, and a
    `PROMPT_DRIFT` diff needs somewhere to live that is *not* the journal — drift is a property of
    the pair (journal, reading code), not of the run, and journaling it would make a run's history
    depend on who read it (§6.6).
    """

    replay_id: UUID
    run_id: RunId
    mode: str
    requested_by: str
    program_version: str
    base_seq: int
    result: str | None = None
    fork_run_id: RunId | None = None
    replayed_steps: int | None = None
    elapsed_ms: int | None = None
    projection_hash: str | None = None
    diff_blob_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class SignalRow:
    """One row of the inbox (§5.6): the only path by which anything that is not the lease holder
    influences a run.

    `client_key` is the caller's dedup handle and is UNIQUE per run. The API is at-least-once by
    design — a retried `approve` inserts twice unless the client sets one — and the run's state
    machine, not the insert, is what makes the second one harmless.
    """

    signal_id: SignalId
    run_id: RunId
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    client_key: str | None = None
    source: str = "api:cli"
    created_at: datetime | None = None
    consumed_seq: int | None = None


class AppendTx(Protocol):
    """One fenced append transaction: the fence UPDATE has already run as its first statement."""

    async def now(self) -> datetime:
        """Postgres `now()` — the transaction start time. Never a worker clock (§5.3)."""
        ...

    async def append(self, body: Any, *, causation_seq: int | None = None) -> int: ...

    async def write_effect(self, row: EffectRow) -> None: ...

    async def update_effect(self, effect_key: EffectKey, **fields: Any) -> None: ...

    async def set_run(self, **fields: Any) -> None: ...

    async def consume_signal(self, signal_id: SignalId, seq: int) -> None:
        """`UPDATE signals SET consumed_seq = $seq WHERE signal_id = $s AND consumed_seq IS NULL`.

        In *this* transaction, with the event that records what was done about it. That co-commit
        is the whole guarantee of the inbox: a signal cannot be applied without being consumed, and
        cannot be consumed without the journal saying so. It is the same same-database-transaction
        argument that gives TRANSACTIONAL tools theirs (§5.6).
        """
        ...

    async def insert_signal(self, row: SignalRow) -> None:
        """An inbox row for *another* run, in this transaction (§5.10).

        The child's terminal event and its parent's `child_result` row commit together, so a child
        cannot become terminal and die before notifying — the L1 hole a same-database design
        closes for free. The parent's CANCEL_ACKNOWLEDGED inserts a `cancel` per non-terminal child
        the same way. Not a foreign append: the constitution names child workers as inbox writers.
        """
        ...

    async def create_child(self, row: RunRow, created: Any, delegation: DelegationRow) -> None:
        """The child's `runs` row, its RUN_CREATED at `lease_epoch = 0`, and its `delegations` row —
        inside the parent's fenced transaction, beside the parent's CHILD_SPAWNED.

        Creation is not a foreign append; it is the birth of the child's journal, and no lease on
        it can exist yet. Committing the four together is what makes "the parent says it spawned"
        and "the child exists" one fact rather than two that a crash could separate (§7.6.1).
        """
        ...

    async def settle_delegation(
        self, delegation_id: UUID, *, status: str, usage_settled: dict[str, Any] | None, settled_seq: int
    ) -> None:
        """The parent-owned projection cache, updated in the same transaction as CHILD_COMPLETED /
        CHILD_FAILED. Truth is the event; this is what `keel show` and the reaper read."""
        ...


class BlobStore(Protocol):
    async def put(self, data: bytes, *, media_type: str = "application/json") -> str: ...

    async def get(self, blob_id: str) -> bytes: ...


class JournalBackend(Protocol):
    async def migrate(self) -> None: ...

    async def register_program(
        self,
        *,
        program: str,
        program_version: str,
        declared_version: str,
        code_hash: str,
        entrypoint: str,
        keel_version: str,
        tools: Mapping[str, Any],
    ) -> None: ...

    async def create_run(self, row: RunRow, created: Any, *, runnable_at: datetime | None) -> None:
        """The one append with no fence: the `runs` row and RUN_CREATED are INSERTed together at
        lease_epoch = 0, so there is no prior writer to fence out (§23.4)."""
        ...

    async def claim(self, worker_id: str, ttl: timedelta) -> Lease | None: ...

    async def acquire(self, run_id: RunId, worker_id: str, ttl: timedelta) -> Lease | None: ...

    def append(self, lease: Lease) -> AbstractAsyncContextManager[AppendTx]: ...

    async def heartbeat(self, lease: Lease, ttl: timedelta) -> bool: ...

    async def release(
        self,
        lease: Lease,
        *,
        runnable_at: datetime | None = None,
        wake_at: datetime | None = None,
        phase: str | None = None,
        runnable_reason: str | None = None,
    ) -> None: ...

    async def read(self, run_id: RunId, *, from_seq: int = 0) -> list[Event]: ...

    def tail(self, run_id: RunId, *, from_seq: int = 0) -> AsyncIterator[Event]: ...

    async def run_row(self, run_id: RunId) -> RunRow | None: ...

    async def list_runs(self, *, phase: str | None = None, limit: int = 50) -> list[RunRow]: ...

    async def effects(self, run_id: RunId) -> list[EffectRow]: ...

    async def recoveries(self, run_id: RunId) -> list[RecoveryRow]: ...

    async def set_recovery(self, run_id: RunId, lease_epoch: int, **fields: Any) -> None: ...

    async def reap(self) -> list[RunId]: ...

    async def insert_signal(self, row: SignalRow) -> bool:
        """Put a signal in the inbox and make the run claimable. False when `client_key` already
        exists for this run — the caller's retry, deduplicated by the one index that can do it.

        Never writes `events`: the inbox is how a non-holder influences a run precisely because it
        does not need the lease (§4.10). What the signal *means* is decided at the drain, by the
        holder, from the run's state at that moment — an approval inserted against a run that
        terminates first is simply never drained.
        """
        ...

    async def pending_signals(self, run_id: RunId) -> list[SignalRow]:
        """Unconsumed rows, in application order `(created_at, signal_id)` (§4.10)."""
        ...

    async def sweep_timers(self) -> int:
        """Fire every due `wake_at`: insert one `timer` signal per run and make it runnable.

        The other half of the zero-tick park. A parked run has `runnable_at IS NULL`, so nothing
        polls it — this is what brings it back when its deadline passes rather than when someone
        asks. `client_key = 'timer:<wake_at>'` so two schedulers firing the same deadline produce
        one row (§5.6), which is also why this can run on every worker without coordination.
        """
        ...

    # --- delegation (§17) ------------------------------------------------------
    async def children(self, parent_run_id: RunId) -> list[RunRow]:
        """A parent may read its children's *control-plane* rows — never their journals (§17.3)."""
        ...

    async def delegations(self, parent_run_id: RunId) -> list[DelegationRow]: ...

    async def stray_children(self) -> list[RunRow]:
        """The reaper's liveness predicate (§17.7): `child.terminal_at IS NULL AND
        parent.terminal_at IS NOT NULL`. A child cannot outlive its parent's terminal state; the
        reaper cancels each stray and takes its lease over after `cancel_grace`. S8 measures what
        slips through."""
        ...

    async def takeover(
        self,
        child_run_id: RunId,
        worker_id: str,
        ttl: timedelta,
        *,
        cancel_grace: timedelta,
    ) -> Lease | None:
        """The forced-cancel acquisition of §7.6.2 / §17.7: the fifth control-plane statement, and
        the only one that moves a lease its holder still believes it has.

            UPDATE runs SET lease_epoch = lease_epoch + 1, lease_owner = $w, lease_expires_at = now() + $ttl
             WHERE run_id = $child AND lease_epoch = $observed AND terminal_at IS NULL
               AND EXISTS (cancel signal for $child older than $cancel_grace)
               AND (attempt_deadline IS NULL OR attempt_deadline < now())

        Three things are in that WHERE on purpose. The epoch is pinned so the read and the move
        cannot straddle a heartbeat. The cancel row must exist and be older than the grace, judged
        by the *store's* clock: the child was told, and had its chance to acknowledge at a step
        boundary. And an open non-PURE attempt's deadline is honoured — the same bound the reaper
        applies — so a takeover can never jump a request that could still commit. `None` for any
        of the three: the caller re-parks and asks again after the grace.

        A takeover *is* a lease acquisition: `RECOVERY_STARTED{cause=ORPHANED, forced_by}` is the
        new epoch's first append, the `recoveries` row is inserted here, and no new cause exists.
        """
        ...

    async def record_replay(self, row: ReplayRow) -> None: ...

    async def replays(self, run_id: RunId) -> list[ReplayRow]: ...

    async def resolve_run_id(self, prefix: str) -> RunId | None: ...

    async def close(self) -> None: ...
