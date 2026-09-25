"""Canonical argument encoding and the three hashes derived from it (§23.1).

Credentials are never arguments, so they are never hashed and never journaled — the secrets
contract (Appendix A §2) is a property of this module's inputs, not a filter inside it.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from uuid import UUID

from keel.core.ids import EffectKey, RunId


def canonical_json(value: Any) -> str:
    """Sorted keys, no insignificant whitespace, UUIDs and datetimes as strings."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_encode)


def _encode(o: Any) -> Any:
    if isinstance(o, UUID):
        return str(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    raise TypeError(f"{type(o).__name__} is not canonically encodable")


def canonical_args(args: Any) -> str:
    """A step's arguments, total and process-independent (§9.1): `bytes` as base64 (a model's own bytes
    fields follow its `ser_json_bytes`), and a `set` or `frozenset` anywhere in them refused, bare or
    inside a model, because its order follows per-process hash randomisation and two workers would hash
    the same call differently. §9.1 refuses those at registration; arguments here are a keyword dict
    with no declared type, so they are refused at the call, before anything is journaled. A value that
    encoded before this rule and holds no set encodes exactly as it did."""
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=_encode_arg)


_UNORDERED = "a set or frozenset is not a canonical argument (its order is per-process); pass a sorted list"


def _encode_arg(o: Any) -> Any:
    if isinstance(o, (bytes, bytearray)):
        return base64.b64encode(o).decode("ascii")
    if isinstance(o, (set, frozenset)):
        raise TypeError(_UNORDERED)
    if hasattr(o, "model_dump"):
        # JSON mode turns a set field into a list in iteration order: the case the rule exists for.
        _refuse_sets(o.model_dump(mode="python"))
    return _encode(o)


def _refuse_sets(value: Any) -> None:
    if isinstance(value, (set, frozenset)):
        raise TypeError(_UNORDERED)
    items = value.values() if isinstance(value, dict) else value if isinstance(value, (list, tuple)) else ()
    for item in items:
        _refuse_sets(item)


def args_hash(args: Any) -> str:
    return hashlib.sha256(canonical_args(args).encode()).hexdigest()


def request_hash(request: Any) -> str:
    """Diagnostics only. RECOVER never compares it; VERIFY reports PromptDrift from it (§1)."""
    return hashlib.sha256(canonical_json(request).encode()).hexdigest()


def effect_key(run_root_id: RunId, step_index: int, tool_name: str, args: Any) -> EffectKey:
    """sha256(run_root_id ‖ step_index ‖ tool ‖ canonical_args)[:32] hex characters (§3).

    Stable across attempts and recoveries (the receiver can dedup), unique per logical effect
    across the run root (step_index never repeats), different across forks (new run_root_id).
    """
    material = f"{run_root_id}\x1f{step_index}\x1f{tool_name}\x1f{canonical_args(args)}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def projection_hash(state: Any) -> str:
    """Raw projection hash = sha256(canonical_json(RunState)) (§4.5, MVP form)."""
    return hashlib.sha256(canonical_json(state).encode()).hexdigest()
