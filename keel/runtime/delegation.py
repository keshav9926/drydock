"""The delegation contract, and the two things the parent owes the child (§17.2, §17.8).

A child is a run. What makes it a *child* is a contract the parent wrote down before the child
existed — program, task, the shape of the answer, the budget it may spend, the tools it may touch,
what to do if it fails — committed as `CHILD_SPAWNED.contract` in the same transaction as the
child's own RUN_CREATED. Everything the parent will ever know about the child is in that contract
and in the one signal the child sends back; the parent is contractually blind to the rest (§17.3).

Two decisions here are made once so nothing downstream has to remake them.

**The result schema is part of the DELEGATE step's identity.** It is dumped to JSON Schema inside
the canonical args, so a redeploy that changes what a delegated task is asked to return trips
`NondeterminismDetected` at that step instead of silently re-grading children spawned under the
old contract. §17.8's "a later schema change never re-judges an old result" is a consequence of
that, not a separate rule.

**Validation happens before the INTENT commits, and a violation is a program bug.** A contract that
asks for tools the parent does not have, a `verify` role holding a tool that can write, a slice
larger than what remains, or `retry` on a tool that cannot be probed — none of these is a fault the
runtime should survive; they are `ContractInvalid`. The engine journals the refusal the way it
journals a budget refusal — the step's INTENT and a `STEP_FAILED` at `attempt_no = 0`, in one
transaction — so the program sees it as its own step failing and a replay sees the same thing
without re-judging it: a registry that has changed since cannot turn a failed run into a
different failed run (§10.5).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from keel.core.errors import ContractInvalid
from keel.core.ids import RunId, uuid7
from keel.journal.protocol import SignalRow

OnFailure = Literal["retry", "escalate", "fail_parent"]
Role = Literal["worker", "verify"]

#: §17.5: children that currently hold a lease, per parent. The lease is the compute, so a child
#: parked on an approval frees its slot.
MAX_CHILDREN_IN_FLIGHT = 4
#: §17.5: a verifier delegating to a verifier is refused; three levels is the honest default.
MAX_DELEGATION_DEPTH = 3


class Delegation(BaseModel):
    """One contract. The constitution fixes the core fields; the rest are §17.2's section-local
    decisions, carried here in its spirit."""

    model_config = ConfigDict(frozen=True)

    program: str
    task: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    #: A Pydantic model class, or an already-dumped JSON Schema. Stored as the schema either way.
    result_schema: Any = None
    budget_slice: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: frozenset[str] = frozenset()
    on_failure: OnFailure = "escalate"
    max_retries: int = 1
    on_parent_cancel: Literal["cancel"] = "cancel"
    role: Role = "worker"
    deadline_s: float | None = None

    def schema_json(self) -> dict[str, Any] | None:
        s = self.result_schema
        if s is None:
            return None
        if isinstance(s, dict):
            return s
        if isinstance(s, type) and issubclass(s, BaseModel):
            return s.model_json_schema()
        raise ContractInvalid(f"result_schema must be a Pydantic model or a JSON schema, not {type(s).__name__}")

    def as_journaled(self) -> dict[str, Any]:
        """What CHILD_SPAWNED carries and what the child is handed as its own args. The schema is
        dumped, never the class: a journal must not depend on a class still being importable."""
        return {
            "program": self.program,
            "task": self.task,
            "args": dict(self.args),
            "result_schema": self.schema_json(),
            "budget_slice": dict(self.budget_slice),
            "allowed_tools": sorted(self.allowed_tools),
            "on_failure": self.on_failure,
            "max_retries": self.max_retries,
            "on_parent_cancel": self.on_parent_cancel,
            "role": self.role,
            "deadline_s": self.deadline_s,
        }


class ChildResult(BaseModel):
    """What `ctx.delegate` returns — always this wrapper, never the bare result, so the failure
    path is impossible to skip by accident (§17.8)."""

    model_config = ConfigDict(frozen=True)

    child_run_id: str
    status: Literal["completed", "failed", "cancelled"]
    result: Any = None
    error: str | None = None
    usage_settled: dict[str, Any] = Field(default_factory=dict)


def canonical(contracts: list[Delegation]) -> list[dict[str, Any]]:
    """The DELEGATE step's args: the journaled form of every contract, in order. Hashing this is
    what puts the result schema into the step's identity."""
    return [c.as_journaled() for c in contracts]


