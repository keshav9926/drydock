"""The oracle: what the World will answer about what actually happened (§4.13).

Three questions, and they are the reason the harness can say anything at all:

    applied(logical_identity)   how many times the world really changed
    receipts(logical_identity)  how many times it was asked to
    probe(effect_key | args)    did *this* effect land?

`probe` is the same query Keel's EXTERNAL `create_issue` calls from its `probe` hook, which is the
point: the runtime under test and the verifier read the same ground truth, and neither reads the
runtime's own opinion. It is **point-in-time** by construction — it answers "as of now", so a
zombie request the receiver applies after the probe returns ABSENT is a duplicate the probe could
not have seen. That window is measured (§8.4), never argued away.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crashproof.world.services import World


def applied(world: World, logical_identity: str | None = None) -> dict[str, int] | int:
    counts = world.applied_counts()
    return counts if logical_identity is None else counts.get(logical_identity, 0)


def receipts(world: World, logical_identity: str | None = None) -> dict[str, int] | int:
    counts = world.receipt_counts()
    return counts if logical_identity is None else counts.get(logical_identity, 0)


def probe(
    world: World,
    *,
    endpoint: str | None = None,
    effect_key: str | None = None,
    args: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """COMMITTED (with the result the killed attempt never received) | ABSENT.

    Answered by presented key when there was one — F1 — and by logical identity when there was not,
    which is the only thing available at F0 and on a `dedup:false` endpoint that never saw a key.
    """
    if effect_key is not None:
        found = world.lookup_key(effect_key)
        if found is not None:
            return _committed(found, f"effect_key {effect_key} applied at {found['logical_identity']}")
    if endpoint is not None and args is not None:
        label = world.label_for(endpoint, args)
        found = world.lookup(label)
        if found is not None:
            return _committed(found, f"{label} applied {world.applied_counts()[label]}x")
        return {"verdict": "ABSENT", "evidence": f"no application of {label}", "result": None}
    return {
        "verdict": "ABSENT",
        "evidence": f"no application under effect_key {effect_key}",
        "result": None,
    }


def _committed(result: dict[str, Any], evidence: str) -> dict[str, Any]:
    return {
        "verdict": "COMMITTED",
        "evidence": evidence,
        "result": result,
        "external_ref": result.get("external_ref"),
    }


def state(world: World) -> dict[str, Any]:
    """Everything a trial's collector takes: raw observations, never verdicts."""
    return {
        "applied": world.applied_counts(),
        "receipts": world.receipt_counts(),
        "endpoints": {
            e.id: {"dedup": e.dedup, "natural": e.natural, "kind": e.kind}
            for e in world.endpoints.values()
        },
        "log": [
            {
                "seq": r.seq,
                "endpoint": r.endpoint,
                "effect_key": r.effect_key,
                "logical_identity": r.logical_identity,
                "ts": r.ts,
            }
            for r in world.receipts
        ],
    }
