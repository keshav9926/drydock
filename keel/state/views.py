"""Read models the API, CLI and TUI use: journal phase ∪ lease status (§24.1, §6.6).

A run can be WAITING_APPROVAL (journal) and ORPHANED (control plane) at once, and both are true —
so the view carries both rather than collapsing them into one word.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from keel.journal.protocol import EffectRow, RunRow
from keel.state.fold import RunState


@dataclass(slots=True)
class StepView:
    step_index: int
    kind: str
    name: str
    state: str
    attempts: int
    origin: str
    effect_key: str | None = None
    effect_class: str | None = None
    intent_seq: int | None = None
    outcome_seq: int | None = None
    result: Any = None
    error: str | None = None


@dataclass(slots=True)
class RunView:
    run_id: UUID
    run_root_id: UUID
    program: str
    program_version: str
    phase: str
    control_status: str | None  # None | ORPHANED | RECOVERING
    lease_owner: str | None
    lease_epoch: int
    lease_expires_at: datetime | None
    last_seq: int
    projection_hash: str
    steps: list[StepView] = field(default_factory=list)
    effects: list[EffectRow] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    suspended_reason: str | None = None
    epochs: list[int] = field(default_factory=list)
    live_from_step: dict[int, int] = field(default_factory=dict)


@dataclass(slots=True)
class RunSummary:
    run_id: UUID
    program: str
    phase: str
    control_status: str | None
    lease_epoch: int
    created_at: datetime | None


def control_status(row: RunRow, state: RunState, now: datetime) -> str | None:
    """ORPHANED and RECOVERING are control-plane statuses, not events (§6.6)."""
    if row.orphaned_at is not None:
        return "ORPHANED"
    live = row.lease_expires_at is not None and row.lease_expires_at >= now
    if live and state.recovery_open:
        return "RECOVERING"
    return None


def run_view(row: RunRow, state: RunState, now: datetime, effects: list[EffectRow] | None = None) -> RunView:
    epoch = state.latest_epoch
    return RunView(
        run_id=row.run_id,
        run_root_id=row.run_root_id,
        program=row.program,
        program_version=row.program_version,
        phase=row.phase if state.phase == "CREATED" else state.phase,
        control_status=control_status(row, state, now),
        lease_owner=row.lease_owner,
        lease_epoch=row.lease_epoch,
        lease_expires_at=row.lease_expires_at,
        last_seq=state.last_seq,
        projection_hash=state.projection_hash(),
        steps=[
            StepView(
                step_index=s.step_index,
                kind=s.kind,
                name=s.name,
                state=s.state,
                attempts=s.attempts,
                origin=state.origin(s.step_index, epoch),
                effect_key=s.effect_key,
                effect_class=s.effect_class,
                intent_seq=s.intent_seq,
                outcome_seq=s.outcome_seq,
                result=s.result,
                error=s.error,
            )
            for s in sorted(state.steps.values(), key=lambda s: s.step_index)
        ],
        effects=effects or [],
        result=state.result,
        error=state.error,
        suspended_reason=state.suspended_reason,
        epochs=list(state.epochs),
        live_from_step=dict(state.live_from_step),
    )


def run_summary(row: RunRow, state: RunState, now: datetime) -> RunSummary:
    return RunSummary(
        run_id=row.run_id,
        program=row.program,
        phase=row.phase,
        control_status=control_status(row, state, now),
        lease_epoch=row.lease_epoch,
        created_at=row.created_at,
    )
