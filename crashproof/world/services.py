"""The World: deterministic mock external services, and the receipt log that is ground truth (§11.1).

Every received request is logged as `(effect_key_if_any, args, logical_identity, ts)` and **fsynced
before the response is computed**. That ordering is the whole instrument: it is what makes
`after:tool_effect` a real boundary rather than a guess, and every later cell inherits its
truthfulness (§28.2's K11(a)). Nothing in this module may be reordered around it.

Two accountings, deliberately separate:

- `receipts` — every request the World received. `duplicate_receipts`.
- `applied`  — every request that actually changed the world. `duplicate_effects`, which is what
  S1 reads. The gap between them is exactly what a receiver's idempotency buys.

Per-endpoint `dedup` and `natural` exist so that "receiver honours keys", "receiver is naturally
idempotent" and "receiver does neither" are all measured by the same workload (§13.2).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Kind = Literal["read", "write"]


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One World endpoint. `dedup` / `natural` are properties of the *receiver*, declared per
    workload, never of the caller (§13.2)."""

    id: str
    service: str
    kind: Kind = "write"
    dedup: bool = False
    natural: bool = False
    logical_identity: tuple[str, ...] = ()

    @property
    def op(self) -> str:
        return self.id.split(".", 1)[1]


@dataclass(frozen=True, slots=True)
class Receipt:
    """One received request. Written and fsynced before anything is applied or answered."""

    seq: int
    endpoint: str
    effect_key: str | None
    args: dict[str, Any]
    logical_identity: str
    ts: float

    def as_json(self) -> str:
        return json.dumps(
            {
                "seq": self.seq,
                "endpoint": self.endpoint,
                "effect_key": self.effect_key,
                "args": self.args,
                "logical_identity": self.logical_identity,
                "ts": self.ts,
            },
            sort_keys=True,
        )


class UnknownEndpoint(KeyError):
    pass


@dataclass(slots=True)
class _Applied:
    """What the World holds for one logical identity at one endpoint."""

    label: str
    count: int
    result: dict[str, Any]
    keys: set[str] = field(default_factory=set)


