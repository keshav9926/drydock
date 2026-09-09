"""The envelope every journaled event carries, and the (envelope, body) pair that is one row (§6.1).

`event_id = (run_id, seq)`; there is no surrogate id, because the pair *is* the ordering.
The envelope holds what is identical for every type; `type`, `step_index` and `attempt_no` are
denormalised out of the body by the Postgres journal so partial unique indexes can express the
step-lifecycle invariants (§5.3) — they are not duplicated here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from keel.events.schema import EventBody


class Envelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    seq: int
    ts: AwareDatetime
    schema_version: int
    lease_epoch: int  # 0 only for RUN_CREATED
    program_version: str
    trace_id: UUID  # root run id of the delegation tree
    causation_seq: int | None = None
    blob_ids: tuple[str, ...] = ()


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: Envelope
    body: EventBody

    @property
    def type(self) -> str:
        return self.body.type

    @property
    def seq(self) -> int:
        return self.env.seq

    @property
    def run_id(self) -> UUID:
        return self.env.run_id

    @property
    def ts(self) -> datetime:
        return self.env.ts

    @property
    def lease_epoch(self) -> int:
        return self.env.lease_epoch

    @property
    def step_index(self) -> int | None:
        return getattr(self.body, "step_index", None)

    @property
    def attempt_no(self) -> int | None:
        return getattr(self.body, "attempt_no", None)
