"""The neutral workload specification (§13.2).

A workload names four things and nothing else: tools with effect classes, World endpoints with
dedup flags, a decision script that is a pure function of request content, and the expected end
state. That is what lets one document run unchanged against every runtime in a cell — the moment a
workload mentions a checkpointer or an activity, the cross-runtime comparison is over.

The models are the validation; the YAML is the source of truth. `spec_hash` is computed over the
canonical document and travels on every trial row, so "the same spec" is a fact, not a claim.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

SCRIPTS = Path(__file__).parent / "scripts"

EffectClassName = Literal["PURE", "IDEMPOTENT", "EXTERNAL", "TRANSACTIONAL"]
KeySource = Literal["none", "framework", "adapter"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolDecl(Frozen):
    name: str
    effect_class: EffectClassName
    endpoint: str
    resolution: Literal["probe", "assume_failed", "assume_succeeded", "escalate"] | None = None
    idempotency: Literal["NONE", "KEY", "NATURAL"] | None = None


class EndpointDecl(Frozen):
    """`dedup` and `natural` are properties of the receiver. Declaring both per endpoint is what
    measures "honours keys", "naturally idempotent" and "neither" inside one workload."""

    id: str
    service: str
    kind: Literal["read", "write"] = "write"
    dedup: bool = False
    natural: bool = False
    logical_identity: tuple[str, ...] = ()


class WorldDecl(Frozen):
    endpoints: tuple[EndpointDecl, ...]


class ScriptNode(Frozen):
    """`key` is the ordered (tool_name, occurrence) pairs answered in the request — never a
    counter. A re-asked request after a restart produces the same key, so the same node."""

    key: tuple[tuple[str, int], ...] = ()
    decision: dict[str, Any]
    alternate: dict[str, Any] | None = None


class Variant(Frozen):
    """One published band. It overrides tool declarations and the effects the World must show; it
    never changes the program or the script."""

    key_source: KeySource = "none"
    tools: tuple[ToolDecl, ...] = ()
    required_effects: tuple[str, ...] = ()
    world_state: dict[str, int] = Field(default_factory=dict)


class Expected(Frozen):
    status: str = "COMPLETED"
    result: dict[str, Any] = Field(default_factory=dict)


class Workload(Frozen):
    workload: str
    version: int = 1
    budget: dict[str, Any] = Field(default_factory=dict)
    tool_timeout_s: float = 1.0
    tools: tuple[ToolDecl, ...] = ()
    variants: dict[str, Variant] = Field(default_factory=dict)
    world: WorldDecl
    script: tuple[ScriptNode, ...] = ()
    expected: Expected = Expected()
    spec_hash: str = ""

    # --- resolution ----------------------------------------------------------
    def tools_for(self, variant: str | None = None) -> tuple[ToolDecl, ...]:
        """The declared tools with the variant's overrides applied, by name."""
        merged = {t.name: t for t in self.tools}
        for t in self.variant(variant).tools:
            merged[t.name] = t
        return tuple(merged.values())

    def variant(self, variant: str | None = None) -> Variant:
        if variant is None:
            return Variant()
        try:
            return self.variants[variant]
        except KeyError as exc:
            raise KeyError(f"{self.workload}: no variant {variant!r}") from exc

    def endpoint_decls(self) -> list[dict[str, Any]]:
        """What `world_from_endpoints` consumes — the World is declared here but does not import
        this module."""
        return [e.model_dump() for e in self.world.endpoints]

    def node_for(self, key: tuple[tuple[str, int], ...]) -> ScriptNode | None:
        for node in self.script:
            if node.key == key:
                return node
        return None


def load(path: Path | str) -> Workload:
    raw = Path(path).read_text(encoding="utf8")
    doc = yaml.safe_load(raw)
    doc["spec_hash"] = spec_hash(doc)
    return Workload.model_validate(doc)


def load_named(name: str) -> Workload:
    return load(SCRIPTS / f"{name}.yaml")


def spec_hash(doc: dict[str, Any]) -> str:
    body = {k: v for k, v in doc.items() if k != "spec_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
