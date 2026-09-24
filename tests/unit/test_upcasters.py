"""Schema evolution (§6.5): the first real upcaster, STEP_COMPLETED v1 → v2, and the load path around it.

v2 adds `cache_read_tokens` to `usage`. Stored rows are never rewritten: a v1 row is upcast at load, a
v2 writer that forgets the field is refused by the model, and an event newer than this code is not
guessed at — the worker hands the run back, with a backoff, for a worker that can read it. C4 — every
projection folds equal over v1 rows and their upcast — is `tests/property/test_fold_props.py`.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from keel import Keel, program
from keel.core.clock import FakeClock
from keel.core.errors import SchemaTooNew
from keel.events import Event
from keel.events.registry import CURRENT, body_from_payload
from keel.events.upcasters import step_completed_v1_to_v2
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import Decision, ScriptedProvider
from keel.replay.fixtures import load_all
from keel.runtime.worker import SCHEMA_BACKOFF_S

V1_USAGE = {"input_tokens": 120, "output_tokens": 30}


def test_the_upcaster_is_pure_and_reads_no_cache() -> None:
    raw = {"type": "STEP_COMPLETED", "schema_version": 1, "step_index": 0, "attempt_no": 1, "usage": dict(V1_USAGE)}
    up = step_completed_v1_to_v2(raw)
    assert up["usage"] == {**V1_USAGE, "cache_read_tokens": 0} and up["schema_version"] == 2
    assert raw["usage"] == V1_USAGE and raw["schema_version"] == 1, "the caller's dict is untouched"
    assert step_completed_v1_to_v2({**raw, "usage": None})["usage"] is None, "no usage, nothing to add"
    assert CURRENT["STEP_COMPLETED"] == 2 and CURRENT["STEP_FAILED"] == 1


def test_the_load_path_upcasts_refuses_a_forgetful_writer_and_a_newer_row() -> None:
    body = body_from_payload("STEP_COMPLETED", 1, {"step_index": 0, "attempt_no": 1, "usage": V1_USAGE})
    assert body.usage["cache_read_tokens"] == 0
    with pytest.raises(ValidationError, match="cache_read_tokens"):
        body_from_payload("STEP_COMPLETED", 2, {"step_index": 0, "attempt_no": 1, "usage": V1_USAGE})
    with pytest.raises(SchemaTooNew):
        body_from_payload("STEP_COMPLETED", 3, {"step_index": 0, "attempt_no": 1})


def test_archived_journals_are_upcast_at_load_and_never_rewritten() -> None:
    fixtures = load_all(Path(__file__).resolve().parents[1] / "journals")
    completed = [e for f in fixtures for e in f.events if e.type == "STEP_COMPLETED" and e.body.usage]
    assert completed, "the fixtures carry model usage to upcast"
    assert {e.env.schema_version for e in completed} == {1}, "the stored version is what was written"
    assert all(e.body.usage["cache_read_tokens"] == 0 for e in completed)


@program(name="upcast_asker", version="1.0")
async def asker(ctx: Any, args: dict[str, Any]) -> str:
    return (await ctx.model([{"role": "user", "content": "q"}], name="ask")).text


async def test_a_worker_hands_back_a_run_it_cannot_read() -> None:
    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), provider=ScriptedProvider([Decision(text="a")] * 2),
             programs=[asker], clock=clock)
    first = await k.run(asker, {})
    assert first.phase == "COMPLETED"
    written = [e for e in await k.events(first.run_id) if e.type == "STEP_COMPLETED"]
    assert written and all(e.env.schema_version == 2 for e in written), "every writer emits CURRENT"
    assert written[0].body.usage.keys() >= {"input_tokens", "cache_read_tokens", "output_tokens"}

    # A newer Keel wrote one of this run's rows: this worker has no downcaster for it.
    handle = await k.start(asker, {})
    stored = k.journal._events[handle.run_id]
    stored[0] = Event(env=stored[0].env.model_copy(update={"schema_version": CURRENT["RUN_CREATED"] + 1}),
                      body=stored[0].body)
    lease = await k.journal.claim("old-worker", timedelta(seconds=2))
    assert lease is not None and lease.run_id == handle.run_id
    await k.worker(worker_id="old-worker", lease_ttl=2.0).execute(lease)
    row = await k.journal.run_row(handle.run_id)
    assert row.lease_expires_at is None and row.runnable_at == clock.now() + timedelta(seconds=SCHEMA_BACKOFF_S)
    assert [r.outcome for r in await k.journal.recoveries(handle.run_id)] == ["RELEASED"]
    assert len(k.journal._events[handle.run_id]) == 1, "nothing journaled by a worker that could not read"
    assert await k.journal.claim("old-worker", timedelta(seconds=2)) is None, "the backoff holds"
