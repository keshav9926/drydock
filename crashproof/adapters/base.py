"""What a runtime has to expose to be measured, and what it has to declare about itself (§13.3).

Adapters are thin, and the thinness is the finding. An adapter expresses the canonical workload in
its framework's *documented* primitives and adds no counter, no pre-send lookup, no retry and no
dedup. If the framework re-fires, the World sees it. An adapter that quietly helps its framework
destroys the result more thoroughly than one that hurts it.

Two declarations decide how a trial is read:

`claims` — what the runtime says it guarantees per effect class. A verdict is judged against the
claim, not against a fixed bar: an adapter that declares `at_least_once` and produces a duplicate
has not failed S1, and the raw duplicate is published anyway. This is the Jepsen rule.

`recovery_mechanism` — *who noticed*. `self` (the restarted process scans its own store), `engine`
(a server re-drives it) or `harness` (the supervisor re-invokes it by an id it kept). It is a
column of the matrix and a headline finding in its own right, never a detail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

Claim = Literal["none", "at_most_once", "at_least_once", "effectively_once", "exactly_once"]
RecoveryMechanism = Literal["engine", "self", "harness"]
KeySource = Literal["none", "framework", "adapter"]
Status = Literal["COMPLETED", "FAILED", "CANCELLED", "WAITING", "SUSPENDED", "UNKNOWN"]


@dataclass(slots=True)
class ConfigPin:
    """Everything that would change a number, hashed into every row. An unpinned trial is
    unpublishable — not because pinning is tidy, but because "Keel recovers faster" is a claim
    about timeouts unless both arms' timeouts are printed beside it."""

    framework_versions: dict[str, str] = field(default_factory=dict)
    backend: str = ""
    durability: str = ""
    lease_ttl_s: float | None = None
    tool_timeout_s: float | None = None
    heartbeat_s: float | None = None
    retry: str = "none"
    worker_count: int = 1
    pause_ms: float | None = None
    successor_start_delay_s: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return {k: v for k, v in asdict(self).items() if v not in (None, "", {}, [])}


@dataclass(slots=True)
class Dependency:
    """The SUT's own store, started per trial by the adapter that owns it. Keel gets a cloned
    Postgres database; Temporal would get a dev server. The harness owns the World, never this."""

    name: str
    dsn: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    teardown: Any = None


@dataclass(slots=True)
class SutHandle:
    """What the supervisor holds between spawns. Never a run id passed on a command line: a
    runtime that has to be *told* which run to resume is `recovery_mechanism = harness`, and it is
    told only through `on_worker_restart`."""

    trial_dir: Path
    dependency: Dependency
    world_url: str
    run_ref: str | None = None


@dataclass(slots=True)
class CanonicalResult:
    """One trial's outcome in runtime-neutral terms.

    Missing inputs are named individually, never bundled: `committed_effects = None` makes S2 and
    C3 N/A, and no per-attempt STARTED with timestamps makes S4 N/A. A runtime can supply one and
    not the other, so the two N/As are reported separately (§15.11).
    """

    status: Status = "UNKNOWN"
    result: Any = None
    committed_effects: set[str] | None = None
    export: Path | None = None
    steps: int | None = None
    model_calls: int | None = None
    tokens: int | None = None
    recoveries: list[dict[str, Any]] = field(default_factory=list)
    detect_ms: float | None = None
    storage_bytes: int | None = None


class RuntimeAdapter(Protocol):
    name: str
    claims: dict[str, Claim]
    recovery_mechanism: RecoveryMechanism
    key_sources: frozenset[str]
    workloads: frozenset[str]
    workload_evidence: dict[str, str]

    def config_pin(self, **kwargs: Any) -> ConfigPin: ...

    def worker_count(self, spec: Any) -> int: ...

    async def start_dependency(self, handle: SutHandle) -> Dependency: ...

    def worker_argv(self, handle: SutHandle) -> list[str]:
        """A pure function of the trial directory, restarted verbatim. Never a run or thread id."""
        ...

    def worker_env(self, handle: SutHandle) -> dict[str, str]: ...

    async def submit(self, handle: SutHandle) -> None:
        """Called once per trial. The only moment a run id may be handed to the SUT."""
        ...

    async def on_worker_restart(self, handle: SutHandle) -> None:
        """`engine` and `self` runtimes: a no-op. `harness` runtimes: nudge by an id the framework
        itself persisted, re-read from the trial directory — never from process memory."""
        ...

    async def collect(self, handle: SutHandle) -> CanonicalResult: ...

    async def stop_dependency(self, handle: SutHandle) -> None: ...
