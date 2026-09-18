"""W7 `streaming_answer` in the neutral vocabulary, and its Keel binding end to end (§14.1, §29.2).

    m1 streamed (40 chunks) -> fetch_log (PURE, STREAMS, partial_ok) -> m2 streamed final

The run below is the Keel form against a MemoryJournal and an in-process World: every model call and
the read stream, the answer is the scripted full response, and the chunks are journaled beside it.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta

import pytest

from crashproof.adapters.keel import WorkloadProvider, _build_tool, program_of
from crashproof.runner.bench import Matrix
from crashproof.workloads.spec import load_named
from crashproof.world.client import WorldClient
from crashproof.world.server import WorldServer
from crashproof.world.services import world_from_endpoints
from keel import Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.core.protocols import EffectClass, Idempotency, Modifier, ProbeResult
from keel.effects.registry import ToolCtx, tool
from keel.journal.memory import MemoryJournal
from keel.replay.verify import verify
from keel.state.fold import fold

W7 = load_named("streaming_answer")
FINAL = W7.script[1].decision["final"]


def test_the_workload_declares_a_streamed_read_and_two_streamed_answers() -> None:
    [decl] = W7.tools_for("STREAMS")
    assert (decl.effect_class, decl.modifiers, decl.partial_ok) == ("PURE", ("STREAMS",), True)
    assert W7.node_for(()).decision["chunks"] == 40
    assert W7.landmarks() == ("model:start", "model:fetch_log1", "tool:fetch_log")
    assert W7.expected_occurrences("model:*") == 2 and W7.expected_occurrences("tool:fetch_log") == 1
    assert program_of(W7) is demo.tool_chain and W7.input["stream"] is True


def test_the_w7_matrix_is_section_14_2s_twelve_pairs() -> None:
    cells = {c.trigger: c for c in Matrix.load("bench/specs/w7.yaml").cells()}
    assert len(cells) == 13 and "baseline" in cells
    for trigger in ("kill@during:model_stream(chunk=7)", "model_stream_truncate@during:model_stream(chunk=7)"):
        [fault] = cells[trigger].spec.faults
        assert (fault.trigger.landmark, fault.trigger.occurrence) == ("model:*", 1), "m1, the 40-chunk stream"


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    w = world_from_endpoints(W7.endpoint_decls())
    server = WorldServer(w, port=0)
    await server.start()
    try:
        yield w, server.base_url
    finally:
        await server.stop()


async def test_streaming_answer_end_to_end_on_the_memory_journal(world) -> None:
    w, url = world
    [decl] = W7.tools_for("STREAMS")
    fetch_log = _build_tool(decl, "none", WorldClient(url), None, tool, ToolCtx, EffectClass, Idempotency, ProbeResult)
    assert fetch_log.modifiers == {Modifier.STREAMS} and fetch_log.partial_ok
    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), provider=WorkloadProvider(W7), tools=[fetch_log],
             programs=[demo.tool_chain], clock=clock)
    handle = await k.start(demo.tool_chain, W7.input)
    lease = await k.journal.claim("w", timedelta(seconds=30))
    with contextlib.suppress(BaseException):
        await k.worker(worker_id="w", lease_ttl=30).execute(lease)

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED" and state.result == {"answer": FINAL}, "the scripted full response"
    chunked = {e.step_index for e in events if e.type == "STEP_CHUNK"}
    assert chunked == {0, 1, 2}, "both model calls and the read streamed"
    m1 = "".join(e.body.blob for e in events if e.type == "STEP_CHUNK" and e.step_index == 0)
    assert m1.startswith(W7.script[0].decision["text"]) and "fetch_log" in m1, "the text, then the call"
    assert state.steps[1].result["lines"][2].endswith("test_retry_backoff FAILED: timeout after 2.0s")
    assert w.receipt_counts() == {"logs.fetch#1": 1} and w.applied_counts() == {}, "no write effect"
    assert (await verify(k.journal, handle.run_id, demo.tool_chain, tools=k.tools)).ok
