"""The OTel export as a projection (§19.7): a pure fold from events to spans, and those spans as OTLP/JSON.

It never sits on the write path and the journal has no dependency on it: an export that fails loses
nothing, because a re-fold produces the same spans — every id is derived, never random:

    trace   the envelope's `trace_id` (the delegation tree's root run id; a UUID is already 128 bits)
    run     sha256(run_id ‖ "run")[:8]
    epoch   sha256(run_id ‖ lease_epoch)[:8]              one recovery span per lease epoch
    attempt sha256(run_id ‖ step_index ‖ attempt_no)[:8]  STARTED → its outcome
    wait    sha256(run_id ‖ "wait" ‖ seq)[:8]              RUN_WAITING → the next epoch's RECOVERY_STARTED

A memoized step emits nothing: there is no new event for it, so a crash shows as a recovery span that
splits the trace and the attempts after it, never as a second copy of the work before it. MODEL
attempts carry the OTel GenAI attribute names, which is what makes a Langfuse *generation* of them;
the names are the semantic conventions' as known here, not checked against a Langfuse ingest. What
the journal knows and a trace cannot show — fence trips, resolution evidence, the diff — stays in
`keel show`, `keel events` and `keel diff`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from keel.events import Event

OUTCOMES = frozenset({"STEP_COMPLETED", "STEP_FAILED", "STEP_AMBIGUOUS", "STEP_CANCELLED"})
TERMINAL = frozenset({"RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED", "RUN_SUPERSEDED"})
_ERROR = frozenset({"STEP_FAILED", "STEP_AMBIGUOUS", "RUN_FAILED"})
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(slots=True)
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start: datetime
    end: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def span_id(*parts: Any) -> str:
    """64 bits of sha256 over the parts: the same span on every re-export."""
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:16]


def spans(events: list[Event], *, parent_span_id: str | None = None) -> list[Span]:
    """One run's spans. `parent_span_id` hangs a child run under its parent's DELEGATE attempt (§19.7);
    `tree_spans` finds it from the parent's CHILD_SPAWNED."""
    if not events:
        return []
    run_id = events[0].run_id
    trace = events[0].env.trace_id.hex
    first, last = events[0], events[-1]
    created = first.body
    run = Span(trace, span_id(run_id, "run"), parent_span_id, f"run {getattr(created, 'program', '')}", first.ts,
               attributes={"keel.run_id": str(run_id), "keel.program_version": first.env.program_version,
                           **({"keel.parent_run_id": str(created.parent_run_id)} if getattr(created, "parent_run_id", None) else {}),
                           **({"keel.delegation_id": str(created.delegation_id)} if getattr(created, "delegation_id", None) else {})})
    out = [run]
    epochs: dict[int, Span] = {}
    attempts: dict[tuple[int, int], Span] = {}
    intents: dict[int, Any] = {}
    waits: list[Span] = []
    for ev in events:
        b, t = ev.body, ev.type
        if t == "RECOVERY_STARTED":
            for w in waits:
                w.end = w.end or ev.ts  # a wait ends when a worker re-acquires the lease
            for s in epochs.values():
                s.end = s.end or ev.ts
            epochs[b.lease_epoch] = Span(trace, span_id(run_id, b.lease_epoch), run.span_id, f"epoch {b.lease_epoch} {b.cause}",
                                         ev.ts, attributes={"keel.lease_epoch": b.lease_epoch, "keel.cause": b.cause})
            out.append(epochs[b.lease_epoch])
        elif t == "RECOVERY_COMPLETED" and ev.lease_epoch in epochs:
            epochs[ev.lease_epoch].attributes.update(
                {"keel.replayed_steps": b.replayed_steps, "keel.live_from_step": b.live_from_step})
        elif t == "STEP_INTENDED":
            intents[b.step_index] = b
        elif t == "STEP_ATTEMPT_STARTED":
            intent = intents.get(b.step_index)
            parent = epochs.get(ev.lease_epoch, run)
            s = Span(trace, span_id(run_id, b.step_index, b.attempt_no), parent.span_id,
                     f"{getattr(intent, 'kind', 'STEP')} {getattr(intent, 'name', '')}".strip(), ev.ts,
                     attributes={"keel.step_index": b.step_index, "keel.attempt_no": b.attempt_no,
                                 "keel.kind": getattr(intent, "kind", None), "keel.name": getattr(intent, "name", None),
                                 "keel.effect_class": getattr(intent, "effect_class", None),
                                 "keel.effect_key": getattr(intent, "effect_key", None)})
            if ev.env.blob_ids:
                s.attributes["keel.blob_ids"] = list(ev.env.blob_ids)  # ids, never contents
            attempts[(b.step_index, b.attempt_no)] = s
            out.append(s)
        elif t in OUTCOMES:
            key = (b.step_index, b.attempt_no if b.attempt_no is not None else 1)
            s = attempts.get(key)
            if s is not None and s.end is None:
                s.end = ev.ts
                s.attributes["keel.outcome"] = t
                if t in _ERROR:
                    s.error = getattr(b, "error", None) or getattr(b, "cause", None) or t
                if t == "STEP_COMPLETED" and s.attributes.get("keel.kind") in ("MODEL", "COMPACT"):
                    s.attributes.update(_gen_ai(b))
        elif t == "RUN_WAITING":
            w = Span(trace, span_id(run_id, "wait", ev.seq), epochs.get(ev.lease_epoch, run).span_id,
                     f"wait {b.reason}", ev.ts, attributes={"keel.reason": b.reason})
            waits.append(w)
            out.append(w)
        elif t in TERMINAL:
            run.end = ev.ts
            run.attributes["keel.phase"] = t.removeprefix("RUN_")
            if t in _ERROR:
                run.error = getattr(b, "error", None) or t
    # Whatever is still open is open at the last event: an abandoned attempt never got an outcome of its
    # own (the successor's closure names attempt n, and ended it above), a live run has not ended.
    for s in out:
        s.end = s.end or last.ts
    return out


