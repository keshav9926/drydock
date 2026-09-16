"""Retries that do not duplicate, and a budget that is an upper bound (§8.5, §8.6).

Both are day-4 mechanisms and both are dangerous in the same way: a retry policy is how a runtime
turns one effect into two, and a budget that only counts completed calls is how it under-reports
what it was billed for. So each is tested for the case where being generous would be wrong.
"""

from __future__ import annotations

import pytest

from keel import Budget, Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider
from keel.runtime.budget import BudgetExceeded, Reservation, admit, reserve_model
from keel.runtime.retry import NO_RETRY, RetryPolicy
from keel.state.fold import Charged, fold


# --- retry -------------------------------------------------------------------
def test_the_default_is_one_attempt() -> None:
    """Nothing retries unless a caller asks. An unmeasured retry policy is a guess, and a runtime
    that retries by default hides the difference between recovered and did-it-twice."""
    assert NO_RETRY.max_attempts == 1
    assert not NO_RETRY.may_retry(1)


def test_backoff_grows_and_stays_inside_the_lease() -> None:
    """Holding a lease past its TTL is how a worker becomes a zombie. The policy is clamped rather
    than allowed to manufacture one to honour its curve."""
    policy = RetryPolicy(max_attempts=5, base_s=0.5, factor=4.0)
    import random

    rng = random.Random(0)
    for attempt in (1, 2, 3, 4):
        assert policy.backoff_s(attempt, lease_ttl_s=2.0, rng=rng) <= 1.0

    quiet = RetryPolicy(max_attempts=5, base_s=0.05, factor=2.0)
    always_max = type("R", (), {"random": staticmethod(lambda: 1.0)})()
    windows = [quiet.backoff_s(a, lease_ttl_s=100.0, rng=always_max) for a in (1, 2, 3)]
    assert windows == sorted(windows) and windows[0] < windows[-1], "exponential"


async def test_a_retryable_failure_is_retried_and_an_absolute_one_is_not() -> None:
    clock = FakeClock()
    attempts = {"n": 0}

    async def flaky(args, tctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return {"ok": True}

    from keel.core.protocols import EffectClass
    from keel.effects.registry import tool

    flaky_tool = tool(effect=EffectClass.PURE, timeout=1.0, name="search")(flaky)
    k = Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[flaky_tool, demo.create_issue_tool("EXTERNAL")],
        programs=[demo.tool_chain],
        clock=clock,
    )
    # A tool error is `retryable=False` — the receiver spoke plainly — so even a retrying policy
    # stops. This is the guard against turning every failure into a duplicate.
    handle = await k.start(demo.tool_chain, {"task": "t"})
    await k.worker(worker_id="w", lease_ttl=5.0, retry=RetryPolicy(max_attempts=3)).run_until_idle(
        run_id=handle.run_id, timeout=5
    )
    view = await k.get(handle.run_id)
    assert view.phase == "FAILED"
    assert attempts["n"] == 1, "a definite refusal is not retried"


# --- budget ------------------------------------------------------------------
def test_a_crashed_attempt_stays_charged_forever() -> None:
    """The line that makes the journaled charge an upper bound: a model attempt with no outcome may
    well have been served and billed, so the runtime assumes it was."""
    c = Charged()
    c.start(0, 1, 1200, "MODEL")
    assert (c.tokens_charged, c.model_calls) == (1200, 1)

    c.settle(0, 1, {"input_tokens": 90, "output_tokens": 30})
    assert c.tokens_charged == 120, "an outcome swaps the reservation for what it actually cost"

    c.start(1, 1, 1200, "MODEL")  # crashed: no outcome ever arrives
    assert c.tokens_charged == 1320
    c.settle(1, 1, None)
    assert c.tokens_charged == 1320, "an outcome with no usage leaves the reservation charged"


def test_admission_refuses_before_the_barrier() -> None:
    charged = Charged(tokens_charged=900, model_calls=2, tool_calls=1)
    admit({"max_tokens": 2000}, charged, reserve_model(100, 900))
    with pytest.raises(BudgetExceeded) as exc:
        admit({"max_tokens": 1500}, charged, reserve_model(100, 900))
    assert exc.value.dimension == "max_tokens"


def test_model_calls_count_started_attempts_not_outcomes() -> None:
    """An attempt that crashed still asked the provider, so it still counts."""
    charged = Charged(model_calls=3)
    with pytest.raises(BudgetExceeded):
        admit({"max_model_calls": 3}, charged, Reservation(model_call=True))
    admit({"max_tool_calls": 5}, charged, Reservation(tool_call=True)), "a different dimension"


def test_no_budget_admits_everything() -> None:
    admit(None, Charged(), reserve_model(10**9, 10**9))
    admit({}, Charged(tokens_charged=10**9), reserve_model(10**9, 10**9))


async def test_the_projection_bounds_what_the_provider_was_billed() -> None:
    """S9 in miniature: fold the journal, and the charge is never below the usage the provider
    actually reported."""
    clock = FakeClock()
    k = Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue_tool("EXTERNAL")],
        programs=[demo.tool_chain],
        clock=clock,
    )
    import crashproof.workloads.tool_chain_1_effect as w
    from crashproof.world.server import WorldServer

    world = w.build_world()
    server = WorldServer(world, port=0)
    await server.start()
    demo.WORLD_URL = server.base_url
    try:
        result = await k.run(demo.tool_chain, {"task": "t"}, budget=Budget(max_tokens=100_000))
        state = fold(await k.events(result.run_id))
    finally:
        await server.stop()

    reported = sum(
        int((e.body.usage or {}).get("input_tokens", 0)) + int((e.body.usage or {}).get("output_tokens", 0))
        for e in await k.events(result.run_id)
        if e.type == "STEP_COMPLETED" and getattr(e.body, "usage", None)
    )
    assert state.charged.model_calls == 3
    assert state.charged.tokens_charged >= reported > 0