class World:
    """The referee. In-process, deterministic given request order, and the only thing in a trial
    that outlives the process under test."""

    def __init__(
        self,
        endpoints: Iterable[Endpoint],
        *,
        log_path: Path | str | None = None,
    ) -> None:
        self.endpoints: dict[str, Endpoint] = {e.id: e for e in endpoints}
        self.receipts: list[Receipt] = []
        # Questions, not effects: never fsynced, never applied, but observable at the wire and
        # therefore part of "the first thing the runtime did after it came back".
        self.probes: list[dict[str, Any]] = []
        self._applied: dict[str, _Applied] = {}
        self._by_key: dict[str, _Applied] = {}
        self._labels: dict[tuple[str, str], str] = {}
        self._holds: dict[str, float] = {}
        self._log = Path(log_path) if log_path else None
        self._fh = self._log.open("a", encoding="utf8") if self._log else None

    # --- configuration the CLI and the fault spec drive ----------------------
    def set_dedup(self, endpoint_id: str, *, dedup: bool | None = None, natural: bool | None = None) -> Endpoint:
        e = self.endpoint(endpoint_id)
        new = Endpoint(
            id=e.id,
            service=e.service,
            kind=e.kind,
            dedup=e.dedup if dedup is None else dedup,
            natural=e.natural if natural is None else natural,
            logical_identity=e.logical_identity,
        )
        self.endpoints[endpoint_id] = new
        return new

    def hold(self, endpoint_id: str, ms: float) -> None:
        """Withhold the response for `ms` after the effect has been applied, so a kill can be aimed
        into the effect → acknowledgement window (§11.1). Negative means "never answer"."""
        self.endpoint(endpoint_id)
        self._holds[endpoint_id] = ms

    def hold_ms(self, endpoint_id: str) -> float:
        return self._holds.get(endpoint_id, 0.0)

    def endpoint(self, endpoint_id: str) -> Endpoint:
        try:
            return self.endpoints[endpoint_id]
        except KeyError as exc:
            raise UnknownEndpoint(endpoint_id) from exc

    # --- the one write path --------------------------------------------------
    def receive(
        self, endpoint_id: str, args: Mapping[str, Any], *, effect_key: str | None = None
    ) -> dict[str, Any]:
        """Log (and fsync) the receipt, then decide whether to apply it, then answer.

        The order of the three is the contract. A receipt that reached disk after the response was
        computed would make every kill aimed at `after:tool_effect` a guess."""
        ep = self.endpoint(endpoint_id)
        args = dict(args)
        label = self._label(ep, args)
        receipt = Receipt(
            seq=len(self.receipts) + 1,
            endpoint=ep.id,
            effect_key=effect_key,
            args=args,
            logical_identity=label,
            ts=time.time(),
        )
        self._durably_log(receipt)  # ◄── before anything is applied or computed
        if not self._should_apply(ep, label, effect_key):
            entry = self._applied.get(label)
            # A deduplicated re-fire returns the *identical* result, so a duplicate never
            # perturbs the caller's next request (§13.2).
            return dict(entry.result) if entry else self._read(ep, args)
        return self._apply(ep, label, args, effect_key)

    def _durably_log(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)
        if self._fh is None:
            return
        self._fh.write(receipt.as_json() + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def _should_apply(self, ep: Endpoint, label: str, effect_key: str | None) -> bool:
        if ep.kind == "read":
            return False  # a read changes nothing; it is still receipted
        if not ep.dedup:
            return True  # the receiver honours nothing: every request applies
        if ep.natural:
            return label not in self._applied  # upsert / PUT: identity is the key
        if effect_key is None:
            # §13.2: an unkeyed request at a `dedup:true, natural:false` endpoint applies
            # unconditionally — which is what makes F0 measure raw re-fire on every endpoint.
            return True
        return effect_key not in self._by_key

    def _apply(
        self, ep: Endpoint, label: str, args: Mapping[str, Any], effect_key: str | None
    ) -> dict[str, Any]:
        entry = self._applied.get(label)
        if entry is None:
            entry = _Applied(label=label, count=0, result=self._result(ep, label, args))
            self._applied[label] = entry
        entry.count += 1
        if effect_key is not None:
            entry.keys.add(effect_key)
            self._by_key[effect_key] = entry
        return dict(entry.result)

    def note_probe(self, endpoint: str | None, label: str | None, verdict: str) -> None:
        self.probes.append(
            {"endpoint": endpoint, "logical_identity": label, "verdict": verdict, "ts": time.time()}
        )

    # --- the read surface the oracle and the verifier use --------------------
    def applied_counts(self) -> dict[str, int]:
        """`{logical_identity: times actually applied}` — what S1 and `duplicate_effects` read."""
        return {label: entry.count for label, entry in self._applied.items()}

    def receipt_counts(self) -> dict[str, int]:
        """`{logical_identity: times received}` — `duplicate_receipts`. Always ≥ applied_counts."""
        counts: dict[str, int] = {}
        for r in self.receipts:
            counts[r.logical_identity] = counts.get(r.logical_identity, 0) + 1
        return counts

    def lookup(self, label: str) -> dict[str, Any] | None:
        entry = self._applied.get(label)
        return dict(entry.result) if entry else None

    def lookup_key(self, effect_key: str) -> dict[str, Any] | None:
        entry = self._by_key.get(effect_key)
        return dict(entry.result) if entry else None

    def label_for(self, endpoint_id: str, args: Mapping[str, Any]) -> str | None:
        """The label this request already carries, or None if the World has never seen it.

        Deliberately non-allocating. An occurrence number is a landmark — `required_effects` and
        fault triggers are written in them — so handing one to an identity that never arrived would
        renumber the effect that does arrive, and a correct run would fail S3 for a request that
        was only ever asked about.
        """
        ep = self.endpoint(endpoint_id)
        return self._labels.get((ep.id, self._identity(ep, dict(args))))

    # --- identity, results, reads -------------------------------------------
    @staticmethod
    def _identity(ep: Endpoint, args: Mapping[str, Any]) -> str:
        """What makes two requests the same effect, regardless of any key presented."""
        fields = ep.logical_identity or tuple(sorted(args))
        return json.dumps([args.get(f) for f in fields], sort_keys=True, default=str)

    def _label(self, ep: Endpoint, args: Mapping[str, Any]) -> str:
        """`endpoint#occurrence`, allocated on first arrival. Only `receive` may call this."""
        identity = self._identity(ep, args)
        cached = self._labels.get((ep.id, identity))
        if cached is not None:
            return cached
        occurrence = sum(1 for e, _ in self._labels if e == ep.id) + 1
        label = f"{ep.id}#{occurrence}"
        self._labels[(ep.id, identity)] = label
        return label

    def _result(self, ep: Endpoint, label: str, args: Mapping[str, Any]) -> dict[str, Any]:
        """`id = H(logical_identity)`, so a duplicate re-fire returns the identical object and the
        decision script cannot tell the two apart (§13.2)."""
        number = int(label.rsplit("#", 1)[1])
        ident = hashlib.sha256(label.encode()).hexdigest()[:12]
        if ep.service == "issues":
            return {
                "id": ident,
                "number": number,
                "title": args.get("title"),
                "url": f"world://{ep.id}/{number}",
                # the receiver's own id for the object; S2 and C3 join a committed effect to a
                # World entry on it, so it names the endpoint as well as the object (§5.5)
                "external_ref": label,
                "logical_identity": label,
            }
        return {"id": ident, "external_ref": label, "logical_identity": label}

    def _read(self, ep: Endpoint, args: Mapping[str, Any]) -> dict[str, Any]:
        # ponytail: `kv` is search-only. W4 (week 2) is what earns get/put.
        if ep.op == "search":
            q = str(args.get("q", ""))
            return {"hits": [f"{q} #{i}" for i in (1, 2, 3)], "logical_identity": self._label(ep, args)}
        return {"logical_identity": self._label(ep, args)}


def world_from_endpoints(decls: Sequence[Mapping[str, Any]], *, log_path: Path | str | None = None) -> World:
    """Build a World from a workload's `world.endpoints` block, without importing the workload
    models — the World is declared by the workload but does not depend on it."""
    return World(
        [
            Endpoint(
                id=d["id"],
                service=d.get("service") or str(d["id"]).split(".", 1)[0],
                kind=d.get("kind", "write"),
                dedup=bool(d.get("dedup", False)),
                natural=bool(d.get("natural", False)),
                logical_identity=tuple(d.get("logical_identity") or ()),
            )
            for d in decls
        ],
        log_path=log_path,
    )
