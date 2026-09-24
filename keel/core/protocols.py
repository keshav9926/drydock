"""The inversion point (§23.2).

`keel.runtime` must not import `effects`, `approvals` or `orchestration`; those packages register a
`StepExecutor` for their kinds into `runtime.steps.EXECUTORS` at import time. Everything the three
sides need to agree on lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

from keel.core.clock import Clock
from keel.core.ids import EffectKey, RunId


class StepKind(StrEnum):
    MODEL = "MODEL"
    TOOL = "TOOL"
    APPROVAL = "APPROVAL"
    DELEGATE = "DELEGATE"
    SLEEP = "SLEEP"
    SIGNAL_WAIT = "SIGNAL_WAIT"
    NOW = "NOW"
    RANDOM = "RANDOM"
    COMPACT = "COMPACT"
    PLAN = "PLAN"


#: `create_issue.compensate` is the TOOL step that runs `create_issue`'s compensate hook (§9.5).
COMPENSATE = ".compensate"


def capability(name: str) -> str:
    """The capability a tool call needs: a compensating action needs its own tool's, so an undo is
    allowed exactly where the effect it undoes was."""
    return name.removesuffix(COMPENSATE)


class EffectClass(StrEnum):
    """Exactly one per tool, mutually exclusive; the class alone decides retry, replay and
    recovery of the effect (§3)."""

    PURE = "PURE"
    IDEMPOTENT = "IDEMPOTENT"
    EXTERNAL = "EXTERNAL"
    TRANSACTIONAL = "TRANSACTIONAL"


class Modifier(StrEnum):
    """Composes with a class; not a class (§3)."""

    STREAMS = "STREAMS"
    LOCAL_FS = "LOCAL_FS"


class Idempotency(StrEnum):
    """What the *receiver* honours — a property of the receiver, not of the caller (§9)."""

    NONE = "NONE"
    KEY = "KEY"
    NATURAL = "NATURAL"


Resolution = Literal["probe", "assume_failed", "assume_succeeded", "escalate"]


@dataclass(frozen=True, slots=True)
class StepIntent:
    """What is committed as STEP_INTENDED, and what per-kind identity is compared against (§1)."""

    step_index: int
    kind: StepKind
    name: str
    args: Any = None
    args_hash: str | None = None
    request_hash: str | None = None
    effect_key: EffectKey | None = None
    effect_class: EffectClass | None = None
    modifiers: tuple[Modifier, ...] = ()
    program_version: str = ""
    #: §20.2: the Policy's answer at step entry, journaled on the INTENT so replay reads it and never
    #: the live Policy. Not identity. `policy_error` is what a `deny` refuses with (PolicyDenied or
    #: PolicyTimeout) — the STEP_FAILED{attempt_no=0} text, never journaled on the INTENT itself.
    policy_verdict: str = "allow"
    policy_error: str | None = None

    def identity(self) -> tuple:
        """Per-kind intent identity (§1). MODEL compares (kind, name) only, so a prompt edit does
        not suspend a run parked on an approval; everything else compares the args hash too."""
        if self.kind in (StepKind.MODEL, StepKind.COMPACT):
            return (str(self.kind), self.name)
        return (str(self.kind), self.name, self.args_hash)


@dataclass(frozen=True, slots=True)
class Completed:
    result: Any
    usage: dict[str, int] | None = None
    provider_meta: dict[str, Any] | None = None
    external_ref: str | None = None


@dataclass(frozen=True, slots=True)
class Failed:
    error: str
    retryable: bool = False
    #: The request may have been applied: a timeout, or a receiver that failed to answer. Only an
    #: IDEMPOTENT step acts on it — a retry under the same key resolves it; no retry leaves it unknown.
    unknown: bool = False


@dataclass(frozen=True, slots=True)
class Ambiguous:
    cause: str


StepOutcome = Completed | Failed | Ambiguous


@dataclass(slots=True)
class StepCtx:
    """What a StepExecutor is handed for one attempt. `provider` and `tools` are typed `Any`
    because `core` sits below both packages that supply them (§23.2)."""

    run_id: RunId
    run_root_id: RunId
    attempt_no: int
    clock: Clock
    deadline: datetime | None = None
    effect_key: EffectKey | None = None
    provider: Any = None
    tools: Any = None
    hooks: Any = None
    resources: dict[str, Any] = field(default_factory=dict)
    #: A STREAMS attempt's chunk sink, `await emit(piece, usage_cum=None)`; None without STREAMS.
    emit: Any = None
    #: A LOCAL_FS tool's per-epoch checkout (`runtime/sandbox.py`, §20.5); None without a Sandbox.
    workspace: Any = None


@runtime_checkable
class StepExecutor(Protocol):
    kind: StepKind

    async def execute(self, intent: StepIntent, sctx: StepCtx) -> StepOutcome: ...


class ProbeResult:
    """A probe's verdict, plus the result the killed attempt never received when the receiver can
    genuinely be read back; `result=None` makes the runtime materialise the declared sentinel (§23.4)."""

    __slots__ = ("verdict", "evidence", "result", "external_ref")

    def __init__(
        self,
        verdict: Literal["COMMITTED", "ABSENT", "UNKNOWN"],
        evidence: str,
        result: Any = None,
        external_ref: str | None = None,
    ) -> None:
        self.verdict = verdict
        self.evidence = evidence
        self.result = result
        self.external_ref = external_ref


@runtime_checkable
class Tool(Protocol):
    name: str
    effect_class: EffectClass
    modifiers: frozenset[Modifier]
    partial_ok: bool
    timeout: float
    resolution: Resolution
    idempotency: Idempotency
    secrets: tuple[str, ...]

    async def run(self, args: Any, tctx: Any) -> Any: ...


class Policy(Protocol):
    """§20.2, §23.4. Consulted at a live TOOL step's entry, before its index is consumed; `run` is
    the run's `RunState` as the journal has it at that moment. Implementations: `runtime/policy.py`."""

    async def pre_step(
        self, intent: StepIntent, run: Any
    ) -> Literal["allow", "deny", "require_approval"]: ...
