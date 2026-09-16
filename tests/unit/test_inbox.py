"""The signals inbox and its drain (§4.10, §5.6, §29.1).

Everything that is not the lease holder influences a run through one table. Not a second control
path beside the fence — *the* path, and the MVP's direct `runnable_at` UPDATE is deleted rather
than kept beside it, because two ways to influence a run is one more than the fence can defend.

Three properties decide whether the inbox is safe, and each is a test below:

    consumed with its event     one fenced transaction, or a signal could be applied and forgotten
    decided at the drain        the API refuses almost nothing; the holder decides from state *now*
    deterministic on replay     a cancel lands at the index the journal records, not near it

The third is the one a reader should be most suspicious of. A cancel that stopped the program
"somewhere around step 3" would make a cancelled run unreproducible, and every replay-based claim
in this project rests on being able to re-execute a run and get the same history back.
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
from keel.core.ids import uuid7
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import SignalRow
from keel.providers.scripted import ScriptedProvider
from keel.state.fold import fold

TTL = 2.0


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


def _keel(clock: FakeClock) -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue_tool("EXTERNAL")],
        programs=[demo.tool_chain],
        clock=clock,
    )


def _row(run_id, type_: str, **kw) -> SignalRow:
    return SignalRow(signal_id=uuid7(), run_id=run_id, type=type_, **kw)


async def _work(k: Keel, worker_id: str = "w1") -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


async def test_a_signal_is_consumed_in_the_same_transaction_as_its_event(world) -> None:
    """The inbox's whole guarantee. A signal cannot be applied without the journal saying so, and
    cannot be marked consumed without the event that says what was done about it — the same
    same-database-transaction argument that gives TRANSACTIONAL tools theirs."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    assert await k.journal.insert_signal(_row(handle.run_id, "cancel", payload={"reason": "no"}))

    await _work(k)

    events = await k.events(handle.run_id)
    received = [e for e in events if e.type == "SIGNAL_RECEIVED"]
    assert len(received) == 1
    assert await k.journal.pending_signals(handle.run_id) == [], "consumed, so never re-read"
    consumed = next(iter(k.journal._signals.values()))
    assert consumed.consumed_seq == received[0].seq, "the event's own seq, not a later one"


async def test_cancel_is_acknowledged_at_a_step_boundary_and_the_run_ends_cancelled(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "cancel", payload={"reason": "operator"}))

    await _work(k)

    state = fold(await k.events(handle.run_id))
    assert state.phase == "CANCELLED"
    assert state.cancel_acknowledged_at == 0, "the next boundary, which is the first step"
    assert state.steps == {}, "nothing ran: the cancel arrived before the program's first step"
    assert world.applied_counts() == {}, "and so nothing reached the World"


async def test_a_cancel_mid_run_lands_where_the_journal_says_and_nowhere_else(world) -> None:
    """The determinism property. The cancel arrives after two steps are journaled, so it is
    acknowledged at step 2 — and a successor re-executing this journal must raise at step 2 too,
    not run one step further because the second pass happened to be faster."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    # Let the run get two steps in, then stop it where a crash would.
    from keel.runtime import hooks

    def crash_after_step_1(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:outcome_commit" and detail.get("step_index") == 1:
            raise hooks.Crash("power cut")

    hooks.install(crash_after_step_1)
    await _work(k, "w1")
    hooks.reset()

    mid = fold(await k.events(handle.run_id))
    assert set(mid.steps) == {0, 1}, "two steps journaled, nothing more"

    await k.journal.insert_signal(_row(handle.run_id, "cancel"))
    clock.advance(TTL + 2)
    await k.journal.reap()
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "CANCELLED"
    assert state.cancel_acknowledged_at == 2, "the first boundary the successor reached"
    assert set(state.steps) == {0, 1}, "step 2 was never attempted"

    # The proof that it is reproducible: fold the journal again and re-run VERIFY against it. The
    # recorded index is what a replay raises at, so the second pass stops in the same place.
    from keel.replay.verify import verify as run_verify

    out = await run_verify(k.journal, handle.run_id, demo.tool_chain.fn, tools=k.tools)
    assert out.ok, out.as_dict()


async def test_the_inbox_is_at_least_once_and_the_second_cancel_is_ignored_not_obeyed(world) -> None:
    """A retried click is the ordinary case, not an error. The API refuses almost nothing; the
    holder decides, and journals `SIGNAL_IGNORED` with the reason so "nothing happened" is an
    auditable answer rather than a silence."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    for _ in range(3):
        assert await k.journal.insert_signal(_row(handle.run_id, "cancel"))

    await _work(k)

    events = await k.events(handle.run_id)
    assert len([e for e in events if e.type == "SIGNAL_RECEIVED"]) == 3, "all three consumed"
    assert len([e for e in events if e.type == "CANCEL_ACKNOWLEDGED"]) == 1, "acted on once"
    ignored = [e for e in events if e.type == "SIGNAL_IGNORED"]
    assert len(ignored) == 2
    assert {e.body.reason for e in ignored} == {"already_cancelling"}
    assert await k.journal.pending_signals(handle.run_id) == []


