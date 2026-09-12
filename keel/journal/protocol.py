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

from keel.core.ids import EffectKey, RunId
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


class AppendTx(Protocol):
    """One fenced append transaction: the fence UPDATE has already run as its first statement."""

    async def now(self) -> datetime:
        """Postgres `now()` — the transaction start time. Never a worker clock (§5.3)."""
        ...

    async def append(self, body: Any, *, causation_seq: int | None = None) -> int: ...

    async def write_effect(self, row: EffectRow) -> None: ...

    async def update_effect(self, effect_key: EffectKey, **fields: Any) -> None: ...

    async def set_run(self, **fields: Any) -> None: ...


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

    async def mark_runnable(self, run_id: RunId, reason: str = "RESUME") -> bool:
        """MVP `keel resume`: a direct conditional UPDATE of runs.runnable_at. An explicitly
        temporary second control path, *replaced* by the signals inbox at v1 (§27.2, 4.10)."""
        ...

    async def record_replay(self, row: ReplayRow) -> None: ...

    async def replays(self, run_id: RunId) -> list[ReplayRow]: ...

    async def resolve_run_id(self, prefix: str) -> RunId | None: ...

    async def close(self) -> None: ...
