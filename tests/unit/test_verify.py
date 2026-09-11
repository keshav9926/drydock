"""VERIFY: the program still agrees with its journal (§10.9, §28.5).

The case that matters is not the clean one. It is a journal that *recovered* — a step that timed
out, went ambiguous, was probed and found to have landed. If VERIFY or the logical projection hash
treated that as different from a step that completed on the first attempt, C1 would fail every trial
that recovered, which is every trial worth running.

The three outcomes VERIFY has, each proved here: a pass with `live_from_step`, a `FAIL` with a diff
when the program changed, and a *stop* on an open step rather than resolving it — because
resolution is a write and VERIFY holds no lease.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import pytest

from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.server import WorldServer
from keel import Budget, Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider
from keel.replay.determinism import logical_projection_hash, normalise
from keel.replay.verify import diff_projections, raise_for_drift, verify
from keel.state.fold import fold

TTL = 2.0
HOLD_MS = 400


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


async def _verify(k: Keel, run_id: Any, program: Any = demo.tool_chain, **kw: Any):
    return await verify(k.journal, run_id, program, tools=k.tools, **kw)


# --- the clean case, so the interesting ones have something to differ from ---


async def test_a_completed_run_verifies_and_costs_nothing(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    result = await k.run(demo.tool_chain, {"task": "file an issue"}, budget=Budget(max_tokens=50_000))
    assert result.phase == "COMPLETED"

    before = len(await k.events(result.run_id))
    applied = dict(world.applied_counts())

    out = await _verify(k, result.run_id)
    assert out.ok and out.status == "PASS"
    assert out.replayed_steps == 5
    assert out.projection_hash is not None

    # No tokens, no effects, no lease: the journal is the same length and the world did not move.
    assert len(await k.events(result.run_id)) == before
    assert world.applied_counts() == applied


# --- the case the phase exists for ------------------------------------------


async def test_a_recovered_run_verifies_and_hashes_like_a_clean_one(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that crashed, went ambiguous and probed its way to the answer is *logically* the same
    run as one that never crashed. §10.5 normalises RESOLVED_COMPLETED to COMPLETED for exactly
    this reason, and this is the assertion that keeps it honest."""
    import asyncio

    server_url = demo.WORLD_URL
    # A *fresh* World for the clean run. The World labels effects by ordinal, so a second run
    # against the same receiver files `issues.create#2` and the two runs would differ in their
    # results for a reason that has nothing to do with recovery.
    clean_world = build_world()
    clean_server = WorldServer(clean_world, port=0)
    await clean_server.start()
    try:
        monkeypatch.setattr(demo, "WORLD_URL", clean_server.base_url)
        clean = _keel(FakeClock())
        clean_result = await clean.run(
            demo.tool_chain, {"task": "file an issue"}, budget=Budget(max_tokens=50_000)
        )
        clean_state = fold(await clean.events(clean_result.run_id))
    finally:
        await clean_server.stop()
    monkeypatch.setattr(demo, "WORLD_URL", server_url)

    clock = FakeClock()
    k = _keel(clock)
    world.hold("issues.create", HOLD_MS)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    task = asyncio.create_task(k.worker(worker_id="w1", lease_ttl=TTL).execute(lease))
    for _ in range(400):
        if world.receipt_counts().get("issues.create#1"):
            break
        await asyncio.sleep(0.005)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    clock.advance(TTL + 2)
    assert await k.journal.reap() == [handle.run_id]
    lease2 = await k.journal.claim("w2", timedelta(seconds=TTL))
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(lease2)

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    assert state.steps[3].state == "RESOLVED_COMPLETED", "this run really did recover"
    assert normalise(state.steps[3].state) == "COMPLETED"

    out = await _verify(k, handle.run_id)
    assert out.ok, out.diff
    assert out.projection_hash == logical_projection_hash(clean_state), (
        "a run that crashed four times and probed its way to the answer is the same run"
    )
    assert diff_projections(state, clean_state) == []


async def test_verify_stops_on_an_open_step_instead_of_resolving_it(world) -> None:
    """An ambiguous step with no outcome is a decision about the world. VERIFY has no lease and no
    standing to make one, so it reports where it stopped (§10.9)."""
    import asyncio

    clock = FakeClock()
    k = _keel(clock)
    world.hold("issues.create", HOLD_MS)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    task = asyncio.create_task(k.worker(worker_id="w1", lease_ttl=TTL).execute(lease))
    for _ in range(400):
        if world.receipt_counts().get("issues.create#1"):
            break
        await asyncio.sleep(0.005)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    before = len(await k.events(handle.run_id))
    applied = dict(world.applied_counts())

    out = await _verify(k, handle.run_id)
    assert out.ok, out.diff
    assert out.stopped == "in_flight_running", out.stopped
    assert out.projection_hash is None, "a run still in flight has no final projection"
    assert len(await k.events(handle.run_id)) == before, "VERIFY appended something"
    assert world.applied_counts() == applied, "VERIFY touched the world"


# --- the failure the whole mode exists to catch ------------------------------


async def test_a_reordered_program_fails_with_the_step_that_disagrees(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    result = await k.run(demo.tool_chain, {"task": "file an issue"}, budget=Budget(max_tokens=50_000))

    async def reordered(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        """A redeploy that calls the tool before asking the model. Same steps, wrong order."""
        await ctx.tool("search", query="anything")
        return await demo.tool_chain(ctx, args)

    out = await _verify(k, result.run_id, reordered)
    assert not out.ok
    assert out.diff is not None and out.diff["step_index"] == 0
    assert out.diff["journaled"][0] == "MODEL" and out.diff["issued"][0] == "TOOL"


async def test_a_prompt_edit_is_drift_and_not_a_failure(world) -> None:
    """A parked run must survive a one-line prompt edit: MODEL identity is `(kind, name)` on
    purpose. The diff is still reported, and `--strict` is what makes it fatal."""
    from keel.core.errors import PromptDrift

    clock = FakeClock()
    k = _keel(clock)
    result = await k.run(demo.tool_chain, {"task": "file an issue"}, budget=Budget(max_tokens=50_000))

    async def edited(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        return await demo.tool_chain(ctx, {**args, "task": "file an issue, politely"})

    out = await _verify(k, result.run_id, edited)
    assert out.ok, "a prompt edit must not fail VERIFY"
    assert out.drift and out.drift[0].step_index == 0
    with pytest.raises(PromptDrift):
        raise_for_drift(out)
