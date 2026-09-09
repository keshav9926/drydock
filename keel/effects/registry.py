"""Tool registration, the effect-class composition rules, and the TOOL StepExecutor (§24.3).

Importing this module registers `StepExecutor(TOOL)` into `runtime.steps.EXECUTORS`; that is the
inversion that lets `runtime` decide recovery by effect class without importing `effects` (§23.2).
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from keel.core.errors import ContractViolation, LeaseTooShort, ToolRegistrationError, UnknownTool
from keel.core.protocols import (
    Completed,
    EffectClass,
    Idempotency,
    Modifier,
    Resolution,
    StepCtx,
    StepIntent,
    StepKind,
    StepOutcome,
)
from keel.runtime.steps import register


@dataclass(slots=True)
class ToolCtx:
    """What a tool is handed. Credentials are the values of the tool's declared `secrets`, resolved
    here and never on the args model — the secrets contract (Appendix A §2)."""

    run_id: Any
    run_root_id: Any
    step_index: int
    attempt_no: int
    effect_key: str | None
    deadline: datetime | None = None
    workspace: Path | None = None
    credentials: dict[str, str] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)


class ToolSpec:
    """A registered tool. One effect class, exactly; modifiers compose with it (§3)."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        name: str,
        effect_class: EffectClass,
        resolution: Resolution,
        timeout: float,
        modifiers: Sequence[Modifier],
        partial_ok: bool,
        idempotency: Idempotency,
        secrets: Sequence[str],
    ) -> None:
        self._fn = fn
        self.name = name
        self.effect_class = effect_class
        self.resolution: Resolution = resolution
        self.timeout = timeout
        self.modifiers = frozenset(modifiers)
        self.partial_ok = partial_ok
        self.idempotency = idempotency
        self.secrets = tuple(secrets)
        self.probe: Callable[..., Any] | None = None
        self.compensate: Callable[..., Any] | None = None
        self._validate()

    def _validate(self) -> None:
        if Modifier.STREAMS in self.modifiers and self.effect_class is EffectClass.TRANSACTIONAL:
            raise ContractViolation(f"{self.name}: STREAMS is never valid with TRANSACTIONAL")
        if self.partial_ok and self.effect_class is not EffectClass.PURE:
            raise ContractViolation(f"{self.name}: partial_ok is only valid with PURE")
        if self.timeout <= 0:
            raise ToolRegistrationError(f"{self.name}: timeout must be positive")

    # decorators: @create_issue.probe / @create_issue.compensate (§24.3)
    def probe_hook(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        self.probe = fn
        return fn

    def compensate_hook(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        self.compensate = fn
        return fn

    async def run(self, args: Any, tctx: ToolCtx) -> Any:
        return await self._fn(args, tctx)

    def manifest(self) -> dict[str, Any]:
        return {
            "class": str(self.effect_class),
            "modifiers": sorted(str(m) for m in self.modifiers),
            "timeout": self.timeout,
            "resolution": self.resolution,
            "idempotency": str(self.idempotency),
            "has_probe": self.probe is not None,
            "has_compensate": self.compensate is not None,
        }


def tool(
    *,
    effect: EffectClass,
    resolution: Resolution = "escalate",
    timeout: float = 5.0,
    modifiers: Sequence[Modifier] = (),
    partial_ok: bool = False,
    idempotency: Idempotency = Idempotency.NONE,
    secrets: Sequence[str] = (),
    name: str | None = None,
) -> Callable[[Callable[..., Any]], ToolSpec]:
    def wrap(fn: Callable[..., Any]) -> ToolSpec:
        spec = ToolSpec(
            fn,
            name=name or fn.__name__,
            effect_class=effect,
            resolution=resolution,
            timeout=timeout,
            modifiers=modifiers,
            partial_ok=partial_ok,
            idempotency=idempotency,
            secrets=secrets,
        )
        spec.__doc__ = fn.__doc__
        return spec

    return wrap


class ToolRegistry:
    def __init__(self, tools: Iterable[ToolSpec] = ()) -> None:
        self._tools: dict[str, ToolSpec] = {}
        for t in tools:
            self.add(t)

    def add(self, spec: ToolSpec) -> ToolSpec:
        if spec.effect_class is EffectClass.EXTERNAL and spec.resolution == "probe" and spec.probe is None:
            # defaulted and warned, per §24.3's registration table
            warnings.warn(
                f"tool {spec.name!r}: EXTERNAL with resolution='probe' but no probe declared; "
                "falling back to 'escalate'",
                stacklevel=2,
            )
            spec.resolution = "escalate"
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownTool(name) from exc

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())

    def manifest(self) -> dict[str, Any]:
        return {name: spec.manifest() for name, spec in self._tools.items()}

    def check_lease_ttl(self, lease_ttl: float) -> None:
        """`lease_ttl` must exceed the largest registered tool.timeout, or the pre-dispatch gate
        could never clear and every attempt would abandon with STARTED open (§8.4, §25.2)."""
        for spec in self._tools.values():
            if spec.effect_class is EffectClass.PURE:
                continue
            if lease_ttl <= spec.timeout:
                raise LeaseTooShort(
                    f"lease_ttl={lease_ttl}s must exceed tool {spec.name!r} timeout={spec.timeout}s"
                )


class _ToolExecutor:
    kind = StepKind.TOOL

    async def execute(self, intent: StepIntent, sctx: StepCtx) -> StepOutcome:
        spec: ToolSpec = sctx.tools.get(intent.name)
        tctx = ToolCtx(
            run_id=sctx.run_id,
            run_root_id=sctx.run_root_id,
            step_index=intent.step_index,
            attempt_no=sctx.attempt_no,
            effect_key=sctx.effect_key,
            deadline=sctx.deadline,
            credentials={n: os.environ[n] for n in spec.secrets if n in os.environ},
            resources=sctx.resources,
        )
        result = await spec.run(intent.args, tctx)
        external_ref = result.get("external_ref") if isinstance(result, dict) else None
        return Completed(result=result, external_ref=external_ref)


register(_ToolExecutor())
