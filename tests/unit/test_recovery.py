"""Crash, recover, and let the World say what really happened (§28.1, §28.2).

Day 1's "done when" — kill the worker mid-run, start another, two work sessions, every earlier step
reused, zero model calls repeated — now judged against ground truth outside the runtime instead of
against the runtime's own word. Both published bands of matrix v0 are here:

    EXTERNAL   @ issues.create (dedup: false)               ambiguity surfaced and probed
    IDEMPOTENT @ issues.upsert (dedup: true, natural: true) re-fired under the same key, applied once
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta

import pytest

from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.server import WorldServer
from keel import Budget, Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider

TTL = 2.0
HOLD_MS = 400  # the World withholds the response, so the kill lands after the effect, before the ack


class CountingProvider(ScriptedProvider):
    """A model that answers from request content only — and counts, so the test can assert that a
    recovered run does not re-ask a question it already has an answer to."""

    def __init__(self, script) -> None:
        super().__init__(script)
        self.calls = 0

    async def complete(self, req):
        self.calls += 1
        return await super().complete(req)


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


def _keel(clock: FakeClock, provider, variant: str = "EXTERNAL") -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=provider,
        tools=[demo.search, demo.create_issue_tool(variant)],
        programs=[demo.tool_chain],
        clock=clock,
    )


async def _run_until_effect_lands(k: Keel, world, endpoint: str) -> None:
    """Start epoch 1 and kill it the moment the World has the receipt and the worker has not been
    told — the window the whole project is about. Aimed by watching the receiver, never by sleeping.
    """
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    assert lease is not None
    task = asyncio.create_task(k.worker(worker_id="w1", lease_ttl=TTL).execute(lease))
    for _ in range(400):
        if world.receipt_counts().get(f"{endpoint}#1"):
            break
        await asyncio.sleep(0.005)
    assert world.receipt_counts().get(f"{endpoint}#1"), "the effect never landed; nothing to resolve"
    task.cancel()  # SIGKILL-shaped: no release, no outcome event
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _take_over(k: Keel, clock: FakeClock, run_id) -> None:
    """The lease lapses, the reaper orphans, a successor claims and re-executes."""
    clock.advance(TTL + 1 + 1)  # past both lease_expires_at and attempt_deadline
    assert await k.journal.reap() == [run_id]
    lease2 = await k.journal.claim("w2", timedelta(seconds=TTL))
    assert lease2 is not None and lease2.cause == "ORPHANED"
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(lease2)


async def test_clean_run(world) -> None:
    clock = FakeClock()
    provider = CountingProvider(demo.SCRIPT)
    k = _keel(clock, provider)
    result = await k.run(demo.tool_chain, {"task": "file an issue"}, budget=Budget(max_tokens=50_000))
    assert result.phase == "COMPLETED"
    assert result.result == {"answer": "filed the issue"}
    assert provider.calls == 3
    assert world.applied_counts() == {"issues.create#1": 1}


async def test_crash_after_effect_resumes_without_redeciding(world) -> None:
    clock = FakeClock()
    provider = CountingProvider(demo.SCRIPT)
    k = _keel(clock, provider)
    world.hold("issues.create", HOLD_MS)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    await _run_until_effect_lands(k, world, "issues.create")
    assert provider.calls == 2
    events = await k.events(handle.run_id)
    assert [e.type for e in events][-1] == "STEP_ATTEMPT_STARTED"  # STARTED, no outcome

    await _take_over(k, clock, handle.run_id)

    view = await k.get(handle.run_id)
    assert view.phase == "COMPLETED"
    assert world.applied_counts()["issues.create#1"] == 1, "the recovered run must not re-fire"
    assert world.receipt_counts()["issues.create#1"] == 1
    assert provider.calls == 3, "only the one live model step may be asked"

    steps = [(s.step_index, s.kind, s.state, s.origin) for s in view.steps]
    assert steps[0] == (0, "MODEL", "COMPLETED", "memo")
    assert steps[1] == (1, "TOOL", "COMPLETED", "memo")
    assert steps[2] == (2, "MODEL", "COMPLETED", "memo")
    assert steps[3] == (3, "TOOL", "RESOLVED_COMPLETED", "recovered")
    assert steps[4] == (4, "MODEL", "COMPLETED", "live")

    types = [e.type for e in await k.events(handle.run_id)]
    assert types.count("RECOVERY_STARTED") == 2, "two work sessions"
    assert "STEP_AMBIGUOUS" in types and "STEP_RESOLVED" in types

    effect = next(e for e in view.effects if e.step_index == 3)
    assert effect.status == "RESOLVED_COMMITTED"
    assert effect.resolution == "probe"
    assert effect.external_ref == "issues.create#1"


async def test_idempotent_band_refires_under_the_same_key(world) -> None:
    """The second band: a crash in the same window re-runs the effect rather than surfacing it,
    and the receiver — not the runtime — is what makes that safe."""
    clock = FakeClock()
    provider = CountingProvider(demo.SCRIPT)
    k = _keel(clock, provider, variant="IDEMPOTENT")
    world.hold("issues.upsert", HOLD_MS)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    await _run_until_effect_lands(k, world, "issues.upsert")
    await _take_over(k, clock, handle.run_id)

    view = await k.get(handle.run_id)
    assert view.phase == "COMPLETED"
    assert view.steps[3].state == "COMPLETED", "IDEMPOTENT is re-run, never ambiguous"
    assert world.receipt_counts()["issues.upsert#1"] == 2, "the effect was genuinely re-fired"
    assert world.applied_counts()["issues.upsert#1"] == 1, "and the receiver applied it once"

    keys = {r.effect_key for r in world.receipts if r.endpoint == "issues.upsert"}
    assert len(keys) == 1 and None not in keys, "the same effect_key across attempts is the point"
    assert keys == {view.steps[3].effect_key}

    types = [e.type for e in await k.events(handle.run_id)]
    assert "STEP_AMBIGUOUS" not in types
    assert types.count("STEP_ATTEMPT_STARTED") == 6  # steps 0-2 and 4, plus two attempts at step 3


async def test_escalate_suspends_instead_of_guessing(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no probe, an ambiguous EXTERNAL effect is surfaced, never silently retried (L3)."""
    clock = FakeClock()
    k = _keel(clock, CountingProvider(demo.SCRIPT))
    monkeypatch.setattr(demo.create_issue_external, "resolution", "escalate")
    world.hold("issues.create", HOLD_MS)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    await _run_until_effect_lands(k, world, "issues.create")
    await _take_over(k, clock, handle.run_id)

    view = await k.get(handle.run_id)
    assert view.phase == "SUSPENDED"
    assert view.suspended_reason == "resolved_unknown"
    assert view.steps[3].state == "RESOLVED_UNKNOWN"
    assert world.applied_counts()["issues.create#1"] == 1, "escalating never re-fires"


async def test_sigterm_hands_the_run_back_at_a_step_boundary(world) -> None:
    """Drain is not a lifecycle state: the worker stops at a boundary, releases the lease, and
    appends nothing. The successor's RECOVERY_STARTED{cause=DRAIN} is the whole record (§5)."""
    clock = FakeClock()
    k = _keel(clock, CountingProvider(demo.SCRIPT))
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    w = k.worker(worker_id="w1", lease_ttl=TTL)
    w.draining = True

    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    await w.execute(lease)

    row = await k.journal.run_row(handle.run_id)
    assert row.lease_expires_at is None, "the lease is released, not left to lapse"
    assert row.runnable_at is not None and row.runnable_reason == "DRAIN"
    assert row.terminal_at is None
    types = [e.type for e in await k.events(handle.run_id)]
    assert types == ["RUN_CREATED", "RECOVERY_STARTED"], "nothing special is appended"

    lease2 = await k.journal.claim("w2", timedelta(seconds=TTL))
    assert lease2.cause == "DRAIN"
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(lease2)
    assert (await k.get(handle.run_id)).phase == "COMPLETED"
