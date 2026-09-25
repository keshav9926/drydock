"""STREAMS: chunks are journaled, the answer is the outcome, and a broken stream is the class's (§9.3, §10.7).

The modifier exists for observability and UI resume, not semantics — so every test here asks the
same question from a different side: did a partial answer become a decision? A truncated model stream
must fail retryable and be re-asked; a crash mid-stream must be disposed by the class exactly as a
crash with no chunks would; the only relaxation is `partial_ok`, for PURE, on a live attempt.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import pytest

from keel import Keel
from keel.client import program
from keel.core.clock import FakeClock
from keel.core.errors import ContractViolation, ToolRegistrationError
from keel.core.protocols import EffectClass, Modifier, ProbeResult
from keel.effects.registry import tool
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import Decision, ScriptedProvider
from keel.replay.verify import verify
from keel.runtime import hooks
from keel.runtime.retry import RetryPolicy
from keel.runtime.steps import CHUNK_BATCH_TOKENS
from keel.state.fold import Charged, fold

TTL = 2.0
#: Long enough to cross the 256-token batch three times: ~800 output tokens, a word per chunk.
ANSWER = " ".join(f"word{i:04d}" for i in range(360))


class Cutting(ScriptedProvider):
    """Streams the scripted answer, and cuts the first `cuts` streams after `after` pieces — the
    `model_stream_truncate` fault, from the provider's side: no final response ever arrives."""

    def __init__(self, script: Any, *, after: int, cuts: int = 1, crash: bool = False) -> None:
        super().__init__(script)
        self.after, self.cuts, self.crash, self.streams = after, cuts, crash, 0

    async def stream(self, req: Any):
        self.streams += 1
        n = 0
        async for chunk in super().stream(req):
            if self.streams <= self.cuts and n == self.after:
                if self.crash:
                    raise hooks.Crash("the worker died mid-stream")
                return
            n += 1
            yield chunk


@program(name="answer", version="1.0")
async def answer(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    resp = await ctx.model([{"role": "user", "content": "explain"}], name="answer", max_tokens=2048, stream=True)
    return {"answer": resp.text}


def _keel(provider: Any, *tools: Any, programs: Any = (answer,)) -> tuple[Keel, FakeClock]:
    clock = FakeClock()
    return Keel(journal=MemoryJournal(clock=clock), provider=provider, tools=list(tools),
                programs=list(programs), clock=clock), clock


async def _work(k: Keel, worker_id: str, lease: Any, **kw: Any) -> None:
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL, **kw).execute(lease)


async def _crash_then_recover(k: Keel, clock: FakeClock, run_id: Any, **kw: Any) -> None:
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    await _work(k, "w1", lease, **kw)
    clock.advance(TTL + 2)
    await k.journal.reap()
    successor = await k.journal.acquire(run_id, "w2", timedelta(seconds=TTL))
    assert successor is not None
    await _work(k, "w2", successor, **kw)


def _chunks(events: list[Any], step: int = 0) -> list[Any]:
    return [e for e in events if e.type == "STEP_CHUNK" and e.step_index == step]