# --- the circuit breaker and the zero-compute backoff (§8, §11.5 provider_outage) ---------------
async def test_an_outage_opens_the_breaker_and_the_run_waits_for_it_at_zero_compute() -> None:
    """`provider_outage`'s claim, on the runtime side: retries back off, the breaker opens after
    `n_open` failures and pushes the next attempt out, the run parks for that wait with its lease
    released (RUN_WAITING{retry_backoff}), the timer sweep wakes it, and the half-open attempt
    completes the run. No retry storm, and no worker held while the provider is down."""
    from keel.client import program
    from keel.core.errors import UnknownOutcome
    from keel.runtime.breaker import CircuitBreaker

    clock = FakeClock()
    calls = {"n": 0}

    class Outage:
        name = "flaky-provider"

        def __init__(self, inner: ScriptedProvider) -> None:
            self.inner = inner

        async def count_tokens(self, req):
            return await self.inner.count_tokens(req)

        async def complete(self, req):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise UnknownOutcome("503 from the provider")
            return await self.inner.complete(req)

    @program(name="asks_once", version="1.0")
    async def asks_once(ctx, args):
        resp = await ctx.model([{"role": "user", "content": "hi"}], name="m")
        return resp.text

    k = Keel(journal=MemoryJournal(clock=clock), provider=Outage(ScriptedProvider(demo.SCRIPT)),
             programs=[asks_once], clock=clock)
    handle = await k.start(asks_once, {})
    breaker = CircuitBreaker(n_open=2, cooldown_s=10.0)
    policy = RetryPolicy(max_attempts=5, base_s=0.01)

    def worker(wid: str):
        return k.worker(worker_id=wid, lease_ttl=5.0, retry=policy, breaker=breaker)

    from datetime import timedelta

    lease = await k.journal.claim("w1", timedelta(seconds=5))
    await worker("w1").execute(lease)

    events = await k.events(handle.run_id)
    state = fold(events)
    row = await k.journal.run_row(handle.run_id)
    assert calls["n"] == 2, "two attempts, then the breaker opened: no storm"
    assert state.phase == "SLEEPING" and state.waiting_reason == "retry_backoff"
    assert row.lease_expires_at is None and row.runnable_at is None, "zero compute while the provider is down"
    failed = [e for e in events if e.type == "STEP_FAILED"]
    assert failed[-1].body.retryable and failed[-1].body.next_attempt_at is not None
    assert row.wake_at == failed[-1].body.next_attempt_at
    assert row.wake_at >= clock.now() + timedelta(seconds=9), "pushed out to the end of the cooldown"

    assert await k.journal.claim("idle", timedelta(seconds=5)) is None
    clock.advance(11)
    assert await k.journal.sweep_timers() == 1
    lease = await k.journal.claim("w2", timedelta(seconds=5))
    await worker("w2").execute(lease)

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED", state.error
    assert calls["n"] == 3, "one half-open attempt, and it succeeded"
    assert not breaker.is_open("flaky-provider", clock.now())


async def test_a_successor_honours_a_retry_the_journal_already_decided() -> None:
    """A worker that dies during a backoff leaves STEP_FAILED{retryable, next_attempt_at}. Before,
    any journaled FAILED ended the run on recovery; the decision to retry is now journal state."""
    from keel.client import program
    from keel.core.errors import UnknownOutcome
    from keel.runtime import hooks

    clock = FakeClock()
    calls = {"n": 0}

    class Blip:
        name = "blip"

        def __init__(self, inner):
            self.inner = inner

        async def count_tokens(self, req):
            return await self.inner.count_tokens(req)

        async def complete(self, req):
            calls["n"] += 1
            if calls["n"] == 1:
                raise UnknownOutcome("503")
            return await self.inner.complete(req)

    @program(name="asks_again", version="1.0")
    async def asks_again(ctx, args):
        return (await ctx.model([{"role": "user", "content": "hi"}], name="m")).text

    k = Keel(journal=MemoryJournal(clock=clock), provider=Blip(ScriptedProvider(demo.SCRIPT)),
             programs=[asks_again], clock=clock)
    handle = await k.start(asks_again, {})

    def crash(boundary, detail):
        if boundary == "after:outcome_commit":
            raise hooks.Crash("died during the backoff")

    from datetime import timedelta

    hooks.install(crash)
    try:
        lease = await k.journal.claim("w1", timedelta(seconds=2))
        with pytest.raises(hooks.Crash):
            await k.worker(worker_id="w1", lease_ttl=2.0, retry=RetryPolicy(max_attempts=3, base_s=0.01)).execute(lease)
    finally:
        hooks.reset()

    clock.advance(5)
    await k.journal.reap()
    lease = await k.journal.claim("w2", timedelta(seconds=2))
    await k.worker(worker_id="w2", lease_ttl=2.0, retry=NO_RETRY).execute(lease)  # a policy that would not retry
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED", state.error
    assert calls["n"] == 2
