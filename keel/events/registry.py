"""Type name <-> model, schema_version per type, and the (de)serialisation entry point (§23.1)."""

from __future__ import annotations

import json
from typing import Any, get_args

from pydantic import TypeAdapter

from keel.core.errors import SchemaTooNew
from keel.events.envelope import Envelope, Event
from keel.events.schema import EventBody
from keel.events.upcasters import UPCASTERS

_BODY_ADAPTER: TypeAdapter[Any] = TypeAdapter(EventBody)

EVENT_TYPES: dict[str, type] = {
    m.model_fields["type"].default: m for m in get_args(get_args(EventBody)[0])
}

# Every type is at version 1 until an upcaster raises it (§6.5): one past its newest upcaster.
CURRENT: dict[str, int] = {t: 1 + max((v for (u, v) in UPCASTERS if u == t), default=0) for t in EVENT_TYPES}


def payload_of(body: Any) -> dict[str, Any]:
    """Body -> the `payload` jsonb column. `type` travels in its own column, not in the payload."""
    d = json.loads(body.model_dump_json(by_alias=True))
    d.pop("type", None)
    return d


def body_from_payload(type_: str, schema_version: int, payload: dict[str, Any]) -> Any:
    """Upcast one version at a time, then validate. A missing upcaster is loud: refuse the run. There
    are no downcasters: an event newer than this code is `SchemaTooNew`, and the worker releases the
    run for a newer one rather than guessing (§6.5)."""
    if schema_version > CURRENT[type_]:
        raise SchemaTooNew(f"{type_} v{schema_version} is newer than this worker's v{CURRENT[type_]}")
    raw = {**payload, "type": type_, "schema_version": schema_version}
    while raw["schema_version"] < CURRENT[type_]:
        raw = UPCASTERS[(type_, raw["schema_version"])](raw)
    raw.pop("schema_version", None)
    return _BODY_ADAPTER.validate_python(raw)


def load_event(dumped: dict[str, Any]) -> Event:
    """One `{env, body}` dump (`keel events --json`, a fixture) through the same load path as a stored
    row: the envelope keeps the version it was written at, the body is upcast to the current one."""
    env = Envelope.model_validate(dumped["env"])
    body = {k: v for k, v in dumped["body"].items() if k != "type"}
    return Event(env=env, body=body_from_payload(dumped["body"]["type"], env.schema_version, body))
