"""`ctx.compact()`: a MODEL step whose outcome is the summary, and the context projection it resets
(§16.1, §16.2).

Compaction is itself a decision. Journaled, the summary is the thing the model will ever see of what
came before, and a recovery hands back the same one; unjournaled, a crash re-summarises and the run's
later decisions stop being explained by its journal.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from keel import Keel, program
from keel.core.clock import FakeClock
from keel.core.protocols import EffectClass
from keel.effects.registry import tool
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import Decision, ScriptedProvider
from keel.replay.verify import verify
from keel.runtime import hooks
from keel.runtime.ctx import COMPACT_SYSTEM
from keel.state.fold import fold

TTL = 2.0


@tool(effect=EffectClass.PURE, timeout=1.0)
async def echo(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    return {"echo": args["n"]}


@program(name="compactor", version="1.0")
async def compactor(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    await ctx.plan.init(["compact once"])
    for i in range(3):
        await ctx.model(ctx.context.messages or [{"role": "user", "content": "go"}], name="decide")
        await ctx.tool("echo", n=i)
    before = len(ctx.context.messages)
    summary = await ctx.compact()
    after = ctx.context.messages
    # Control flow off the context: a replay reading anything but the context at its cursor would
    # issue a different step here.
    if len(after) == 1:
        await ctx.model(after, name="decide")
    return {"before": before, "after": len(after), "summary": summary, "first": after[0]["role"]}


def _keel(clock: FakeClock) -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider([Decision(text=f"turn {i}") for i in range(8)]),
        tools=[echo],
        programs=[compactor],
        clock=clock,
    )


async def _work(k: Keel, worker_id: str) -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


async def test_compaction_is_a_journaled_model_step_that_resets_the_context_projection() -> None:
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(compactor)
    await _work(k, "w1")
    events = await k.events(handle.run_id)
    state = fold(events)

    assert state.phase == "COMPLETED"
    assert state.result == {"before": 6, "after": 1, "summary": "turn 3", "first": "summary"}
    [compact] = [s for s in state.steps.values() if s.kind == "COMPACT"]
    assert (compact.name, compact.state) == ("compact", "COMPLETED")
    intent = next(e for e in events if e.type == "STEP_INTENDED" and e.body.kind == "COMPACT")
    assert intent.body.args["system"] == COMPACT_SYSTEM and len(intent.body.args["messages"]) == 6
    assert intent.body.request_hash, "a compaction's prompt is a request like any other (PromptDrift)"
    assert state.compact_seq == compact.outcome_seq
    assert [m["role"] for m in state.context] == ["summary", "assistant"], "summary, then what came since"
    assert state.context[0]["content"] == "turn 3"
    assert [i["title"] for i in state.plan] == ["compact once"], "compaction never touches the plan"
    assert state.charged.model_calls == 5, "budgeted as a model call"
    assert (await verify(k.journal, handle.run_id, compactor, tools=k.tools)).ok


async def test_a_crash_before_the_summary_commits_re_asks_and_the_replay_reads_the_journaled_one() -> None:
    """MODEL semantics (§10.4): an attempt with no outcome is re-run, and once the summary is
    journaled every later replay hands back that summary, never a fresh one."""
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(compactor)

    def die(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "before:outcome_commit" and detail.get("kind") == "compact":
            raise hooks.Crash("killed with the summary in hand")

    hooks.install(die)
    try:
        await _work(k, "w1")
    finally:
        hooks.reset()
    clock.advance(TTL + 1)
    await k.journal.reap()
    await _work(k, "w2")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED" and state.result["after"] == 1
    [compact] = [s for s in state.steps.values() if s.kind == "COMPACT"]
    assert compact.attempts == 2, "the abandoned attempt was re-run, not resumed"
    assert (await verify(k.journal, handle.run_id, compactor, tools=k.tools)).ok