async def test_a_client_key_deduplicates_the_retry_before_it_reaches_the_inbox(world) -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    assert await k.journal.insert_signal(_row(handle.run_id, "cancel", client_key="op-42"))
    assert not await k.journal.insert_signal(_row(handle.run_id, "cancel", client_key="op-42"))
    assert len(await k.journal.pending_signals(handle.run_id)) == 1


async def test_a_signal_to_a_terminal_run_is_refused_rather_than_left_unconsumed(world) -> None:
    """§5.6: there is no future holder to drain it, so a row inserted here would sit unconsumed for
    the life of the run. The inbox must not grow on late clicks."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await _work(k)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"

    assert not await k.journal.insert_signal(_row(handle.run_id, "cancel"))
    assert await k.journal.pending_signals(handle.run_id) == []


async def test_pause_parks_the_run_and_resume_brings_it_back(world) -> None:
    """The zero-compute wait, in its simplest form. A paused run holds no lease and has no
    `runnable_at`, so nothing polls it — the same park the approval wait uses."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "pause"))

    await _work(k, "w1")

    row = await k.journal.run_row(handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "PAUSED"
    assert row.lease_expires_at is None, "no lease held"
    assert row.runnable_at is None, "and nothing to poll: zero ticks, not just zero compute"

    assert await k.resume(handle.run_id)
    assert (await k.journal.run_row(handle.run_id)).runnable_at is not None, "the signal is the wake"
    await _work(k, "w2")
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"


async def test_a_signal_nothing_handles_is_consumed_and_journaled(world) -> None:
    """An unknown type is not an error at the API and not a silent drop at the drain. It is one
    `SIGNAL_IGNORED{no_handler}`, which is what stops it being re-read at every boundary."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "custom", payload={"hello": "world"}))

    await _work(k)

    events = await k.events(handle.run_id)
    ignored = [e for e in events if e.type == "SIGNAL_IGNORED"]
    assert [e.body.reason for e in ignored] == ["no_handler"]
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED", "and the run is unaffected"


async def test_verify_never_drains(world) -> None:
    """VERIFY appends nothing, so it must not consume anything either. A signal drained by a replay
    would be applied to a run whose history already ran without it."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    # The run must be non-terminal for the signal to be accepted at all, so stop it mid-flight.
    from keel.runtime import hooks

    def crash(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:outcome_commit" and detail.get("step_index") == 1:
            raise hooks.Crash("power cut")

    hooks.install(crash)
    await _work(k, "w1")
    hooks.reset()
    assert await k.journal.insert_signal(_row(handle.run_id, "custom"))

    from keel.replay.verify import verify as run_verify

    before = await k.journal.read(handle.run_id)
    await run_verify(k.journal, handle.run_id, demo.tool_chain.fn, tools=k.tools)
    assert await k.journal.read(handle.run_id) == before, "VERIFY wrote nothing"
    assert len(await k.journal.pending_signals(handle.run_id)) == 1, "and consumed nothing"


# --- the post-phase-8 audit: each test below is a finding that reproduced -----------------------
async def test_a_pause_holds_against_every_signal_but_resume_and_cancel(world) -> None:
    """RUN_PAUSED never set `paused_at`, so any row — an approve, a child result, a `custom` — made
    the paused run claimable and it simply carried on (§16.6). Now the claim skips it, and only a
    `resume` lifts the pause, with RUN_PAUSE_LIFTED clearing the column in its own transaction."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "pause"))
    await _work(k, "w1")
    assert (await k.journal.run_row(handle.run_id)).paused_at is not None

    assert await k.journal.insert_signal(_row(handle.run_id, "custom"))
    assert await k.journal.claim("w2", timedelta(seconds=TTL)) is None, "a custom row does not lift a pause"
    assert fold(await k.events(handle.run_id)).phase == "PAUSED"

    assert await k.journal.insert_signal(_row(handle.run_id, "resume"))
    await _work(k, "w3")
    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED"
    assert "RUN_PAUSE_LIFTED" in [e.type for e in events]
    assert (await k.journal.run_row(handle.run_id)).paused_at is None


async def test_a_pause_and_a_resume_drained_together_cancel_out(world) -> None:
    """Both rows in one drain used to leave the run paused with an empty inbox: the resume was
    judged `not_paused` because the pause had not been released yet."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})
    await k.journal.insert_signal(_row(handle.run_id, "pause"))
    await k.journal.insert_signal(_row(handle.run_id, "resume"))
    await _work(k, "w1")

    types = [e.type for e in await k.events(handle.run_id)]
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert types.index("RUN_PAUSED") < types.index("RUN_PAUSE_LIFTED")


async def test_a_suspended_run_can_be_cancelled(world) -> None:
    """A SUSPENDED run woken by `cancel` used to replay to the step that suspended it, suspend again
    before any drain, and leave the cancel unconsumed for ever (§7.2.1 has SUSPENDED → CANCELLED)."""
    from keel.core.protocols import EffectClass
    from keel.effects.registry import tool
    from keel.runtime import hooks

    @tool(effect=EffectClass.EXTERNAL, timeout=1.0, name="deploy")  # resolution: escalate
    async def deploy(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
        return {"ok": True}

    from keel.client import program as as_program

    @as_program(name="deploys_once", version="1.0")
    async def deploys_once(ctx: Any, args: dict[str, Any]) -> str:
        await ctx.tool("deploy", env="prod")
        return "done"

    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), tools=[deploy], programs=[deploys_once], clock=clock)
    handle = await k.start(deploys_once, {})

    def crash(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:effect_exec":
            raise hooks.Crash(boundary)

    hooks.install(crash)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()
    clock.advance(TTL + 2)
    await k.journal.reap()
    await _work(k, "w2")                                     # AMBIGUOUS → escalate → SUSPENDED
    assert fold(await k.events(handle.run_id)).phase == "SUSPENDED"

    assert await k.journal.insert_signal(_row(handle.run_id, "cancel", payload={"reason": "give up"}))
    await _work(k, "w3")
    state = fold(await k.events(handle.run_id))
    assert state.phase == "CANCELLED"
    assert await k.journal.pending_signals(handle.run_id) == []


async def test_a_suspended_run_woken_by_something_else_stays_suspended_and_quiet(world) -> None:
    """The other half of §7.2.1: a wake that is not `resume` drains and parks again *without*
    re-executing — and consumes the row, or the inbox-aware claim would take the run for ever."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    from keel.events import RunSuspended

    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    async with k.journal.append(lease) as tx:
        await tx.append(RunSuspended(reason="resolved_unknown", detail={"step_index": 0}))
        await tx.set_run(phase="SUSPENDED")
    await k.journal.release(lease, phase="SUSPENDED")

    assert await k.journal.insert_signal(_row(handle.run_id, "custom"))
    await _work(k, "w2")
    events = await k.events(handle.run_id)
    assert fold(events).phase == "SUSPENDED"
    assert not any(e.type == "STEP_INTENDED" for e in events), "nothing re-executed"
    assert await k.journal.pending_signals(handle.run_id) == []
    assert await k.journal.claim("w3", timedelta(seconds=TTL)) is None


async def test_keel_resume_exits_zero(world, monkeypatch) -> None:
    """`keel resume` queued its row and then died on an undefined name — exit 1 on every call."""
    import asyncio

    from typer.testing import CliRunner

    import keel.cli.main as cli

    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "x"})
    monkeypatch.setattr(cli, "_load_app", lambda app_ref, dsn: k)
    monkeypatch.setattr(cli, "_run", lambda coro: asyncio.get_running_loop().create_task(coro))

    for cmd in ("pause", "resume"):
        result = CliRunner().invoke(cli.app, [cmd, str(handle.run_id)])
        assert result.exit_code == 0, (cmd, result.output, result.exception)
    await asyncio.sleep(0)
    assert [s.type for s in await k.journal.pending_signals(handle.run_id)] == ["pause", "resume"]


async def test_an_unknown_signal_type_is_refused_at_the_insert(world) -> None:
    """Memory accepted any type; Postgres' CHECK refuses all but nine. The same refusal on both."""
    from keel.core.errors import IllegalTransition

    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "x"})
    with pytest.raises(IllegalTransition):
        await k.journal.insert_signal(_row(handle.run_id, "deploy_now"))
    assert await k.journal.pending_signals(handle.run_id) == []


