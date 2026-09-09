"""W1 `tool_chain_1_effect` — the workload matrix v0 is built on (§14.1).

    search [PURE] → create_issue [EXTERNAL | IDEMPOTENT] → answer

Three steps, exactly one of which is dangerous. The two variants are the two published bands: the
EXTERNAL one runs against a receiver that honours nothing (`issues.create`, `dedup: false`) and
must surface its ambiguity; the IDEMPOTENT one runs against a receiver that deduplicates on the
identity it is given (`issues.upsert`, `dedup: true, natural: true`) and must re-fire safely.

This module holds only the runtime-neutral half. The Keel binding — the program, the tools, the
provider — is `crashproof/adapters/keel.py`, and arrives with the adapters (§28.3).
"""

from __future__ import annotations

from pathlib import Path

from crashproof.workloads.spec import Workload, load_named
from crashproof.world.services import World, world_from_endpoints

NAME = "tool_chain_1_effect"
VARIANTS = ("EXTERNAL", "IDEMPOTENT")

WORKLOAD: Workload = load_named(NAME)


def build_world(*, log_path: Path | str | None = None) -> World:
    """One World per trial, with every endpoint the workload declares — both variants' endpoints
    exist in the same World, so a trial that fires the wrong one is visible rather than impossible.
    """
    return world_from_endpoints(WORKLOAD.endpoint_decls(), log_path=log_path)


def required_effects(variant: str) -> tuple[str, ...]:
    """The landmarks that must exist in the World for `COMPLETED` to be honest — S3."""
    return WORKLOAD.variant(variant).required_effects


def endpoint_of(variant: str, tool: str = "create_issue") -> str:
    return next(t.endpoint for t in WORKLOAD.tools_for(variant) if t.name == tool)
