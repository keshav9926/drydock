"""Type name <-> model, schema_version per type, and the (de)serialisation entry point (§23.1)."""

from __future__ import annotations

import json
from typing import Any, get_args

from pydantic import TypeAdapter

from keel.events.schema import EventBody
from keel.events.upcasters import UPCASTERS

_BODY_ADAPTER: TypeAdapter[Any] = TypeAdapter(EventBody)

EVENT_TYPES: dict[str, type] = {
    m.model_fields["type"].default: m for m in get_args(get_args(EventBody)[0])
}

# Every type is at version 1 until an upcaster raises it (§6.5).
CURRENT: dict[str, int] = dict.fromkeys(EVENT_TYPES, 1)


def payload_of(body: Any) -> dict[str, Any]:
    """Body -> the `payload` jsonb column. `type` travels in its own column, not in the payload."""
    d = json.loads(body.model_dump_json(by_alias=True))
    d.pop("type", None)
    return d


def body_from_payload(type_: str, schema_version: int, payload: dict[str, Any]) -> Any:
    """Upcast one version at a time, then validate. A missing upcaster is loud: refuse the run."""
    raw = {**payload, "type": type_, "schema_version": schema_version}
    while raw["schema_version"] < CURRENT[type_]:
        raw = UPCASTERS[(type_, raw["schema_version"])](raw)
    raw.pop("schema_version", None)
    return _BODY_ADAPTER.validate_python(raw)