def validate(
    contracts: list[Delegation],
    *,
    parent_tools: Any,
    parent_remaining_tokens: int | None,
    parent_depth: int = 0,
    parent_remaining_usd: float | None = None,
) -> None:
    """Every rule §17.2 lists, checked before anything is committed."""
    if not contracts:
        raise ContractInvalid("delegate_many needs at least one contract")
    if parent_depth + 1 > MAX_DELEGATION_DEPTH:
        raise ContractInvalid(f"delegation depth {parent_depth + 1} exceeds {MAX_DELEGATION_DEPTH}")
    available = {t.name for t in parent_tools} if parent_tools is not None else set()
    total_tokens, total_usd = 0, 0.0
    for i, c in enumerate(contracts):
        c.schema_json()  # raises for a schema that is neither a model nor a dict
        if parent_tools is not None and not c.allowed_tools <= available:
            raise ContractInvalid(
                f"contract {i}: allowed_tools {sorted(c.allowed_tools - available)} are not the parent's"
            )
        if c.role == "verify" and parent_tools is not None:
            writers = [
                t.name for t in parent_tools
                if t.name in c.allowed_tools and str(getattr(t, "effect_class", "")) not in ("PURE", "EffectClass.PURE")
            ]
            if writers:
                raise ContractInvalid(f"contract {i}: a verify role may not hold {writers}; PURE only")
        if c.on_failure == "retry" and parent_tools is not None:
            # §17.6: delegation-level retry is at-least-once at the granularity of the child's
            # effects. The honest combination is "retry only what can be probed or is read-only".
            unsafe = [
                t.name for t in parent_tools
                if t.name in c.allowed_tools and getattr(t, "resolution", None) == "assume_failed"
            ]
            if unsafe:
                raise ContractInvalid(f"contract {i}: retry with assume_failed tools {unsafe} would re-fire")
        total_tokens += int(c.budget_slice.get("max_tokens") or 0)
        total_usd += float(c.budget_slice.get("max_usd") or 0.0)
    if parent_remaining_tokens is not None and total_tokens > parent_remaining_tokens:
        raise ContractInvalid(
            f"Σ budget_slice.max_tokens {total_tokens} exceeds the parent's remaining {parent_remaining_tokens}"
        )
    if parent_remaining_usd is not None and total_usd > parent_remaining_usd:
        raise ContractInvalid(
            f"Σ budget_slice.max_usd {total_usd:g} exceeds the parent's remaining {parent_remaining_usd:g}"
        )


def delegation_id(parent_run_id: Any, step_index: int, ordinal: int, retry_no: int) -> str:
    """Deterministic, so a re-executed spawn addresses the *same* delegation and the unique key
    on `(parent, step, ordinal, retry)` turns a second child into a loud violation (§7.6.1)."""
    material = f"{parent_run_id}\x1f{step_index}\x1f{ordinal}\x1f{retry_no}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def json_schema_ok(schema: dict[str, Any] | None, value: Any) -> tuple[bool, str | None]:
    """The parent's grade of a child's result against the contract's `result_schema` (§17.8).

    Judged on the *journaled* schema, never on a class: grading happens at the drain, possibly in
    another process, and has to give the same answer there. Recursive over what a Pydantic model's
    `model_json_schema()` emits — `type`, `required`, `properties`, `items`, `$ref`/`$defs`,
    `enum`/`const`, `anyOf`/`oneOf`/`allOf` (Optional, unions), numeric bounds, string and array
    lengths, `pattern`, `additionalProperties: false`. The injection wall is only as good as this.

    # ponytail: a subset of JSON Schema (no `format`, `if/then`, `dependentRequired`, remote refs);
    # add a real validator dependency when a contract needs one of those.
    """
    if not schema:
        return True, None
    why = _violation(schema, value, schema.get("$defs") or schema.get("definitions") or {}, "result")
    return why is None, why