# --- the modifier's shape -----------------------------------------------------------------------
async def test_a_streamed_answer_is_journaled_in_batches_and_the_answer_is_the_outcome() -> None:
    k, _ = _keel(ScriptedProvider([Decision(text=ANSWER)]))
    result = await k.run(answer, {})
    events = await k.events(result.run_id)
    chunks = _chunks(events)
    outcome = next(e for e in events if e.type == "STEP_COMPLETED")
    usage = outcome.body.usage

    assert [c.body.chunk_no for c in chunks] == list(range(1, len(chunks) + 1))
    assert len(chunks) == -(-usage["output_tokens"] // CHUNK_BATCH_TOKENS), "one commit per 256 tokens"
    assert "".join(c.body.blob for c in chunks) == ANSWER, "deltas, which add up to what streamed"
    assert chunks[-1].body.usage_cum == usage, "cumulative, ending at the outcome's usage"
    assert all(c.seq < outcome.seq for c in chunks), "every chunk before the one semantic outcome"
    assert result.result == {"answer": ANSWER}
    state = fold(events)
    assert state.charged.tokens_charged == usage["input_tokens"] + usage["output_tokens"]
    assert state.steps[0].state == "COMPLETED"
    replay = await verify(k.journal, result.run_id, answer.fn)
    assert replay.status == "PASS", "a memoized stream replays without reading a chunk"


async def test_a_step_without_streams_journals_no_chunk() -> None:
    @program(name="plain", version="1.0")
    async def plain(ctx: Any, args: dict[str, Any]) -> str:
        return (await ctx.model([{"role": "user", "content": "x"}], name="answer")).text

    k, _ = _keel(ScriptedProvider([Decision(text=ANSWER)]), programs=[plain])
    result = await k.run(plain, {})
    assert not _chunks(await k.events(result.run_id)), "§21.3: no STEP_CHUNK at all without STREAMS"


# --- model_stream_truncate, live ----------------------------------------------------------------
async def test_a_truncated_stream_fails_retryable_and_the_partial_text_is_never_the_answer() -> None:
    provider = Cutting([Decision(text=ANSWER)], after=300)
    k, _ = _keel(provider)
    handle = await k.start(answer, {})
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    await k.worker(worker_id="w1", lease_ttl=TTL, model_retry=RetryPolicy(max_attempts=2, base_s=0.0)).execute(lease)
    events = await k.events(handle.run_id)
    state = fold(events)

    failed = next(e for e in events if e.type == "STEP_FAILED")
    assert (failed.body.attempt_no, failed.body.retryable) == (1, True)
    assert "StreamTruncated" in failed.body.error or "stream ended" in failed.body.error
    first = [c for c in _chunks(events) if c.body.attempt_no == 1]
    assert first and "".join(c.body.blob for c in first) != ANSWER, "the cut attempt stopped short"
    assert state.phase == "COMPLETED" and state.result == {"answer": ANSWER}, "re-asked, whole"
    # The cut attempt is never settled: it stays charged at its reservation, however far it got.
    reservation = next(e.body.reservation for e in events if e.type == "STEP_ATTEMPT_STARTED")
    usage = next(e.body.usage for e in events if e.type == "STEP_COMPLETED")
    assert state.charged.tokens_charged == reservation + usage["input_tokens"] + usage["output_tokens"]


# --- a crash mid-stream, disposed by the class --------------------------------------------------
async def test_a_model_crash_mid_stream_is_a_new_attempt_and_the_chunks_stay_charged() -> None:
    provider = Cutting([Decision(text=ANSWER)], after=300, crash=True)
    k, clock = _keel(provider)
    handle = await k.start(answer, {})
    await _crash_then_recover(k, clock, handle.run_id)
    events = await k.events(handle.run_id)
    state = fold(events)

    dead = [c for c in _chunks(events) if c.body.attempt_no == 1]
    assert dead, "the batches journaled before the crash are there, attempt-scoped"
    closed = next(e for e in events if e.type == "STEP_FAILED")
    assert (closed.body.attempt_no, closed.body.error) == (1, "attempt_abandoned")
    assert state.phase == "COMPLETED" and state.result == {"answer": ANSWER}
    reservation = next(e.body.reservation for e in events if e.type == "STEP_ATTEMPT_STARTED")
    seen = dead[-1].body.usage_cum
    usage = next(e.body.usage for e in events if e.type == "STEP_COMPLETED")
    assert state.charged.tokens_charged == (
        max(reservation, seen["input_tokens"] + seen["output_tokens"]) + sum(usage.values())
    ), "an abandoned attempt: max(reservation, last usage_cum), never settled by its closure"


def test_usage_cum_raises_the_floor_and_never_lowers_it() -> None:
    c = Charged()
    c.start(0, 1, 100, "MODEL")
    c.chunk(0, 1, {"input_tokens": 40, "output_tokens": 30})
    assert c.tokens_charged == 100, "below the reservation: the reservation stands"
    c.chunk(0, 1, {"input_tokens": 40, "output_tokens": 90})
    assert c.tokens_charged == 130, "above it: the floor rises"
    c.chunk(0, 1, {"input_tokens": 40, "output_tokens": 10})
    assert c.tokens_charged == 130
    c.settle(0, 1, {"input_tokens": 40, "output_tokens": 95})
    assert c.tokens_charged == 135, "an outcome swaps the floor for what it cost"


def _streaming_tool(cls: EffectClass, sent: list[Any], *, crash_after: int | None = None,
                    raise_after: int | None = None, partial_ok: bool = False, **kw: Any) -> Any:
    @tool(effect=cls, timeout=1.0, modifiers=(Modifier.STREAMS,), partial_ok=partial_ok, name="tail", **kw)
    async def tail(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
        sent.append((tctx.attempt_no, tctx.effect_key))
        for i in range(4):
            if crash_after is not None and i == crash_after and len(sent) == 1:
                raise hooks.Crash("the worker died mid-stream")
            if raise_after is not None and i == raise_after:
                raise ConnectionError("the stream broke")
            await tctx.emit(f"line {i}\n")
        return {"lines": 4}

    return tail


@program(name="tailing", version="1.0")
async def tailing(ctx: Any, args: dict[str, Any]) -> Any:
    return await ctx.tool("tail", path="ci.log")


@pytest.mark.parametrize("cls", [EffectClass.PURE, EffectClass.IDEMPOTENT])
async def test_a_tool_crash_mid_stream_reruns_pure_and_idempotent_under_the_same_key(cls: EffectClass) -> None:
    sent: list[Any] = []
    k, clock = _keel(ScriptedProvider([]), _streaming_tool(cls, sent, crash_after=2), programs=[tailing])
    handle = await k.start(tailing, {})
    await _crash_then_recover(k, clock, handle.run_id)
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED" and state.result == {"lines": 4}
    assert [a for a, _ in sent] == [1, 2], "discard the partial, new attempt"
    assert sent[0][1] == sent[1][1], "IDEMPOTENT: the same key; PURE: the key is the same derivation"


async def test_an_external_crash_mid_stream_is_ambiguous_and_takes_the_declared_resolution() -> None:
    sent: list[Any] = []
    tail = _streaming_tool(EffectClass.EXTERNAL, sent, crash_after=2, resolution="probe")

    @tail.probe_hook
    async def _probe(effect_key: str, args: Any, tctx: Any) -> ProbeResult:
        return ProbeResult("COMMITTED", evidence="the receiver has it", result={"lines": 2})

    k, clock = _keel(ScriptedProvider([]), tail, programs=[tailing])
    handle = await k.start(tailing, {})
    await _crash_then_recover(k, clock, handle.run_id)
    events = await k.events(handle.run_id)
    state = fold(events)
    assert [e.type for e in events if e.type in ("STEP_AMBIGUOUS", "STEP_RESOLVED")] == ["STEP_AMBIGUOUS", "STEP_RESOLVED"]
    assert len(sent) == 1, "never blindly re-triggered"
    assert state.result == {"lines": 2}, "the receiver's answer, not the chunks"


# --- partial_ok: PURE only, live only -----------------------------------------------------------
@pytest.mark.parametrize("partial_ok", [True, False])
async def test_partial_ok_completes_a_pure_stream_that_broke_and_nothing_else_does(partial_ok: bool) -> None:
    sent: list[Any] = []
    tail = _streaming_tool(EffectClass.PURE, sent, raise_after=2, partial_ok=partial_ok)
    k, _ = _keel(ScriptedProvider([]), tail, programs=[tailing])
    handle = await k.start(tailing, {})
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    await k.worker(worker_id="w1", lease_ttl=TTL).execute(lease)
    events = await k.events(handle.run_id)
    state = fold(events)
    assert _chunks(events), "what streamed before the break is journaled"
    if partial_ok:
        assert state.phase == "COMPLETED"
        assert state.result == {"partial": True, "chunks": ["line 0\n", "line 1\n"]}
    else:
        failed = next(e for e in events if e.type == "STEP_FAILED")
        assert failed.body.retryable and failed.body.error.startswith("mid_stream"), "FAILED-retryable"
        assert state.phase == "FAILED", "NO_RETRY: the retryable failure stands"


def test_the_composition_rules_refuse_streams_on_transactional_and_partial_ok_off_pure() -> None:
    async def fn(args: Any, tctx: Any) -> None:
        return None

    with pytest.raises(ContractViolation):
        tool(effect=EffectClass.TRANSACTIONAL, modifiers=(Modifier.STREAMS,))(fn)
    with pytest.raises(ContractViolation):
        tool(effect=EffectClass.IDEMPOTENT, modifiers=(Modifier.STREAMS,), partial_ok=True)(fn)


def test_transactional_is_refused_rather_than_silently_weakened() -> None:
    """TRANSACTIONAL needs `tctx.db` and the effect-table bridge, which are cut with W4: a tool that
    declared it would recover like PURE. Registration refuses it, naming what is missing."""

    async def fn(args: Any, tctx: Any) -> None:
        return None

    with pytest.raises(ToolRegistrationError, match="TRANSACTIONAL is not built"):
        tool(effect=EffectClass.TRANSACTIONAL)(fn)


async def test_replay_treats_started_with_chunks_exactly_as_started_alone() -> None:
    """§10.7: chunks never reach control flow. A journal cut mid-stream folds to the same open step
    a journal cut before the stream would, and VERIFY stops at it the same way."""
    provider = Cutting([Decision(text=ANSWER)], after=300, crash=True)
    k, _ = _keel(provider)
    handle = await k.start(answer, {})
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    await _work(k, "w1", lease)
    events = await k.events(handle.run_id)
    assert _chunks(events)
    without = [e for e in events if e.type != "STEP_CHUNK"]
    assert fold(events).steps[0].state == fold(without).steps[0].state == "RUNNING"
    replay = await verify(k.journal, handle.run_id, answer.fn)
    assert replay.ok and replay.stopped == "in_flight_running"