async def test_a_lost_takeover_race_ends_the_lease_not_the_worker(world) -> None:
    """A takeover that moved the epoch between a worker's claim and its RECOVERY_STARTED used to
    raise `Fenced` out of `Worker.execute` — ending `keel worker` for a routine lost race."""
    from keel.client import program as as_program
    from keel.runtime.delegation import Delegation, cancel_signal
    from keel.runtime.takeover import force_cancel

    @as_program(name="kid", version="1.0")
    async def kid(ctx: Any, args: dict[str, Any]) -> Any:
        await ctx.now()
        return {"ok": 1}

    @as_program(name="parent", version="1.0")
    async def parent(ctx: Any, args: dict[str, Any]) -> Any:
        await ctx.delegate(Delegation(program="kid", task="t"))
        return {}

    clock = FakeClock()
    j = MemoryJournal(clock=clock)
    k = Keel(journal=j, programs=[parent, kid], clock=clock)
    handle = await k.start(parent, {})
    lease = await j.acquire(handle.run_id, "wp", timedelta(seconds=TTL))
    with contextlib.suppress(BaseException):
        await k.worker(worker_id="wp", lease_ttl=TTL).execute(lease)
    [child] = await j.children(handle.run_id)
    await j.insert_signal(cancel_signal(child.run_id, client_key="c1", by="parent", reason="parent_cancel"))
    clock.advance(6)

    child_lease = await j.claim("w-child", timedelta(seconds=TTL))
    assert child_lease.run_id == child.run_id
    assert await force_cancel(j, child.run_id, worker_id="reaper", ttl_s=TTL, forced_by="reaper",
                              cancel_grace_s=5.0) == "cancelled"
    await k.worker(worker_id="w-child", lease_ttl=TTL).execute(child_lease)   # must not raise
    [rec] = [r for r in await j.recoveries(child.run_id) if r.lease_epoch == child_lease.epoch]
    assert rec.outcome == "FENCED"


