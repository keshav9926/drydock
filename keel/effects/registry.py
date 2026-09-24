"""Tool registration, the effect-class composition rules, and the TOOL StepExecutor (§24.3).

Importing this module registers `StepExecutor(TOOL)` into `runtime.steps.EXECUTORS`; that is the
inversion that lets `runtime` decide recovery by effect class without importing `effects` (§23.2).
"""

from __future__ import annotations

import inspect
import os
import warnings
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from keel.core.errors import ContractViolation, LeaseTooShort, ToolRegistrationError, UnknownTool
from keel.core.protocols import (
    COMPENSATE,
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
    #: STREAMS only (§24.3): `await tctx.emit(chunk)` journals what the tool has produced so far, as
    #: STEP_CHUNK batches. Observability, never the result; None for a tool that does not stream.
    emit: Callable[..., Any] | None = None


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
        #: The compensating action's own class (§9.5): an undo is a second effect, EXTERNAL + escalate
        #: unless its author says otherwise — the same default an undeclared receiver gets.
        self.compensate_effect = EffectClass.EXTERNAL
        self.compensate_idempotency = Idempotency.NONE
        self._validate()

    def _validate(self) -> None:
        if Modifier.STREAMS in self.modifiers and self.effect_class is EffectClass.TRANSACTIONAL:
            raise ContractViolation(f"{self.name}: STREAMS is never valid with TRANSACTIONAL")
        if self.partial_ok and self.effect_class is not EffectClass.PURE:
            raise ContractViolation(f"{self.name}: partial_ok is only valid with PURE")
        if self.timeout <= 0:
            raise ToolRegistrationError(f"{self.name}: timeout must be positive")
        if Modifier.LOCAL_FS in self.modifiers and self.effect_class not in (EffectClass.PURE, EffectClass.IDEMPOTENT):
            # §9.3: EXTERNAL + LOCAL_FS needs the Sandbox snapshot and its tree-hash probe, which are
            # git, which is cut (§29.2). Until then a workspace write is PURE or IDEMPOTENT-by-content.
            raise ContractViolation(f"{self.name}: LOCAL_FS is PURE or IDEMPOTENT-by-content (no snapshot/probe)")

    # decorators: @create_issue.probe / @create_issue.compensate (§24.3)
    def probe_hook(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        self.probe = fn
        return fn

    def compensate_hook(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        effect: EffectClass = EffectClass.EXTERNAL,
        idempotency: Idempotency = Idempotency.NONE,
    ) -> Any:
        """`async hook(effect_key, args, result[, tctx])` — the committed effect's key, args and result,
        and optionally the compensating step's own `ToolCtx`, whose `effect_key` is the one to present
        to the receiver. Keel never calls it by itself: only `ctx.compensate` and `Keel.compensate` do."""
        if effect is EffectClass.IDEMPOTENT and idempotency is Idempotency.NONE:
            raise ToolRegistrationError(f"{self.name}.compensate: IDEMPOTENT needs idempotency KEY or CONTENT")

        def attach(f: Callable[..., Any]) -> Callable[..., Any]:
            self.compensate, self.compensate_effect, self.compensate_idempotency = f, effect, idempotency
            return f

        return attach(fn) if fn is not None else attach

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


def compensation_spec(base: ToolSpec) -> ToolSpec:
    """The compensating action as a tool of its own: its own name, class and key, the base's timeout
    and secrets. Its args are the committed effect's facts, so the step's identity names what it undoes."""
    hook = base.compensate
    wants_tctx = len(inspect.signature(hook).parameters) >= 4

    async def run(args: dict[str, Any], tctx: ToolCtx) -> Any:
        facts = (args["of_effect_key"], args["args"], args["result"])
        return await (hook(*facts, tctx) if wants_tctx else hook(*facts))

    return ToolSpec(
        run,
        name=base.name + COMPENSATE,
        effect_class=base.compensate_effect,
        resolution="escalate",
        timeout=base.timeout,
        modifiers=(),
        partial_ok=False,
        idempotency=base.compensate_idempotency,
        secrets=base.secrets,
    )


class ToolRegistry:
    def __init__(self, tools: Iterable[ToolSpec] = ()) -> None:
        self._tools: dict[str, ToolSpec] = {}
        #: Built on first use and kept out of `manifest()`: a program's registration records the tools it
        #: was given, and a compensating action is derived from one of them, not declared beside it.
        self._compensations: dict[str, ToolSpec] = {}
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
        spec = self._tools.get(name) or self._compensation(name)
        if spec is None:
            raise UnknownTool(name)
        return spec

    def _compensation(self, name: str) -> ToolSpec | None:
        if name in self._compensations or not name.endswith(COMPENSATE):
            return self._compensations.get(name)
        base = self._tools.get(name[: -len(COMPENSATE)])
        if base is None or base.compensate is None:
            return None
        self._compensations[name] = compensation_spec(base)
        return self._compensations[name]

    def __contains__(self, name: object) -> bool:
        return name in self._tools or (isinstance(name, str) and self._compensation(name) is not None)

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
            workspace=sctx.workspace,
            credentials={n: os.environ[n] for n in spec.secrets if n in os.environ},
            resources=sctx.resources,
            emit=sctx.emit,
        )
        result = await spec.run(intent.args, tctx)
        external_ref = result.get("external_ref") if isinstance(result, dict) else None
        return Completed(result=result, external_ref=external_ref)


register(_ToolExecutor())
