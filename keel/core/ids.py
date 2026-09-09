"""Identifiers. Run ids are UUIDv7 so `runs` rows and `events` PKs are time-ordered (§23.1)."""

from __future__ import annotations

import os
import time
import uuid

RunId = uuid.UUID
ApprovalId = uuid.UUID
SignalId = uuid.UUID
EffectKey = str  # 32 hex characters — what an Idempotency-Key header expects (§5.5)


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit big-endian unix_ts_ms, version, 74 random bits.

    stdlib gains `uuid.uuid7` only in 3.14; this is the same layout.
    """
    ms = time.time_ns() // 1_000_000
    rand = os.urandom(10)
    b = bytearray(ms.to_bytes(6, "big") + rand)
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # variant 10
    return uuid.UUID(bytes=bytes(b))


def new_run_id() -> RunId:
    return uuid7()


class StepId(tuple):
    """(run_id, step_index) — the step's identity; no surrogate id."""

    __slots__ = ()

    def __new__(cls, run_id: RunId, step_index: int) -> "StepId":
        return super().__new__(cls, (run_id, step_index))

    @property
    def run_id(self) -> RunId:
        return self[0]

    @property
    def step_index(self) -> int:
        return self[1]
