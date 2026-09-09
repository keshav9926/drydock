"""The discriminated union of every event body (§6.2).

MVP rows only (§27.4): run core, run suspension, step core, step ambiguity. The rest arrive with
their mechanisms — a body added later is a new member of this union and a new CURRENT entry, never
a rewrite of a stored row.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Body(BaseModel):
    model_config = ConfigDict(frozen=True)


class BlobRef(BaseModel):
    """Replaces any field whose serialised size exceeds 32 KiB (§6.1)."""

    model_config = ConfigDict(frozen=True)
    blob_id: str
    media_type: str = "application/json"
    size_bytes: int


# --- run core ----------------------------------------------------------------
class RunCreated(Body):
    type: Literal["RUN_CREATED"] = "RUN_CREATED"
    program: str
    program_version: str
    args: Any = None
    budget: dict[str, Any] = Field(default_factory=dict)
    model_config_: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    parent_run_id: UUID | None = None
    delegation_id: UUID | None = None
    fork_of: dict[str, Any] | None = None


class RecoveryStarted(Body):
    """First append after any lease acquisition. Recovery is not a special path (§1)."""

    type: Literal["RECOVERY_STARTED"] = "RECOVERY_STARTED"
    lease_epoch: int
    cause: Literal["START", "WAKE", "ORPHANED", "RESUME", "DRAIN", "VERIFY"]
    from_seq: int
    from_segment: int = 0


class RecoveryCompleted(Body):
    type: Literal["RECOVERY_COMPLETED"] = "RECOVERY_COMPLETED"
    live_from_step: int
    replayed_steps: int
    elapsed_ms: int


class RunCompleted(Body):
    type: Literal["RUN_COMPLETED"] = "RUN_COMPLETED"
    result: Any = None


class RunFailed(Body):
    type: Literal["RUN_FAILED"] = "RUN_FAILED"
    error: str
    step_index: int | None = None


class RunSuspended(Body):
    type: Literal["RUN_SUSPENDED"] = "RUN_SUSPENDED"
    reason: str  # MVP: nondeterminism | resolved_unknown
    detail: Any = None


# --- step core ---------------------------------------------------------------
class StepIntended(Body):
    type: Literal["STEP_INTENDED"] = "STEP_INTENDED"
    step_index: int
    kind: str
    name: str
    args_hash: str | None = None
    args: Any = None
    request_hash: str | None = None
    effect_key: str | None = None
    effect_class: str | None = None
    modifiers: tuple[str, ...] = ()
    policy_verdict: str = "allow"
    program_version: str = ""


class StepAttemptStarted(Body):
    """The attempt's write-ahead barrier: no effect may begin before this is durably committed."""

    type: Literal["STEP_ATTEMPT_STARTED"] = "STEP_ATTEMPT_STARTED"
    step_index: int
    attempt_no: int
    lease_epoch: int
    started_at: AwareDatetime
    attempt_deadline: AwareDatetime | None = None
    reservation: int | None = None


class StepCompleted(Body):
    type: Literal["STEP_COMPLETED"] = "STEP_COMPLETED"
    step_index: int
    attempt_no: int
    result: Any = None
    usage: dict[str, int] | None = None
    provider_meta: dict[str, Any] | None = None
    synthetic: bool = False


class StepFailed(Body):
    type: Literal["STEP_FAILED"] = "STEP_FAILED"
    step_index: int
    attempt_no: int
    error: str
    retryable: bool = False
    next_attempt_at: AwareDatetime | None = None


class StepAmbiguous(Body):
    """STARTED with no outcome, class EXTERNAL — or an EXTERNAL timeout. A state, not a guarantee."""

    type: Literal["STEP_AMBIGUOUS"] = "STEP_AMBIGUOUS"
    step_index: int
    attempt_no: int
    cause: str


class StepResolved(Body):
    """The memo of an ambiguous step — not a later STEP_COMPLETED (§6.2)."""

    type: Literal["STEP_RESOLVED"] = "STEP_RESOLVED"
    step_index: int
    attempt_no: int
    resolution: Literal["RESOLVED_COMPLETED", "RESOLVED_FAILED", "RESOLVED_UNKNOWN"]
    method: Literal["probe", "assume_failed", "assume_succeeded", "escalate", "human"]
    evidence: dict[str, Any] = Field(default_factory=dict)


EventBody = Annotated[
    RunCreated
    | RecoveryStarted
    | RecoveryCompleted
    | RunCompleted
    | RunFailed
    | RunSuspended
    | StepIntended
    | StepAttemptStarted
    | StepCompleted
    | StepFailed
    | StepAmbiguous
    | StepResolved,
    Field(discriminator="type"),
]

TERMINAL_TYPES = frozenset({"RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED"})
OUTCOME_TYPES = frozenset({"STEP_COMPLETED", "STEP_FAILED", "STEP_AMBIGUOUS"})
