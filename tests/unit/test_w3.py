"""W3 `long_horizon_50` in the neutral vocabulary, and its Keel binding end to end (§14.1, §29.2).

The loop node is the one addition to the script vocabulary: `repeat: 50` answers the key [] plus k
answered `kv_put`s with `@n` = k, and `then` after the fiftieth — still a pure function of the
answered-tools key. The run below is the Keel program against a MemoryJournal and an in-process World,
driven through the timer sweep: 50 puts applied once each, three segments, five plan items completed,
the sleep honoured by the store's clock, C1 and C2 PASS.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from typing import Any

import pytest

from crashproof.adapters.keel import WorkloadProvider, program_of
from crashproof.runner.bench import Matrix
from crashproof.verifier import invariants
from crashproof.workloads.spec import load_named
from crashproof.world.server import WorldServer
from crashproof.world.services import world_from_endpoints
from keel import Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.replay.verify import verify
from keel.state.fold import fold

W3 = load_named("long_horizon_50")


def test_the_loop_node_answers_each_round_and_then_the_final() -> None:
    def key(k: int) -> tuple[tuple[str, int], ...]:
        return tuple(("kv_put", i + 1) for i in range(k))

    assert W3.node_for(key(0)).decision["tool_calls"] == [{"name": "kv_put", "args": {"key": "counter", "value": 0}}]
    assert W3.node_for(key(23)).decision["tool_calls"][0]["args"] == {"key": "counter", "value": 23}
    assert W3.node_for(key(50)).decision == {"final": "counter=@kv_put.result.value"}
    assert W3.node_for(key(51)) is None and W3.node_for((("search", 1),)) is None
    assert W3.expected_occurrences("tool:kv_put") == 50
    assert W3.expected_occurrences("model:*") == 51
    assert W3.landmarks() == ("model:start", "tool:kv_put")
    assert program_of(W3) is demo.long_horizon


def test_the_w3_matrix_aims_mid_segment() -> None:
    matrix = Matrix.load("bench/specs/w3.yaml")
    cells = {c.trigger: c for c in matrix.cells()}
    assert set(cells) == {"baseline", "kill@after:tool_effect", "pause_past_ttl@before:tool_call"}
    [fault] = cells["kill@after:tool_effect"].spec.faults
    assert (fault.trigger.landmark, fault.trigger.occurrence) == ("tool:kv_put", 23)


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    w = world_from_endpoints(W3.endpoint_decls())
    server = WorldServer(w, port=0)
    await server.start()
    monkeypatch.setattr(demo, "WORLD_URL", server.base_url)
    try:
        yield w
    finally:
        await server.stop()


async def test_long_horizon_50_end_to_end_on_the_memory_journal(world) -> None:
    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), provider=WorkloadProvider(W3), tools=[demo.kv_put],
             programs=[demo.long_horizon], clock=clock)
    handle = await k.start(demo.long_horizon, W3.input)

    async def work() -> bool:
        lease = await k.journal.claim("w", timedelta(seconds=30))
        if lease is None:
            return False
        with contextlib.suppress(BaseException):
            await k.worker(worker_id="w", lease_ttl=30).execute(lease)
        return True

    await work()
    row = await k.journal.run_row(handle.run_id)
    assert row.phase == "SLEEPING", "parked after the put of 25"
    clock.advance(2)
    assert await k.journal.sweep_timers() == 1
    await work()

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED"
    assert state.result == {"answer": "counter=49", "iterations": 50, "plan_completed": 5}
    assert world.applied_counts() == W3.variant("IDEMPOTENT").world_state
    # init, then 2 steps a round, +2 (compact, plan) every 10 rounds, +1 (the sleep) after round 26.
    assert [e.body.first_step_index for e in events if e.type == "SEGMENT_STARTED"] == [45, 90]
    assert sum(1 for s in state.steps.values() if s.kind == "COMPACT") == 5
    [sleep] = [s for s in state.steps.values() if s.kind == "SLEEP"]
    started = next(e for e in events if e.type == "STEP_ATTEMPT_STARTED" and e.step_index == sleep.step_index)
    assert datetime.fromisoformat(sleep.result["woke_at"]) >= started.body.started_at + timedelta(seconds=2)
    journal: list[dict[str, Any]] = [
        {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(), "step_index": e.step_index,
         "attempt_no": e.attempt_no, "body": e.body.model_dump(mode="json")} for e in events
    ]
    assert invariants.verify(invariants.TrialFacts(journal=journal)).as_dict()["C2"] == "PASS"
    assert (await verify(k.journal, handle.run_id, demo.long_horizon, tools=k.tools)).ok