def _violation(schema: dict[str, Any], value: Any, defs: dict[str, Any], at: str) -> str | None:  # noqa: C901
    import re

    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        target = defs.get(ref.rsplit("/", 1)[-1])
        if target is None:
            return f"{at}: unresolvable $ref {ref}"
        return _violation(target, value, defs, at)
    for sub in schema.get("allOf") or []:
        if (why := _violation(sub, value, defs, at)) is not None:
            return why
    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if options:
            matches = sum(_violation(o, value, defs, at) is None for o in options)
            if matches == 0 or (key == "oneOf" and matches > 1):
                return f"{at}: matches {matches} of the {key} alternatives"
    if "const" in schema and value != schema["const"]:
        return f"{at}: expected {schema['const']!r}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{at}: {value!r} is not one of {schema['enum']!r}"
    if "type" in schema and not _is_type(value, schema["type"]):
        return f"{at}: expected {schema['type']}, got {type(value).__name__}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{at}: {value} < minimum {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{at}: {value} > maximum {schema['maximum']}"
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            return f"{at}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}"
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            return f"{at}: {value} >= exclusiveMaximum {schema['exclusiveMaximum']}"
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            return f"{at}: shorter than {schema['minLength']}"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{at}: longer than {schema['maxLength']}"
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return f"{at}: does not match {schema['pattern']!r}"
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            return f"{at}: fewer than {schema['minItems']} items"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{at}: more than {schema['maxItems']} items"
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                if (why := _violation(schema["items"], item, defs, f"{at}[{i}]")) is not None:
                    return why
    if isinstance(value, dict):
        for key in schema.get("required") or []:
            if key not in value:
                return f"{at}: missing required field {key!r}"
        props = schema.get("properties") or {}
        for key, item in value.items():
            if key in props:
                if (why := _violation(props[key], item, defs, f"{at}.{key}")) is not None:
                    return why
            elif schema.get("additionalProperties") is False:
                return f"{at}: unexpected field {key!r}"
    return None


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def _is_type(value: Any, json_type: Any) -> bool:
    types = json_type if isinstance(json_type, list) else [json_type]
    return any(isinstance(value, _JSON_TYPES.get(t, ())) for t in types) and not (
        isinstance(value, bool) and "boolean" not in types
    )


def digest(contracts: list[Delegation]) -> str:
    return hashlib.sha256(json.dumps(canonical(contracts), sort_keys=True, default=str).encode()).hexdigest()[:16]


def row_role(role: str) -> str:
    """The API says `verify` (§17.2); the `delegations.role` CHECK says `verifier` (§5.5). One
    place decides which spelling the row gets."""
    return "verifier" if role == "verify" else "worker"


# --- the two inbox rows delegation writes (§5.6, §5.10) ---------------------------------
def child_result_signal(
    parent_run_id: RunId,
    child_run_id: RunId,
    *,
    status: str,
    result: Any = None,
    error: str | None = None,
    usage: dict[str, Any] | None = None,
) -> SignalRow:
    """The child's terminal notice, inserted by the child's own holder in the same transaction as
    its terminal event. `client_key = 'child_result:' || child_run_id`: a child has one terminal
    event, so it has one notice, whoever retries what."""
    return SignalRow(
        signal_id=uuid7(),
        run_id=parent_run_id,
        type="child_result",
        payload={
            "child_run_id": str(child_run_id),
            "status": status,
            "result": result,
            "error": error,
            "usage": dict(usage or {}),
        },
        client_key=f"child_result:{child_run_id}",
        source=f"child:{child_run_id}",
    )


def cancel_signal(run_id: RunId, *, client_key: str, by: str, reason: str) -> SignalRow:
    """A `cancel` from a parent or the reaper: the same row `keel cancel` writes, keyed so a
    re-executed acknowledgement or a second reaper tick produces one."""
    return SignalRow(
        signal_id=uuid7(),
        run_id=run_id,
        type="cancel",
        payload={"by": by, "reason": reason},
        client_key=client_key,
        source=by,
    )


def usage_of(state: Any) -> dict[str, Any]:
    """What a child reports back as `usage`: its own budget projection, which is already an upper
    bound on its provider bill (§16.4) — so the parent's ledger stays a bound for the whole tree."""
    charged = state.charged
    return {
        "tokens_charged": charged.tokens_charged,
        "model_calls": charged.model_calls,
        "tool_calls": charged.tool_calls,
        "usd_charged": charged.usd_charged,
        "usd_priced": charged.usd_priced,
    }
