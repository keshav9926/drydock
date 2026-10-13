"""TRANSACTIONAL: the tool's writes and their outcome are one commit, or neither happened (§9.1).

The other three classes bound an ambiguity window; this one has none. Every test asks the same
question from a different side — after a crash, a timeout, an error or a lost lease, is the table
consistent with the journal? A row with no STEP_COMPLETED, or a STEP_COMPLETED with no row, is the
class broken; a second row is S1 against the one `exactly_once` claim Keel makes.

The memory backend's `tctx.db` is its tables (`MemoryJournal.tables`), staged in the append and
applied at its commit; `tests/integration/test_transactional_pg.py` runs the same shapes on Postgres,
where it is the connection itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from datetime import timedelta
from typing import Any

import pytest

from keel import Keel
from keel.client import program
from keel.core.clock import FakeClock
from keel.core.errors import ContractViolation, Rejected, ToolRegistrationError
from keel.core.protocols import EffectClass, Modifier
from keel.effects.registry import tool
from keel.journal.memory import MemoryJournal
from keel.replay.verify import verify
from keel.runtime import hooks
from keel.runtime.retry import RetryPolicy
from keel.runtime.steps import _rolled_back
from keel.runtime.worker import Worker
from keel.state.fold import fold

TTL = 2.0
RETRY = RetryPolicy(max_attempts=2, base_s=0.01)


class Deadlock(Exception):
    """What psycopg raises for SQLSTATE 40P01, minus psycopg."""

    sqlstate = "40P01"


def orders_tool(plan: dict[int, str] | None = None, *, timeout: float = 1.0) -> tuple[Any, list[int]]:
    """`save_order`, TRANSACTIONAL: one row in `orders` through `tctx.db`. `plan` maps an attempt to
    what it does *after* its write — raise, sleep past its timeout, deadlock or be refused — so every
    failure has a write to roll back. Returns the tool and the attempts that ran it."""
    plan = dict(plan or {})
    ran: list[int] = []

    @tool(effect=EffectClass.TRANSACTIONAL, timeout=timeout, name="save_order")
    async def save_order(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
        ran.append(tctx.attempt_no)
        tctx.db.setdefault("orders", []).append({"id": args["id"], "attempt": tctx.attempt_no})
        what = plan.get(tctx.attempt_no)
        if what == "raise":
            raise ValueError("violates check constraint orders_qty")
        if what == "sleep":
            await asyncio.sleep(timeout * 4)
        if what == "deadlock":
            raise Deadlock("deadlock detected")
        if what == "rejected":
            raise Rejected("the order is closed")
        return {"id": args["id"], "external_ref": f"orders/{args['id']}"}

    return save_order, ran


@program(name="place_order", version="1.0")
async def place_order(ctx: Any, args: dict[str, Any]) -> Any:
    return await ctx.tool("save_order", id="o1")


def _keel(*tools: Any) -> tuple[Keel, FakeClock]:
    clock = FakeClock()
    return Keel(journal=MemoryJournal(clock=clock), tools=list(tools), programs=[place_order], clock=clock), clock


async def _work(k: Keel, worker_id: str, lease: Any, **kw: Any) -> None:
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL, **kw).execute(lease)


async def _take_over(k: Keel, clock: FakeClock, run_id: Any) -> None:
    clock.advance(TTL + 2)  # past both the lease and the attempt deadline
    assert await k.journal.reap() == [run_id]
    successor = await k.journal.acquire(run_id, "w2", timedelta(seconds=TTL))
    assert successor is not None
    await _work(k, "w2", successor)


def _crash_at(boundary: str) -> None:
    spent: list[bool] = []

    def hook(at: str, detail: dict[str, Any]) -> None:
        if at == boundary and not spent and detail.get("name") == "save_order":
            spent.append(True)
            raise hooks.Crash(f"power cut at {at}")

    hooks.install(hook)


@pytest.fixture(autouse=True)
def _no_hook_leaks():
    hooks.reset()
    yield
    hooks.reset()


def _orders(k: Keel) -> list[dict[str, Any]]:
    return k.journal.tables.get("orders", [])


# --- the shape --------------------------------------------------------------------------------
async def test_the_write_and_its_outcome_commit_together() -> None:
    save_order, ran = orders_tool()
    k, _ = _keel(save_order)
    result = await k.run(place_order, {})
    assert result.phase == "COMPLETED"
    assert _orders(k) == [{"id": "o1", "attempt": 1}]
    [effect] = await k.journal.effects(result.run_id)
    assert (effect.effect_class, effect.status, effect.external_ref) == ("TRANSACTIONAL", "COMMITTED", "orders/o1")
    events = await k.events(result.run_id)
    assert [e.type for e in events if e.type.startswith("STEP_")] == [
        "STEP_INTENDED", "STEP_ATTEMPT_STARTED", "STEP_COMPLETED"
    ]
    replay = await verify(k.journal, result.run_id, place_order.fn, tools=k.tools)
    assert replay.status == "PASS" and ran == [1], "a memoized write is never re-run"


async def test_only_a_transactional_tool_is_handed_the_connection() -> None:
    seen: list[Any] = []

    @tool(effect=EffectClass.PURE, timeout=1.0, name="save_order")
    async def look(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
        seen.append(tctx.db)
        return {}

    k, _ = _keel(look)
    await k.run(place_order, {})
    assert seen == [None]


# --- a crash -----------------------------------------------------------------------------------
@pytest.mark.parametrize("boundary", ["before:effect_exec", "after:effect_exec", "before:outcome_commit"])
async def test_a_crash_before_the_commit_leaves_no_row_and_the_successor_writes_once(boundary: str) -> None:
    """The class's whole claim. At `after:effect_exec` and `before:outcome_commit` the row has been
    written — inside the transaction, which the crash takes with it — so the journal and the table
    agree at the instant of the fault: STARTED with no outcome, and no row (§8.3)."""
    save_order, ran = orders_tool()
    k, clock = _keel(save_order)
    handle = await k.start(place_order, {})
    _crash_at(boundary)
    await _work(k, "w1", await k.journal.claim("w1", timedelta(seconds=TTL)))
    hooks.reset()

    state = fold(await k.events(handle.run_id))
    assert state.steps[0].state == "RUNNING" and _orders(k) == [], "STARTED, no outcome, no row"
    assert ran == ([] if boundary == "before:effect_exec" else [1])

    await _take_over(k, clock, handle.run_id)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED"
    assert _orders(k) == [{"id": "o1", "attempt": 2}], "exactly one row, the successor's"
    abandoned = [e for e in events if e.type == "STEP_FAILED"]
    assert [(e.attempt_no, e.body.error) for e in abandoned] == [(1, "attempt_abandoned")]
    replay = await verify(k.journal, handle.run_id, place_order.fn, tools=k.tools)
    assert replay.status == "PASS"


async def test_a_crash_after_the_commit_is_memoized_and_never_re_run() -> None:
    save_order, ran = orders_tool()
    k, clock = _keel(save_order)
    handle = await k.start(place_order, {})
    _crash_at("after:outcome_commit")
    await _work(k, "w1", await k.journal.claim("w1", timedelta(seconds=TTL)))
    hooks.reset()
    assert _orders(k) == [{"id": "o1", "attempt": 1}], "durable: row and outcome together"

    await _take_over(k, clock, handle.run_id)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert ran == [1] and len(_orders(k)) == 1


# --- a failure is journaled after the rollback ----------------------------------------------------
async def test_a_tool_error_rolls_its_write_back_and_fails_the_step() -> None:
    save_order, ran = orders_tool({1: "raise"})
    k, _ = _keel(save_order)
    result = await k.run(place_order, {})
    assert result.phase == "FAILED" and ran == [1]
    assert _orders(k) == [], "the row written before the raise went with the rollback"
    [failed] = [e for e in await k.events(result.run_id) if e.type == "STEP_FAILED"]
    assert failed.body.error.startswith("ValueError") and not failed.body.retryable
    [effect] = await k.journal.effects(result.run_id)
    assert effect.status == "ABSENT", "provably not applied — never AMBIGUOUS"


async def test_a_timeout_rolls_back_and_the_retry_writes_once() -> None:
    """§8.5: TRANSACTIONAL ⇒ ROLLBACK, then STEP_FAILED{retryable}. The attempt that timed out had
    written its row; the retry's is the only one that commits."""
    save_order, ran = orders_tool({1: "sleep"}, timeout=0.2)
    k, _ = _keel(save_order)
    handle = await k.start(place_order, {})
    await _work(k, "w1", await k.journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED" and ran == [1, 2]
    [failed] = [e for e in events if e.type == "STEP_FAILED"]
    assert (failed.attempt_no, failed.body.error, failed.body.retryable) == (1, "timeout", True)
    assert _orders(k) == [{"id": "o1", "attempt": 2}]


async def test_a_deadlock_is_retried_and_a_refusal_is_not() -> None:
    save_order, ran = orders_tool({1: "deadlock"})
    k, _ = _keel(save_order)
    handle = await k.start(place_order, {})
    await _work(k, "w1", await k.journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED" and ran == [1, 2]
    assert _orders(k) == [{"id": "o1", "attempt": 2}]

    refused, ran = orders_tool({1: "rejected"})
    k, _ = _keel(refused)
    handle = await k.start(place_order, {})
    await _work(k, "w1", await k.journal.claim("w1", timedelta(seconds=TTL)), retry=RETRY)
    assert fold(await k.events(handle.run_id)).phase == "FAILED" and ran == [1] and _orders(k) == []


def test_a_rolled_back_attempt_is_retryable_only_for_a_transient_cause_and_never_unknown() -> None:
    def sql(state: str) -> Exception:
        exc = Exception(state)
        exc.sqlstate = state  # type: ignore[attr-defined]
        return exc

    assert (_rolled_back(TimeoutError()).error, _rolled_back(TimeoutError()).retryable) == ("timeout", True)
    transient = [Deadlock("x"), sql("40001"), sql("53100"), sql("55P03"), sql("57014")]
    final = [ValueError("x"), Rejected("x"), sql("22012"), sql("23505"), sql("55000"), sql("57P01")]
    assert all(_rolled_back(e).retryable for e in transient), "40, 53, 55P03, 57014: the try, not the tool"
    assert not any(_rolled_back(e).retryable for e in final)
    assert not any(_rolled_back(e).unknown for e in transient + final), "the rollback is the answer"


# --- the zombie --------------------------------------------------------------------------------
class Frozen:
    """One worker's handle on the store, stoppable between two statements as SIGSTOP stops a
    process: once frozen every call waits for the thaw — the heartbeat's included, so the lease
    lapses exactly as a stopped process's would."""

    def __init__(self, journal: MemoryJournal) -> None:
        self._journal = journal
        self.thawed = asyncio.Event()
        self.thawed.set()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._journal, name)
        if name == "append":

            @contextlib.asynccontextmanager
            async def append(lease: Any, **kwargs: Any):
                await self.thawed.wait()
                async with attr(lease, **kwargs) as tx:
                    yield tx

            return append
        if inspect.iscoroutinefunction(attr):

            async def call(*args: Any, **kwargs: Any) -> Any:
                await self.thawed.wait()
                return await attr(*args, **kwargs)

            return call
        return attr


async def test_a_holder_that_lost_its_lease_is_fenced_before_its_tool_runs() -> None:
    """§9.1's zombie row: the fence is the first statement of the transaction the tool would run in,
    so a holder stopped between STARTED and that transaction — past its lease, a successor done in
    its place — never runs the tool when it wakes. One row, the successor's."""
    save_order, ran = orders_tool()
    k, clock = _keel(save_order)
    handle = await k.start(place_order, {})
    frozen = Frozen(k.journal)

    def freeze(at: str, detail: dict[str, Any]) -> None:
        if at == "before:effect_exec" and detail.get("name") == "save_order" and frozen.thawed.is_set() and not ran:
            frozen.thawed.clear()

    hooks.install(freeze)
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    holder = Worker(frozen, resolve=k.resolve, tools=k.tools, clock=clock, worker_id="w1", lease_ttl=TTL)
    task = asyncio.create_task(holder.execute(lease))
    for _ in range(200):
        if not frozen.thawed.is_set():
            break
        await asyncio.sleep(0.005)
    assert not frozen.thawed.is_set(), "the holder never reached the TRANSACTIONAL dispatch"

    await _take_over(k, clock, handle.run_id)
    assert _orders(k) == [{"id": "o1", "attempt": 2}]
    frozen.thawed.set()
    with contextlib.suppress(BaseException):
        await asyncio.wait_for(task, 5)

    assert ran == [2], "the zombie woke into a fenced transaction and never ran its tool"
    assert len(_orders(k)) == 1 and fold(await k.events(handle.run_id)).phase == "COMPLETED"


# --- registration ------------------------------------------------------------------------------
def test_registration_takes_a_transactional_tool_that_can_be_handed_the_context() -> None:
    async def needs_tctx(args: Any, tctx: Any) -> None:
        return None

    async def args_only(args: Any) -> None:
        return None

    assert tool(effect=EffectClass.TRANSACTIONAL)(needs_tctx).effect_class is EffectClass.TRANSACTIONAL
    with pytest.raises(ToolRegistrationError, match="must take"):
        tool(effect=EffectClass.TRANSACTIONAL)(args_only)
    with pytest.raises(ContractViolation):
        tool(effect=EffectClass.TRANSACTIONAL, modifiers=(Modifier.STREAMS,))(needs_tctx)
    with pytest.raises(ContractViolation):
        tool(effect=EffectClass.TRANSACTIONAL, modifiers=(Modifier.LOCAL_FS,))(needs_tctx)

    base = tool(effect=EffectClass.EXTERNAL, timeout=1.0)(needs_tctx)

    async def undo_without_tctx(effect_key: str, args: Any, result: Any) -> None:
        return None

    async def undo(effect_key: str, args: Any, result: Any, tctx: Any) -> None:
        return None

    with pytest.raises(ToolRegistrationError, match="TRANSACTIONAL undo"):
        base.compensate_hook(effect=EffectClass.TRANSACTIONAL)(undo_without_tctx)
    base.compensate_hook(effect=EffectClass.TRANSACTIONAL)(undo)
    assert base.compensate_effect is EffectClass.TRANSACTIONAL
