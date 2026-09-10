"""The fault spec: what to break, and where (§11.3).

A spec names faults by *landmark* — a logical point in the canonical workload that every runtime
reaches — never by an ordinal in one runtime's traffic. `tool:create_issue` is somewhere every arm
goes; "the third HTTP request" is a statement about a framework's chattiness. That distinction is
what lets one spec run unchanged against every adapter in a cell, which is the publication rule.

`seed` is deliberately absent. It is supplied per trial, so `(spec_hash, seed)` is simultaneously
the reproduction key and the pairing key for `compare`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["hook", "shim", "proxy"]

#: Boundaries a `shim` fires at — runtime-neutral, and the same three instants in every SUT.
SHIM_BOUNDARIES = (
    "before:tool_call",
    "after:tool_effect",
    "after:tool_return",
    "before:model_call",
    "after:model_return",
)
#: `supervisor` is the one boundary that is not in the SUT: the harness executes it from outside.
BOUNDARIES = (*SHIM_BOUNDARIES, "supervisor")

#: Fault types that end the process, so the supervisor must have restarts left for them.
RESTART_CAUSING = frozenset({"kill", "sigterm_grace_ok", "sigterm_grace_too_short", "pause_past_ttl"})

#: What the MVP shim can actually do. A spec naming anything else is refused at load, loudly,
#: rather than producing a trial that quietly never fires.
MVP_FAULT_TYPES = frozenset({"kill", "pause_past_ttl"})


class CrashproofSpecError(Exception):
    """A spec or schedule error. Never a Keel error — the harness is at fault, not the runtime."""


class UnreachableTrigger(CrashproofSpecError):
    def __init__(self, fault_id: str, occurrence: int, bound: int) -> None:
        super().__init__(
            f"fault {fault_id!r}: occurrence {occurrence} exceeds the reachable bound {bound}; "
            "a trigger that can never fire is a spec error, not a trial that scores zero"
        )


class ScheduleExceedsRecoveries(CrashproofSpecError):
    def __init__(self, fault_id: str, fires: int, max_recoveries: int) -> None:
        super().__init__(
            f"fault {fault_id!r}: {fires} restart-causing firings with max_recoveries="
            f"{max_recoveries}; the supervisor would stop before the schedule finished"
        )


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Trigger(Frozen):
    """Where a fault fires, addressed by history alone.

    No wall clock, PID, port or hostname enters the decision — `delay_ms` is the only time-shaped
    input, and it is a value drawn at expansion applied *after* a history-defined observation.
    """

    boundary: str
    landmark: str
    occurrence: int = 1
    recovery_index: int | None = None
    delay_ms: int = 0

    def model_post_init(self, _: Any) -> None:
        if self.boundary not in BOUNDARIES:
            raise CrashproofSpecError(f"unknown boundary {self.boundary!r}; one of {BOUNDARIES}")
        if self.occurrence < 1:
            raise CrashproofSpecError("occurrence is 1-based")


class Fault(Frozen):
    id: str
    type: str
    trigger: Trigger
    params: dict[str, Any] = Field(default_factory=dict)
    probability: float | None = None
    count: int = 1
    every: bool = False

    def model_post_init(self, _: Any) -> None:
        if self.probability is not None and not 0 < self.probability <= 1:
            raise CrashproofSpecError(f"fault {self.id!r}: probability must be in (0, 1]")
        if self.count < 1:
            raise CrashproofSpecError(f"fault {self.id!r}: count must be >= 1")


class FaultSpec(Frozen):
    spec_version: int = 1
    name: str
    workload: str
    workload_variant: str | None = None
    mode: Mode = "shim"
    max_recoveries: int = 3
    timeout: float = 120.0
    faults: tuple[Fault, ...] = ()
    spec_hash: str = ""

    def model_post_init(self, _: Any) -> None:
        if self.mode != "shim":
            raise CrashproofSpecError(
                f"mode {self.mode!r} is not built: `hook` is phase 6 and `proxy` is week 2 (§27.7)"
            )
        for f in self.faults:
            if f.type not in MVP_FAULT_TYPES:
                raise CrashproofSpecError(
                    f"fault {f.id!r}: type {f.type!r} is not built; the shim fires "
                    f"{sorted(MVP_FAULT_TYPES)} (§27.7 stages the rest)"
                )
            if f.trigger.boundary not in SHIM_BOUNDARIES and f.trigger.boundary != "supervisor":
                raise CrashproofSpecError(f"fault {f.id!r}: {f.trigger.boundary} is not a shim boundary")

    @property
    def is_baseline(self) -> bool:
        """A no-fault spec. The baseline cells are what make every delta metric computable, so
        `faults: []` is a first-class spec rather than a missing one."""
        return not self.faults


def spec_hash(doc: dict[str, Any]) -> str:
    """Identity is the canonical document, not the name — two specs that differ anywhere are
    different specs, and the hash is what a published row cites."""
    body = {k: v for k, v in doc.items() if k != "spec_hash"}
    canonical = yaml.safe_dump(body, sort_keys=True, default_flow_style=False, allow_unicode=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load(path: Path | str) -> FaultSpec:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf8")) or {}
    return from_doc(doc)


def from_doc(doc: dict[str, Any]) -> FaultSpec:
    doc = dict(doc)
    doc["spec_hash"] = spec_hash(doc)
    return FaultSpec.model_validate(doc)
