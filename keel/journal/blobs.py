"""Content-addressed blob store and the 32 KiB externalisation rule (§5.3, §6.1).

Blobs are written **before** the fenced append that references them, in their own transaction —
never inside it. A fenced or crashed writer can then leave at most an orphan blob (harmless,
collected with retention), never an event pointing at a missing blob. There is no FK from
`events.blob_ids` to `blobs`; integrity is by immutability — a hash never changes meaning.
"""

from __future__ import annotations

import hashlib
from typing import Any

from keel.core.hashing import canonical_json
from keel.journal.protocol import BlobStore

BLOB_THRESHOLD = 32 * 1024
_MARK = "__keel_blob__"


def blob_id_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MemoryBlobStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, data: bytes, *, media_type: str = "application/json") -> str:
        bid = blob_id_of(data)
        self._blobs.setdefault(bid, data)  # ON CONFLICT DO NOTHING
        return bid

    async def get(self, blob_id: str) -> bytes:
        return self._blobs[blob_id]


async def externalise(payload: dict[str, Any], store: BlobStore) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Replace any top-level field over 32 KiB with a blob reference."""
    out = dict(payload)
    ids: list[str] = []
    for key, value in payload.items():
        if value is None or isinstance(value, (int, float, bool)):
            continue
        raw = canonical_json(value).encode()
        if len(raw) <= BLOB_THRESHOLD:
            continue
        bid = await store.put(raw)
        out[key] = {_MARK: True, "blob_id": bid, "media_type": "application/json", "size_bytes": len(raw)}
        ids.append(bid)
    return out, tuple(ids)


async def internalise(payload: dict[str, Any], store: BlobStore) -> dict[str, Any]:
    """Dereference blob refs on load. Eager at MVP: a run's payloads are small enough that lazy
    dereference would be an optimisation with no measurement behind it (§4)."""
    if not any(isinstance(v, dict) and v.get(_MARK) for v in payload.values()):
        return payload
    import json

    out = dict(payload)
    for key, value in payload.items():
        if isinstance(value, dict) and value.get(_MARK):
            out[key] = json.loads(await store.get(value["blob_id"]))
    return out
