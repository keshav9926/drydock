"""Continuation segments (§4.9, §10.8, §18.3): recovery bounded by segment length, not run length.

What a boundary is: SEGMENT_STARTED{segment_no, first_step_index, program_version, state_blob,
compact_seq} and the plan's `init` snapshot, one transaction. What it promises: re-execution starts
there, with the blob as the program's input and the step counter where it was — never reset — and
the Keel-owned projections rebuildable from it alone (C2). What it refuses: a blob the program's
current model cannot read, which suspends the run with the validation error before any step.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import pytest
from pydantic import BaseModel

from crashproof.verifier import invariants
from keel import Continue, Keel, program
from keel.core.clock import FakeClock
from keel.core.errors import IllegalTransition
from keel.events import SegmentStarted
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import Decision, ScriptedProvider
from keel.replay.verify import verify
from keel.runtime import hooks
from keel.state.fold import fold

TTL = 2.0
#: (ctx.step_index, state.i) at every entry into `counter` — how a test sees where re-execution began.
ENTRIES: list[tuple[int, int | None]] = []


class Count(BaseModel):
    i: int = 0
    seen: list[int] = []


@program(name="counter", version="1.0", state=Count)
async def counter(ctx: Any, args: dict[str, Any], state: Count | None = None) -> Any:
    ENTRIES.append((ctx.step_index, state.i if state else None))
    state = state or Count()
    if state.i == 0:
        await ctx.plan.init(["first half", "second half"])
    while state.i < args["n"]:
        ctx.segment_point(state)
        await ctx.random()
        state.seen.append(state.i)
        state.i += 1
        if state.i == args["n"] // 2:
            await ctx.plan.complete(ctx.plan.items[0]["id"])
            await ctx.compact()
        if args.get("every") and state.i % args["every"] == 0 and state.i < args["n"]:
            return Continue(state)
    return {"i": state.i, "seen": state.seen, "plan": [i["status"] for i in ctx.plan.items]}


class Renamed(BaseModel):
    """A redeploy that renamed `i` without the upcasting validator §18.3 asks for."""

    count: int
    seen: list[int] = []


@program(name="counter", version="2.0", state=Renamed)
async def counter_v2(ctx: Any, args: dict[str, Any], state: Renamed | None = None) -> Any:
    raise AssertionError("never re-executed: the schema check runs first")


def _keel(clock: FakeClock, prog: Any = counter) -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider([Decision(text="summary") for _ in range(4)]),
        programs=[prog],
        clock=clock,
    )


async def _work(k: Keel, worker_id: str, **worker: Any) -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL, **worker).execute(lease)


def _c2(events: list[Any]) -> str:
    journal = [{"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(), "step_index": e.step_index,
                "attempt_no": e.attempt_no, "body": e.body.model_dump(mode="json")} for e in events]
    return invariants.verify(invariants.TrialFacts(journal=journal)).as_dict()["C2"]


async def test_continue_journals_a_boundary_and_the_counter_never_resets() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(counter, {"n": 6, "every": 2})
    await _work(k, "w1")
    events = await k.events(handle.run_id)
    state = fold(events)

    assert state.phase == "COMPLETED"
    assert state.result == {"i": 6, "seen": [0, 1, 2, 3, 4, 5], "plan": ["completed", "pending"]}
    segs = [e for e in events if e.type == "SEGMENT_STARTED"]
    assert [(e.body.segment_no, e.body.first_step_index) for e in segs] == [(1, 3), (2, 7)]
    assert [e.body.state_blob["i"] for e in segs] == [2, 4], "the program's state, and only that"
    assert all(e.body.program_version == counter.version for e in segs)
    intents = [e.body.step_index for e in events if e.type == "STEP_INTENDED"]
    assert intents == list(range(len(intents))), "step indices continue across boundaries"
    for seg in segs:
        snapshot = next(e for e in events if e.seq == seg.seq + 1)
        assert (snapshot.type, snapshot.body.op, snapshot.body.step_index) == ("PLAN_UPDATED", "init", None)
        assert "plan" not in seg.body.state_blob, "the plan is Keel-owned and never in the blob"
    # The second boundary follows the compaction at i=3: it names that summary, and the context it
    # resets to is that summary alone.
    compact = next(s for s in state.steps.values() if s.kind == "COMPACT")
    assert (segs[0].body.compact_seq, segs[1].body.compact_seq) == (None, compact.outcome_seq)
    assert state.segment.segment_no == 2 and state.segment_context == [{"role": "summary", "content": "summary"}]
    assert _c2(events) == "PASS"

    out = await verify(k.journal, handle.run_id, counter)
    assert out.ok and out.replayed_steps == 2, "VERIFY replays the last segment only"


async def test_recovery_re_executes_from_the_latest_boundary_only() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(counter, {"n": 6, "every": 2})

    def die(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:intent_commit" and detail.get("step_index") == 8:
            raise hooks.Crash("killed in segment 2")

    ENTRIES.clear()
    hooks.install(die)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()
    clock.advance(TTL + 1)
    await k.journal.reap()
    ENTRIES.clear()
    await _work(k, "w2")

    events = await k.events(handle.run_id)
    rec = [e for e in events if e.type == "RECOVERY_STARTED"][-1]
    assert rec.body.from_segment == 2
    assert ENTRIES == [(7, 4)], "called once, with the boundary's state, the counter at its first_step_index"
    state = fold(events)
    assert state.phase == "COMPLETED" and state.result["seen"] == [0, 1, 2, 3, 4, 5]
    assert _c2(events) == "PASS"
    assert (await verify(k.journal, handle.run_id, counter)).ok


async def test_a_crash_before_the_segment_write_re_executes_the_previous_segment() -> None:
    """`before:segment_write`: nothing of the boundary committed. The successor replays the previous
    segment from memo, the program returns the same `Continue(state)`, and the boundary is written
    once — `events_segment_once` would refuse a second."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(counter, {"n": 6, "every": 2})
    fired: list[int] = []

    def die(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:segment_write" and not fired:
            fired.append(detail["segment_no"])
            raise hooks.Crash("killed writing the boundary")

    hooks.install(die)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()
    assert fired == [1] and fold(await k.events(handle.run_id)).segment is None, "no torn boundary"
    clock.advance(TTL + 1)
    await k.journal.reap()
    await _work(k, "w2")
    events = await k.events(handle.run_id)
    assert [e.body.segment_no for e in events if e.type == "SEGMENT_STARTED"] == [1, 2]
    assert fold(events).phase == "COMPLETED" and _c2(events) == "PASS"


async def test_a_forced_boundary_falls_at_the_first_safe_point_after_n_steps() -> None:
    """No `Continue`: Keel cuts at the first `ctx.segment_point` once the segment has issued N steps,
    before the next step's INTENT. N is worker configuration — a successor with another N replays
    the same journal without a nondeterminism in sight."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(counter, {"n": 6})

    def die(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:intent_commit" and detail.get("step_index") == 5:
            raise hooks.Crash("killed after the first forced boundary")

    hooks.install(die)
    try:
        await _work(k, "w1", segment_steps=3)
    finally:
        hooks.reset()
    segs = [e for e in await k.events(handle.run_id) if e.type == "SEGMENT_STARTED"]
    assert [(e.body.segment_no, e.body.first_step_index, e.body.state_blob["i"]) for e in segs] == [(1, 3, 2)]
    clock.advance(TTL + 1)
    await k.journal.reap()
    await _work(k, "w2", segment_steps=400)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED" and _c2(events) == "PASS"
    assert (await verify(k.journal, handle.run_id, counter)).ok


async def test_a_state_the_new_model_cannot_read_suspends_before_any_step() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(counter, {"n": 6, "every": 2})

    def die(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:intent_commit" and detail.get("step_index") == 4:
            raise hooks.Crash("killed in segment 1")

    hooks.install(die)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()
    steps_before = len(fold(await k.events(handle.run_id)).steps)

    k.register(counter_v2)  # the redeploy
    clock.advance(TTL + 1)
    await k.journal.reap()
    await _work(k, "w2")
    events = await k.events(handle.run_id)
    state = fold(events)
    assert (state.phase, state.suspended_reason) == ("SUSPENDED", "state_schema_mismatch")
    assert state.suspended_detail["segment_no"] == 1 and "count" in state.suspended_detail["error"]
    tail = [e.type for e in events if e.lease_epoch == 2]
    assert tail[0] == "RECOVERY_STARTED" and tail[-1] == "RUN_SUSPENDED"
    assert len(state.steps) == steps_before, "checked at acquisition, before any step"

    out = await verify(k.journal, handle.run_id, counter_v2, requested_by="ci")
    assert not out.ok and out.error.startswith("StateSchemaMismatch")
    assert (await k.journal.replays(handle.run_id))[-1].result == "STATE_SCHEMA_MISMATCH"


async def test_the_memory_journal_refuses_a_second_boundary_with_the_same_number() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(counter, {"n": 6, "every": 2})
    await _work(k, "w1")
    lease = await k.journal.acquire(handle.run_id, "w9", timedelta(seconds=TTL))
    with pytest.raises(IllegalTransition, match="events_segment_once|second SEGMENT_STARTED"):
        async with k.journal.append(lease) as tx:
            await tx.append(SegmentStarted(segment_no=1, first_step_index=99, program_version="x"))


def test_c2_fails_a_boundary_that_is_not_rebuildable_from_itself() -> None:
    """The verifier's side of C2, on hand-made journals: a stale plan snapshot, a `compact_seq`
    naming the wrong summary, and a counter that reset are each a FAIL; no boundary is N/A."""
    def ev(seq: int, type_: str, step: int | None = None, **body: Any) -> dict[str, Any]:
        return {"seq": seq, "type": type_, "step_index": step, "body": {"step_index": step, **body} if step is not None else body}

    item = {"id": "0.0", "title": "a", "status": "pending", "created_at_step": 0, "notes": []}
    done = {**item, "status": "completed"}
    base = [
        ev(1, "RUN_CREATED", args={}),
        ev(2, "STEP_INTENDED", 0, kind="PLAN", name="plan.init"),
        ev(3, "PLAN_UPDATED", 0, op="init", diff={"items": [item]}),
        ev(4, "STEP_INTENDED", 1, kind="PLAN", name="plan.complete"),
        ev(5, "PLAN_UPDATED", 1, op="complete", diff={"id": "0.0"}),
        ev(6, "STEP_INTENDED", 2, kind="COMPACT", name="compact"),
        ev(7, "STEP_COMPLETED", 2, result={"text": "s1"}),
    ]

    def verdict(journal: list[dict[str, Any]]) -> str:
        return invariants.verify(invariants.TrialFacts(journal=journal)).as_dict()["C2"]

    good = [*base, ev(8, "SEGMENT_STARTED", segment_no=1, first_step_index=3, compact_seq=7),
            ev(9, "PLAN_UPDATED", None, op="init", diff={"items": [done]})]
    assert verdict(good) == "PASS"
    stale = [*base, ev(8, "SEGMENT_STARTED", segment_no=1, first_step_index=3, compact_seq=7),
             ev(9, "PLAN_UPDATED", None, op="init", diff={"items": [item]})]
    assert verdict(stale) == "FAIL"
    wrong_summary = [*base, ev(8, "SEGMENT_STARTED", segment_no=1, first_step_index=3, compact_seq=None),
                     ev(9, "PLAN_UPDATED", None, op="init", diff={"items": [done]})]
    assert verdict(wrong_summary) == "FAIL"
    reset = [*base, ev(8, "SEGMENT_STARTED", segment_no=1, first_step_index=0, compact_seq=7),
             ev(9, "PLAN_UPDATED", None, op="init", diff={"items": [done]})]
    assert verdict(reset) == "FAIL"
    assert verdict(base) == "N/A"
    assert invariants.verify(invariants.TrialFacts()).as_dict()["C2"] == "N/A"
