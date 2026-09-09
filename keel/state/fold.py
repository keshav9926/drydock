"""The fold. All run state is a pure fold over events; a projection bug is fixed by re-folding,
never by editing events (§4).

This module has no I/O imports — VERIFY, the CLI and the TUI fold the same code (§23.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from keel.core.hashing import projection_hash as _hash
from keel.events import Event

# step states (§7.3); the `effects` mirror uses its own vocabulary (INTENDED/STARTED/COMMITTED/…)
INTENDED = "INTENDED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
AMBIGUOUS = "AMBIGUOUS"
CANCELLED = "CANCELLED"
RESOLVED_COMPLETED = "RESOLVED_COMPLETED"
RESOLVED_FAILED = "RESOLVED_FAILED"
RESOLVED_UNKNOWN = "RESOLVED_UNKNOWN"

_SETTLED = frozenset({COMPLETED, FAILED, CANCELLED, RESOLVED_COMPLETED, RESOLVED_FAILED})


@dataclass(slots=True)
class StepState:
    step_index: int
    kind: str
    name: str
    state: str
    intent_seq: int
    intent_epoch: int
    args_hash: str | None = None
    request_hash: str | None = None
    effect_key: str | None = None
    effect_class: str | None = None
    attempts: int = 0
    outcome_seq: int | None = None
    outcome_epoch: int | None = None
    result: Any = None
    error: str | None = None
    retryable: bool = False
    resolution: str | None = None
    method: str | None = None

    @property
    def settled(self) -> bool:
        """Has this step a value the program can be handed without executing anything?"""
        return self.state in _SETTLED

    def identity(self) -> tuple:
        """Per-kind intent identity (§1): MODEL compares (kind, name); the rest add the args hash."""
        if self.kind in ("MODEL", "COMPACT"):
            return (self.kind, self.name)
        return (self.kind, self.name, self.args_hash)


@dataclass(slots=True)
class RunState:
    run_id: UUID | None = None
    program: str = ""
    program_version: str = ""
    phase: str = "CREATED"
    args: Any = None
    result: Any = None
    error: str | None = None
    suspended_reason: str | None = None
    suspended_detail: Any = None
    last_seq: int = 0
    steps: dict[int, StepState] = field(default_factory=dict)
    epochs: list[int] = field(default_factory=list)
    live_from_step: dict[int, int] = field(default_factory=dict)
    recovery_cause: dict[int, str] = field(default_factory=dict)
    recovery_open: bool = False

    # --- what re-execution asks -------------------------------------------
    def step(self, step_index: int) -> StepState | None:
        return self.steps.get(step_index)

    @property
    def next_step_index(self) -> int:
        return max(self.steps, default=-1) + 1

    @property
    def open_step(self) -> StepState | None:
        """At most one step lacks an outcome at a crash (steps are strictly sequential, §1)."""
        for s in self.steps.values():
            if not s.settled and s.state != RESOLVED_UNKNOWN:
                return s
        return None

    @property
    def latest_epoch(self) -> int:
        return self.epochs[-1] if self.epochs else 0

    @property
    def terminal(self) -> bool:
        return self.phase in ("COMPLETED", "FAILED", "CANCELLED", "SUPERSEDED")

    def origin(self, step_index: int, epoch: int | None = None) -> str:
        """memo | recovered | live, computed against an epoch — a property of the STEP (§25.4)."""
        epoch = self.latest_epoch if epoch is None else epoch
        s = self.steps.get(step_index)
        if s is None:
            return "-"
        live_from = self.live_from_step.get(epoch)
        if live_from is not None and step_index >= live_from:
            return "live"
        if s.outcome_epoch == epoch:
            return "recovered"
        return "memo"

    def projection_hash(self) -> str:
        """Raw projection hash: sha256(canonical_json(RunState)) — the MVP form of §4.5."""
        return _hash(
            {
                "phase": self.phase,
                "result": self.result,
                "error": self.error,
                "steps": [
                    {
                        "i": s.step_index,
                        "kind": s.kind,
                        "name": s.name,
                        "state": s.state,
                        "args_hash": s.args_hash,
                        "effect_key": s.effect_key,
                        "result": s.result,
                        "error": s.error,
                    }
                    for s in sorted(self.steps.values(), key=lambda s: s.step_index)
                ],
            }
        )


def fold(events: list[Event]) -> RunState:
    st = RunState()
    for ev in events:
        _apply(st, ev)
        st.last_seq = ev.seq
    return st


def _apply(st: RunState, ev: Event) -> None:  # noqa: C901 - one dispatch, deliberately flat
    b = ev.body
    t = ev.type
    if t == "RUN_CREATED":
        st.run_id = ev.run_id
        st.program = b.program
        st.program_version = b.program_version
        st.args = b.args
        st.phase = "CREATED"
    elif t == "RECOVERY_STARTED":
        st.epochs.append(b.lease_epoch)
        st.recovery_cause[b.lease_epoch] = b.cause
        st.recovery_open = True
        if not st.terminal:
            st.phase = "RUNNING"
    elif t == "RECOVERY_COMPLETED":
        st.live_from_step[ev.lease_epoch] = b.live_from_step
        st.recovery_open = False
    elif t == "RUN_COMPLETED":
        st.phase = "COMPLETED"
        st.result = b.result
    elif t == "RUN_FAILED":
        st.phase = "FAILED"
        st.error = b.error
    elif t == "RUN_SUSPENDED":
        st.phase = "SUSPENDED"
        st.suspended_reason = b.reason
        st.suspended_detail = b.detail
    elif t == "STEP_INTENDED":
        st.steps[b.step_index] = StepState(
            step_index=b.step_index,
            kind=b.kind,
            name=b.name,
            state=INTENDED,
            intent_seq=ev.seq,
            intent_epoch=ev.lease_epoch,
            args_hash=b.args_hash,
            request_hash=b.request_hash,
            effect_key=b.effect_key,
            effect_class=b.effect_class,
        )
    elif t == "STEP_ATTEMPT_STARTED":
        s = st.steps[b.step_index]
        s.state = RUNNING
        s.attempts = b.attempt_no
    elif t == "STEP_COMPLETED":
        s = st.steps[b.step_index]
        s.state = COMPLETED
        s.result = b.result
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
    elif t == "STEP_FAILED":
        s = st.steps[b.step_index]
        s.state = FAILED
        s.error = b.error
        s.retryable = b.retryable
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
    elif t == "STEP_AMBIGUOUS":
        s = st.steps[b.step_index]
        s.state = AMBIGUOUS
        s.error = b.cause
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
    elif t == "STEP_RESOLVED":
        s = st.steps[b.step_index]
        s.state = b.resolution
        s.resolution = b.resolution
        s.method = b.method
        s.outcome_seq = ev.seq
        s.outcome_epoch = ev.lease_epoch
        if b.resolution == RESOLVED_COMPLETED:
            s.result = b.evidence.get("result")
        elif b.resolution == RESOLVED_FAILED:
            s.error = b.evidence.get("evidence") or "resolved failed"
