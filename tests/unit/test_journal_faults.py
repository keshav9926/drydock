"""What happens when the store a durable runtime is durable *into* stops answering (§28.6).

Every other fault in this project breaks something outside the runtime: a receiver, a model
provider, the process itself. These break the journal, which is the one thing Keel has no fallback
for — and the requirement is not that the run survives. It is that the run fails **safely**:

    it must not report COMPLETED       a run whose outcome was never written did not complete
    it must not lose the effect        the World's copy is the truth, and it still holds it
    the successor must see the truth   STARTED with no outcome, disposed of by effect class

The third is the one that makes this worth testing rather than assuming. A runtime that finishes
from memory after its journal went away looks *better* than one that stops — right answer, no
errors — and is the more dangerous of the two, because the next crash has nothing to recover from.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import pytest

from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.server import WorldServer
from keel import Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.core.errors import StoreUnavailable
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider
from keel.runtime import hooks
from keel.state.fold import fold

TTL = 2.0
CREATE_STEP = 3  # the EXTERNAL effect in tool_chain_1_effect


@pytest.fixture(autouse=True)
def _no_hook_leaks():
    hooks.reset()
    yield
    hooks.reset()


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    w = build_world()
    server = WorldServer(w, port=0)
    await server.start()
    monkeypatch.setattr(demo, "WORLD_URL", server.base_url)
    try:
        yield w
    finally:
        await server.stop()


def _keel(clock: FakeClock, variant: str = "EXTERNAL") -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue_tool(variant)],
        programs=[demo.tool_chain],
        clock=clock,
    )


def _break_at(boundary: str, step_index: int | None = CREATE_STEP) -> None:
    def hook(seen: str, detail: dict[str, Any]) -> None:
        if seen == boundary and (step_index is None or detail.get("step_index") == step_index):
            raise StoreUnavailable(f"store unavailable at {seen}")

    hooks.install(hook)


async def _work(k: Keel, worker_id: str = "w1") -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


async def test_the_store_dying_before_the_outcome_does_not_produce_a_completed_run(world) -> None:
    """The effect happened and the journal could not be told. That is not a completed run, and a
    runtime that says it is has turned an outage into a lie its own recovery will believe."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    _break_at("before:outcome_commit")
    await _work(k)
    hooks.reset()

    state = fold(await k.events(handle.run_id))
    assert state.phase != "COMPLETED", "a run whose outcome was never written did not complete"
    assert world.applied_counts().get("issues.create#1") == 1, "the World still holds the truth"
    assert state.steps[CREATE_STEP].state == "RUNNING", (
        "the journal must show an attempt with no outcome, which is what the successor disposes of"
    )


async def test_the_successor_recovers_the_run_the_outage_abandoned(world) -> None:
    """The point of failing safely: someone else can finish. Same journal, store working again,
    and the EXTERNAL step is resolved by probing the receiver rather than by re-firing."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    _break_at("before:outcome_commit")
    await _work(k, "w1")
    hooks.reset()  # the outage ends

    clock.advance(TTL + 2)
    assert await k.journal.reap() == [handle.run_id]
    lease = await k.journal.claim("w2", timedelta(seconds=TTL))
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(lease)

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    assert world.applied_counts()["issues.create#1"] == 1, "the recovered run must not re-file it"
    assert state.steps[CREATE_STEP].state == "RESOLVED_COMPLETED"


async def test_the_store_dying_before_the_intent_costs_nothing_at_all(world) -> None:
    """The mirror case, and the reason the write-ahead barrier is where it is. Nothing was sent,
    so nothing can have happened — the World is untouched and the step has no row."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    _break_at("before:intent_commit")
    await _work(k)
    hooks.reset()

    state = fold(await k.events(handle.run_id))
    assert world.applied_counts() == {}, "nothing was sent, so nothing may have landed"
    assert CREATE_STEP not in state.steps, "a step that was never intended has no row"


async def test_a_dead_store_never_lets_the_run_report_success_from_memory(world) -> None:
    """The dangerous failure, stated as an assertion.

    A runtime that keeps going after its journal stops answering looks better than one that stops:
    right answer, no errors, no complaints. It is worse, because the next crash has nothing to
    recover from. Break the store for the rest of the run and the phase must not reach COMPLETED.
    """
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    _break_at("after:effect_exec", step_index=None)  # every step, from the first one on
    await _work(k)
    hooks.reset()

    state = fold(await k.events(handle.run_id))
    assert state.phase != "COMPLETED"
    assert state.result is None