async def test_the_memory_journal_commits_all_or_nothing(world) -> None:
    """A guard that fired inside `_commit` used to leave the events before it committed — a state
    Postgres, which rolls the transaction back, can never produce. Includes the approval guard
    (`events_approval_once`) the memory backend did not mirror."""
    from keel.core.errors import IllegalTransition
    from keel.events import ApprovalRequested, RunWaiting

    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "x"})
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    before = [e.seq for e in await k.events(handle.run_id)]
    next_seq = lease.next_seq
    with pytest.raises(IllegalTransition):
        async with k.journal.append(lease) as tx:
            await tx.append(RunWaiting(reason="approval", wake_at=None, step_index=0))
            await tx.append(ApprovalRequested(step_index=0, approval_id=uuid7(), payload={}))
            await tx.append(ApprovalRequested(step_index=0, approval_id=uuid7(), payload={}))
    assert [e.seq for e in await k.events(handle.run_id)] == before, "nothing committed"
    assert lease.next_seq == next_seq, "and the counter rewound"


async def test_verify_reproduces_a_run_that_died_between_acknowledge_and_cancelled(world) -> None:
    """CANCEL_ACKNOWLEDGED durable, RUN_CANCELLED not yet: the replay raises `Cancelled` at the
    recorded index, which *is* the reproduction — VERIFY used to call it a failed pass."""
    from keel.replay.verify import verify as run_verify
    from keel.runtime import hooks

    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "x"})
    assert await k.journal.insert_signal(_row(handle.run_id, "cancel"))

    def crash(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:signal_consume":
            raise hooks.Crash(boundary)

    hooks.install(crash)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()
    state = fold(await k.events(handle.run_id))
    assert state.cancel_acknowledged_at is not None and state.phase != "CANCELLED"
    out = await run_verify(k.journal, handle.run_id, demo.tool_chain.fn, tools=k.tools)
    assert out.ok, out.as_dict()