def _gen_ai(b: Any) -> dict[str, Any]:
    meta, usage = b.provider_meta or {}, b.usage or {}
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.system": meta.get("provider"),
        "gen_ai.request.model": meta.get("model"),
        "gen_ai.response.model": meta.get("model_version") and f"{meta.get('model')}@{meta.get('model_version')}",
        "gen_ai.usage.input_tokens": usage.get("input_tokens"),
        "gen_ai.usage.output_tokens": usage.get("output_tokens"),
        "keel.cache_read_tokens": usage.get("cache_read_tokens"),
    }
    return {k: v for k, v in attrs.items() if v is not None}


def otlp(all_spans: list[Span], *, version: str = "") -> dict[str, Any]:
    """OTLP/JSON (the protobuf JSON mapping: hex ids, int64 as strings), for `POST /v1/traces`."""
    return {"resourceSpans": [{
        "resource": {"attributes": _attrs({"service.name": "keel"})},
        "scopeSpans": [{"scope": {"name": "keel", "version": version}, "spans": [
            {
                "traceId": s.trace_id,
                "spanId": s.span_id,
                **({"parentSpanId": s.parent_span_id} if s.parent_span_id else {}),
                "name": s.name,
                "kind": 1,  # SPAN_KIND_INTERNAL
                "startTimeUnixNano": str(_nanos(s.start)),
                "endTimeUnixNano": str(_nanos(s.end or s.start)),
                "attributes": _attrs(s.attributes),
                "status": {"code": 2, "message": s.error} if s.error else {"code": 1},
            }
            for s in all_spans
        ]}],
    }]}


def _nanos(ts: datetime) -> int:
    """Integer arithmetic, not `timestamp()`: a float can land a hair below a whole second."""
    return (ts - _EPOCH) // timedelta(microseconds=1) * 1_000


def _attrs(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": k, "value": _value(v)} for k, v in attrs.items() if v is not None]


def _value(v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, (list, tuple)):
        return {"arrayValue": {"values": [_value(x) for x in v]}}
    return {"stringValue": str(v)}
