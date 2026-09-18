"""The simulated runtime `KeelMachine` drives (§12.2, §28.6).

The risk in a stateful property suite is that the sim drifts from the runtime and starts proving
things about itself. The mitigation is that there is almost no sim here. The journal is the real
`MemoryJournal`; the worker, step engine, inbox drain, approvals, delegation, takeover, reaper, retry
policy and breaker are the real ones; the judge is `crashproof/verifier/invariants.py`, the same
functions the benchmark calls. Four things are fake, and only four:

    the clock     `SimClock`: `now()` moves only when a rule ticks it, and every wait the runtime
                  makes — attempt timeout, heartbeat, in-process backoff — goes through the clock's
                  `sleep`/`timeout` seam (§12.2), so a timeout fires because a rule said so
    the World     the harness's own `World`, in-process: its dedup and its oracle, with every call
                  that leaves the process *held* until a rule lands it (`Held`)
    the process   a worker is one asyncio task over a journal handle that dies with it; a kill is
                  abandonment (§11.10), a pause is a task whose timers stop firing
    the program   one data-driven program (`sim_agent`) and its child (`sim_child`), whose script and
                  tool registry are generated data (§12.5)

Hypothesis rules are synchronous; the sim owns one event loop and each rule runs it until every
worker is parked on something only a rule can release (`settle`). There is no wall clock in any
decision a rule makes: the only real-time reads left are the pre-dispatch margin's monotonic clock and
the heartbeat's, and the lease is sized so an example never gets near them.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from crashproof.adapters.keel import KeelAdapter
from crashproof.faults import spec as fault_spec
from crashproof.verifier import invariants
from crashproof.world import oracle
from crashproof.world.services import Endpoint, World
from keel import Continue, Keel
from keel.client import program
from keel.core import aio
from keel.core.clock import FakeClock
from keel.core.errors import Rejected, StoreUnavailable, UnknownOutcome
from keel.core.ids import uuid7
from keel.core.protocols import EffectClass, Idempotency, ProbeResult
from keel.effects.registry import tool
from keel.events import ChildSpawned, RecoveryStarted, RunCompleted, RunCreated
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import DelegationRow, RunRow, SignalRow
from keel.providers.protocol import ModelChunk, ModelResponse, Usage
from keel.runtime import human
from keel.replay.verify import verify as run_verify
from keel.runtime import hooks
from keel.runtime.breaker import CircuitBreaker
from keel.runtime.delegation import Delegation
from keel.runtime.reaper import Reaper
from keel.runtime.retry import NO_RETRY, RetryPolicy
from keel.runtime.worker import Worker
from keel.state.fold import RESOLVED_UNKNOWN, fold

#: Long against the tool timeouts (`LeaseTooShort`) and against an example's wall time, because the
#: pre-dispatch margin is still measured on the loop's real monotonic clock.
TTL = 30.0
GRACE = 5.0
MODEL_TIMEOUT = 10.0
SLOTS = ("W0", "W1")
#: Journal calls one worker may make inside one `settle` before the sim calls it a livelock. A
#: worker that spins without awaiting anything a rule controls never yields the loop back, so the
#: only place it can be stopped is its own journal handle.
SPIN_LIMIT = 2_000
#: Boundaries a journal fault may be aimed at: the ones beside a journal write. `*:effect_exec` are
#: inside the tool's own `except Exception`, where a store error is indistinguishable from a tool's.
JOURNAL_FAULT_BOUNDARIES = (
    "before:intent_commit",
    "after:intent_commit",
    "before:attempt_commit",
    "after:attempt_commit",
    "before:outcome_commit",
    "after:outcome_commit",
    "before:lease_release",
    "before:signal_consume",
    "after:signal_consume",
    "before:child_spawn",
    "before:segment_write",
    # A STEP_CHUNK append (§10.7): the store failing around a batch leaves the attempt open.
    "during:stream",
)
SCHEMA = {"type": "object", "required": ["ok"]}
#: A streamed model call is three chunks of 300 output tokens: each crosses the 256-token batch, so
#: every chunk is its own STEP_CHUNK and `during:stream` fires three times (§10.7, §21.3 item 6).
STREAM_CHUNKS, STREAM_CHUNK_TOKENS, STREAM_MAX_TOKENS = 3, 300, 1024

CURRENT: contextvars.ContextVar[SimWorker | None] = contextvars.ContextVar("sim_worker", default=None)


class SimLivelock(BaseException):
    """A worker made `SPIN_LIMIT` journal calls without parking. A `BaseException`, like
    `hooks.Crash`, so nothing in the runtime can catch it and keep spinning."""


# --- the program (§12.2): fixed code, generated script ------------------------------------------
class SimState(BaseModel):
    """What restarts `sim_agent` at a continuation boundary: the script position and the results so
    far. The plan and the compaction summary are Keel's, never in here (§18.3)."""

    i: int = 0
    out: list[Any] = []


@program(name="sim_agent", version="1.0", state=SimState)
async def sim_agent(ctx: Any, args: dict[str, Any], state: SimState | None = None) -> dict[str, Any]:
    """`model` asks, `tool` calls (behind `ctx.approve` when the tool is gated), `delegate` fans
    out, `compact` summarises, `sleep` parks on a timer, `continue` ends the segment. Every op is a
    safe point, so a worker with a small N cuts forced boundaries too. Tool args carry the run id so
    two runs never share a logical identity at the World."""
    state = state or SimState()
    out: list[Any] = list(state.out)
    script = args["script"]
    for i in range(state.i, len(script)):
        op = script[i]
        ctx.segment_point(SimState(i=i, out=out))
        if op["op"] == "model" and op.get("stream"):
            # STREAMS (§9.3): room for every chunk the sim delivers inside the reservation, as a real
            # provider stops at `max_tokens` — so a charge can only ever be the reservation or usage.
            await ctx.model([{"role": "user", "content": f"decide {i}"}], name=f"decide{i}",
                            max_tokens=STREAM_MAX_TOKENS, stream=True)
        elif op["op"] == "model":
            await ctx.model([{"role": "user", "content": f"decide {i}"}], name=f"decide{i}", max_tokens=16)
        elif op["op"] == "continue":
            return Continue(SimState(i=i + 1, out=out))
        elif op["op"] == "compact":
            await ctx.compact(max_tokens=16)
        elif op["op"] == "sleep":
            await ctx.sleep(op["s"])
        elif op["op"] == "tool":
            call = {"n": i, "run": str(ctx.run_id)}
            if op.get("gated"):
                decision = await ctx.approve({"op": i}, expires_in=op.get("expires_in"), gates=(op["tool"], call))
                if decision["decision"] != "granted":
                    return {"stopped": decision["decision"], "out": out}
            await ctx.tool(op["tool"], **call)
            out.append(i)
        else:
            results = await ctx.delegate_many(
                [
                    Delegation(
                        program="sim_child",
                        task=f"{i}.{k}",
                        args={"script": op["child"], "violate": op["violate"], "fail": op["fail"]},
                        allowed_tools=frozenset(c["tool"] for c in op["child"] if c["op"] == "tool"),
                        result_schema=SCHEMA,
                        on_failure=op["on_failure"],
                        max_retries=1,
                    )
                    for k in range(op["n"])
                ]
            )
            out.append([r.status for r in results])
    return {"out": out}


@program(name="sim_child", version="1.0")
async def sim_child(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    for i, op in enumerate(args["script"]):
        if op["op"] == "model":
            await ctx.model([{"role": "user", "content": f"child {i}"}], name=f"child{i}", max_tokens=16)
        else:
            await ctx.tool(op["tool"], n=i, run=str(ctx.run_id))
    if args.get("fail"):
        raise RuntimeError("the child's own failure")
    return {"nope": True} if args.get("violate") else {"ok": True}


# --- generated data ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ToolDecl:
    name: str
    cls: str = "PURE"
    resolution: str = "escalate"
    dedup: bool = True
    gated: bool = False
    timeout: float = 1.0

    @property
    def endpoint(self) -> str:
        return f"{self.name}.call"

    @property
    def claim(self) -> str:
        """§12.4's S1 sim form. EXTERNAL with a probe re-attempts after ABSENT, so a request still in
        flight can land beside the re-attempt: at-least-once. EXTERNAL with `escalate` never
        re-sends, and an IDEMPOTENT tool against a receiver that ignores its key is reported raw."""
        if self.cls == "EXTERNAL":
            return "at_least_once" if self.resolution == "probe" else "effectively_once"
        if self.cls == "IDEMPOTENT" and not self.dedup:
            return "at_least_once"
        return KeelAdapter.claims[self.cls]


class SimRetry(RetryPolicy):
    """The real policy with the jitter drawn at the top of its window: a backoff that decides
    between sleeping and parking must not be a coin flip the example cannot record."""

    def backoff_s(self, attempt_no: int, *, rng: Any = None) -> float:
        return super().backoff_s(attempt_no, rng=_TOP)


class _Top:
    @staticmethod
    def random() -> float:
        return 1.0


_TOP = _Top()
POLICIES = {"none": NO_RETRY, "retry": SimRetry(max_attempts=3, base_s=0.5, max_backoff_s=4.0)}


# --- the fakes --------------------------------------------------------------------------------
class SimClock(FakeClock):
    """`FakeClock` whose waits are timers a tick fires (§12.2). A timer belongs to the worker whose
    task armed it, so a paused worker's heartbeat and timeout stop with it and fire late on resume."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.loop = loop
        self.timers: list[list[Any]] = []  # [due, owner, kind, fire]

    def _arm(self, seconds: float, kind: str, fire: Any) -> list[Any]:
        timer = [self.now() + timedelta(seconds=seconds), CURRENT.get(), kind, fire]
        self.timers.append(timer)
        return timer

    def _disarm(self, timer: list[Any]) -> None:
        with contextlib.suppress(ValueError):
            self.timers.remove(timer)

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        fut = self.loop.create_future()
        # The worker's own task sleeps for a backoff; any other task of its (the heartbeat) keeps time.
        w = CURRENT.get()
        kind = "sleep" if w is not None and asyncio.current_task() is w.task else "heartbeat"
        timer = self._arm(seconds, kind, lambda: fut.done() or fut.set_result(None))
        try:
            await fut
        finally:
            self._disarm(timer)

    @contextlib.asynccontextmanager
    async def timeout(self, seconds: float):
        async with asyncio.timeout(None) as cm:
            timer = self._arm(seconds, "timeout", lambda: cm.expired() or cm.reschedule(self.loop.time()))
            try:
                yield cm
            finally:
                self._disarm(timer)

    async def fire_due(self, *, only: SimWorker | None = None) -> int:
        """Inside the loop, because `Timeout.reschedule` needs a running one."""
        fired = 0
        for timer in sorted(self.timers, key=lambda t: t[0]):
            due, owner, _, fire = timer
            if due > self.now() or (only is not None and owner is not only):
                continue
            if owner is not None and owner.state != "live":
                continue
            self._disarm(timer)
            fire()
            fired += 1
        return fired


@dataclass(eq=False)
class SimWorker:
    name: str
    slot: str
    lease: Any
    worker: Any = None
    task: asyncio.Task | None = None
    state: str = "live"  # live | paused | dead | done
    at: dict[str, Any] = field(default_factory=dict)
    crash_at: str | None = None
    drain_deadline: Any = None
    calls: int = 0


class _Handle:
    """What a worker process holds of the store: dead with its worker (§12.2 — a killed worker can
    neither release a lease nor append an outcome), and the one place a spinning worker is caught."""

    def __init__(self, journal: MemoryJournal, owner: SimWorker, sim: Sim) -> None:
        self._journal, self._owner, self._sim = journal, owner, sim

    def __getattr__(self, name: str) -> Any:
        w = self._owner
        if w.state == "dead":
            raise hooks.Crash(f"{w.name} is dead; its journal handle went with it")
        w.calls += 1
        if w.calls > SPIN_LIMIT:
            self._sim.errors.append(f"{w.name}: {SPIN_LIMIT} journal calls without parking (last: {name})")
            raise SimLivelock(w.name)
        return getattr(self._journal, name)


@dataclass(eq=False)
class Held:
    """A call that left the worker and has not landed: the sim's "in flight"."""

    id: int
    worker: SimWorker
    run_id: Any
    step: int
    attempt: int
    name: str
    decl: ToolDecl | None
    args: dict[str, Any]
    key: str | None
    future: asyncio.Future
    landed: bool = False
    #: Its worker was killed while waiting on it. The request had left; it may still arrive.
    orphaned: bool = False
    #: A streamed model call: its answer is a list of chunks, landed whole or cut (`truncate_stream`).
    stream: bool = False

    @property
    def landmark(self) -> str:
        return f"tool:{self.name}" if self.decl is not None else f"model:{self.name}"

    @property
    def awaited(self) -> bool:
        return not self.future.done()


@dataclass(slots=True)
class Landing:
    run_id: Any
    step: int
    attempt: int
    label: str
    ts: float
    effect_key: str | None
    endpoint: str
    #: Awaited by the worker that holds the run's lease. A landing nobody current was waiting for —
    #: orphaned by a kill, late after a timeout, a zombie's after a takeover — is §8.4's residual:
    #: the fence protects the journal and cannot reach a third party.
    current: bool = True


class SimProvider:
    name = "sim"

    def __init__(self, sim: Sim) -> None:
        self.sim = sim

    async def count_tokens(self, req: Any) -> int:
        return 10

    async def complete(self, req: Any) -> Any:
        return await self.sim.call(None, {}, None)

    async def stream(self, req: Any) -> Any:
        """The chunks a rule landed, in order; a cut stream ends without the final response."""
        for chunk in await self.sim.call(None, {}, None, stream=True):
            yield chunk


# --- the sim ----------------------------------------------------------------------------------
class Sim:
    def __init__(
        self,
        tools: list[ToolDecl],
        script: list[dict[str, Any]],
        *,
        retry: str = "none",
        model_retry: str = "none",
        segment_steps: int = 400,
    ) -> None:
        self.decls = {t.name: t for t in tools}
        self.script = script
        self.retry_name, self.model_retry_name = retry, model_retry
        #: N for the forced continuation boundary (§18.3): 400 never cuts in an example; 2 cuts often.
        self.segment_steps = segment_steps
        self.loop = aio.loop_factory()
        asyncio.set_event_loop(self.loop)
        self.clock = SimClock(self.loop)
        self.journal = MemoryJournal(clock=self.clock)
        self.world = World(
            Endpoint(id=t.endpoint, service=t.name, kind="read" if t.cls == "PURE" else "write", dedup=t.dedup)
            for t in tools
        )
        self.provider = SimProvider(self)
        self.keel = Keel(
            journal=self.journal,
            provider=self.provider,
            tools=[self._tool(t) for t in tools],
            programs=[sim_agent, sim_child],
            clock=self.clock,
        )
        self.workers: dict[str, SimWorker] = {}
        self.incarnation = 0
        self.held: list[Held] = []
        self.landings: list[Landing] = []
        self.errors: list[str] = []
        self.journal_faults: Counter[str] = Counter()
        self.observed: Counter[tuple[str, str]] = Counter()
        self.signals_sent: list[SignalRow] = []
        self.signals_tried = 0
        self.stray_parents: set[Any] = set()
        #: A kill aimed at a slot with no worker yet: the next worker there dies at the boundary if its
        #: first settle reaches it, which is how a successor's own recovery window is addressed.
        self.armed: dict[str, str] = {}
        #: Event types and effect-row states this example has reached: what `hypothesis.target` steers by.
        self.reached: set[str] = set()
        self.acquisitions = 0
        #: The rules that did something, in order, with what `to_fault_spec` needs to place them.
        self.log: list[dict[str, Any]] = []
        self._terminal: dict[Any, str] = {}
        self._applied_high: dict[str, int] = {}
        #: What the provider produced per run, streamed or not, landed to anyone (S9).
        self.billed: Counter[Any] = Counter()
        hooks.install(self._hook)
        handle = self.loop.run_until_complete(self.keel.start(sim_agent, {"script": script}))
        self.root = handle.run_id

    # --- plug-ins the runtime takes ---------------------------------------------------------
    def _tool(self, decl: ToolDecl) -> Any:
        async def fn(args: dict[str, Any], tctx: Any) -> Any:
            key = tctx.effect_key if decl.cls == "IDEMPOTENT" else None
            return await self.call(decl, dict(args), key)

        spec = tool(
            effect=EffectClass(decl.cls),
            resolution=decl.resolution if decl.cls == "EXTERNAL" else "escalate",
            timeout=decl.timeout,
            idempotency=Idempotency.KEY if decl.cls == "IDEMPOTENT" else Idempotency.NONE,
            name=decl.name,
        )(fn)
        if decl.cls == "EXTERNAL" and decl.resolution == "probe":

            async def probe(effect_key: str, args: dict[str, Any], tctx: Any) -> ProbeResult:
                answer = oracle.probe(self.world, endpoint=decl.endpoint, args=dict(args))
                return ProbeResult(
                    answer["verdict"], evidence=answer["evidence"], result=answer.get("result"),
                    external_ref=answer.get("external_ref"),
                )

            spec.probe_hook(probe)
        return spec

    async def call(self, decl: ToolDecl | None, args: dict[str, Any], key: str | None, *, stream: bool = False) -> Any:
        """Every call that leaves a worker. A PURE read lands at once; everything else is held."""
        w = CURRENT.get()
        at = dict(w.at) if w is not None else {}
        run_id = w.lease.run_id if w is not None else None
        step, attempt = int(at.get("step_index", -1)), int(at.get("attempt_no", 0))
        if decl is not None and decl.cls == "PURE":
            return self._land_request(run_id, step, attempt, decl, args, key)
        name = decl.name if decl is not None else str(at.get("name"))
        h = Held(len(self.held), w, run_id, step, attempt, name, decl, args, key, self.loop.create_future(),
                 stream=stream)
        self.held.append(h)
        return await h.future

    def _answer(self, h: Held, k: int | None = None) -> Any:
        """A model call's answer — one response, or a stream's chunks: all of them and the final
        response, or the first `k` and nothing after. The provider bills what it produced, whoever
        was still listening (§12.4 S9's sim form: completed *and* abandoned attempts)."""
        if not h.stream:
            self.billed[h.run_id] += 2
            return ModelResponse(text="ok", usage=Usage(input_tokens=1, output_tokens=1))
        n = STREAM_CHUNKS if k is None else k
        usage = [Usage(input_tokens=10, output_tokens=STREAM_CHUNK_TOKENS * j) for j in range(1, n + 1)]
        chunks = [ModelChunk(text=f"c{j} ", usage_cum=u) for j, u in enumerate(usage, 1)]
        self.billed[h.run_id] += 10 + STREAM_CHUNK_TOKENS * n
        if k is None:
            chunks.append(ModelChunk(usage_cum=usage[-1], response=ModelResponse(text="ok", usage=usage[-1])))
        return chunks

    def truncate(self, h: Held, k: int) -> None:
        """`truncate_stream(k)` (§12.3): k chunks, then the stream ends with no final response."""
        self.log.append({"rule": "truncate_stream", "landmark": h.landmark, "k": k, "occurrence": h.attempt})
        h.landed = True
        if not h.future.done():
            h.future.set_result(self._answer(h, k))
        self.settle()

    def _land_request(self, run_id: Any, step: int, attempt: int, decl: ToolDecl, args: dict[str, Any],
                      key: str | None, current: bool = True) -> Any:
        result = self.world.receive(decl.endpoint, args, effect_key=key)
        label = self.world.receipts[-1].logical_identity
        self.landings.append(
            Landing(run_id, step, attempt, label, self.clock.now().timestamp(), key, decl.endpoint, current)
        )
        return result

    def land(self, h: Held, outcome: str = "ok") -> None:
        """The World receives `h` (unless refused at the door) and answers — to nobody, if nobody
        is listening any more."""
        if outcome == "rejected" and h.decl is not None and h.decl.dedup and h.key and self.world.lookup_key(h.key):
            outcome = "ok"  # a receiver that honours keys answers an applied key with its result, never a 422
        if outcome != "rejected" and h.decl is not None:
            current = (h.awaited and h.worker.state == "live"
                       and self.journal._runs[h.run_id].lease_epoch == h.worker.lease.epoch)
            result = self._land_request(h.run_id, h.step, h.attempt, h.decl, h.args, h.key, current)
        else:
            result = None
        h.landed = True
        if h.future.done() or outcome == "dropped":
            return
        if outcome == "ok":
            h.future.set_result(result if h.decl is not None else self._answer(h))
        elif outcome == "error":
            h.future.set_exception(UnknownOutcome("500 after the request was applied"))
        else:
            h.future.set_exception(Rejected("422: refused at the door"))

    def _hook(self, boundary: str, detail: dict[str, Any]) -> None:
        kind, name = detail.get("kind"), detail.get("name")
        landmark = f"{kind}:{name}" if kind and name else "lease:*"
        # The stream boundary is addressed by its batch, as the hook injector names it (§24.5).
        named = f"during:stream(chunk={detail['chunk']})" if boundary == "during:stream" else boundary
        self.observed[(landmark, named)] += 1
        w = CURRENT.get()
        if w is None:
            return
        w.at = {"boundary": boundary, **detail}
        if w.crash_at == boundary:
            w.crash_at = None
            self.log.append({"rule": "crash_at_boundary", "boundary": named, "landmark": landmark,
                             "occurrence": self.observed[(landmark, named)]})
            self._kill(w)
            raise hooks.Crash(f"{w.name} killed at {boundary}")
        if self.journal_faults[boundary] > 0 and boundary in JOURNAL_FAULT_BOUNDARIES:
            self.journal_faults[boundary] -= 1
            self.log.append({"rule": "journal_fault", "boundary": named, "landmark": landmark,
                             "occurrence": self.observed[(landmark, named)]})
            raise StoreUnavailable(f"store unavailable at {boundary}")

    # --- the loop ---------------------------------------------------------------------------
    def settle(self) -> None:
        """Run the loop until every task is parked on something only a rule can release."""
        for w in self.workers.values():
            w.calls = 0

        async def idle() -> None:
            for _ in range(100_000):
                await asyncio.sleep(0)
                if not self.loop._ready:  # type: ignore[attr-defined]
                    return
            self.errors.append("the loop never went idle")

        self.loop.run_until_complete(idle())
        for w in self.workers.values():
            if w.calls or w.state != "live":
                w.crash_at = None  # it moved and parked again: the aimed kill fired, or it missed

    def run(self, coro: Any) -> Any:
        return self.loop.run_until_complete(coro)

    def _kill(self, w: SimWorker) -> None:
        w.state = "dead"
        for h in self.held:
            if h.worker is w and h.awaited:
                h.orphaned = True
        if w.task is not None and w.task is not asyncio.current_task(self.loop):
            w.task.cancel()

    def _ended(self, w: SimWorker, task: asyncio.Task) -> None:
        if task.cancelled():
            w.state = "dead"
            return
        exc = task.exception()
        if exc is None:
            w.state = "done" if w.state != "dead" else "dead"
            return
        w.state = "dead"
        if not isinstance(exc, (hooks.Crash, SimLivelock)):
            self.errors.append(f"{w.name}: {type(exc).__name__}: {exc} escaped Worker.execute")

    # --- rules ------------------------------------------------------------------------------
    def live(self) -> list[SimWorker]:
        return [w for w in self.workers.values() if w.state == "live"]

    def slot(self, slot: str) -> SimWorker | None:
        w = self.workers.get(slot)
        return w if w is not None and w.state in ("live", "paused") else None

    def sweep(self) -> None:
        """The reaper's three sweeps, on demand (§12.2): orphaned leases, due timers, strays."""
        reaper = Reaper(self.journal, worker_id="reaper", lease_ttl=TTL, cancel_grace=GRACE)
        self.run(reaper.sweep())
        self.run(reaper.timers())
        self.run(reaper.strays())

    def restart_worker(self, slot: str) -> bool:
        if self.slot(slot) is not None:
            return False
        self.sweep()
        self.incarnation += 1
        w = SimWorker(name=f"{slot}.{self.incarnation}", slot=slot, lease=None)
        lease = self.run(self.journal.claim(w.name, timedelta(seconds=TTL)))
        if lease is None:
            return False
        self.acquisitions += 1
        w.lease = lease
        w.worker = Worker(
            _Handle(self.journal, w, self),
            resolve=self.keel.resolve,
            provider=self.provider,
            tools=self.keel.tools,
            clock=self.clock,
            worker_id=w.name,
            lease_ttl=TTL,
            retry=POLICIES[self.retry_name],
            model_retry=POLICIES[self.model_retry_name],
            model_timeout_s=MODEL_TIMEOUT,
            cancel_grace=GRACE,
            breaker=CircuitBreaker(n_open=2, cooldown_s=10.0),
            segment_steps=self.segment_steps,
        )
        self.workers[slot] = w
        w.crash_at = self.armed.pop(slot, None)
        ctx = contextvars.copy_context()
        ctx.run(CURRENT.set, w)
        w.task = self.loop.create_task(w.worker.execute(lease), context=ctx)
        w.task.add_done_callback(lambda t, w=w: self._ended(w, t))
        self.settle()
        return True

    def completable(self) -> list[Held]:
        """Held calls a rule may land: awaited by a live worker, or orphaned by a dead one (the
        request left before the kill and may still arrive)."""
        return [
            h for h in self.held
            if not h.landed and ((h.awaited and h.worker.state == "live") or h.orphaned)
        ]

    def late(self) -> list[Held]:
        """Held calls whose attempt a timeout ended on a live worker: nobody awaits them, and the
        request may still land — `duplicate_response`'s precondition (§12.3)."""
        return [h for h in self.held if not h.landed and not h.orphaned and h.future.cancelled()]

    def complete(self, h: Held, outcome: str) -> None:
        if outcome != "ok":
            self.log.append({"rule": "complete_effect", "outcome": outcome, "landmark": h.landmark,
                             "tool": h.decl is not None, "occurrence": h.attempt})
        self.land(h, outcome)
        self.settle()

    def advance(self, n: int) -> None:
        for _ in range(n):
            ready = [h for h in self.completable() if h.worker.state == "live"]
            if not ready:
                return
            self.complete(ready[0], "ok")

    def crash(self, slot: str, boundary: str) -> None:
        """Aim a kill at `boundary` (§12.3). A parked worker dies there if the rule that next moves it
        reaches the boundary before it parks again, and the aim lapses if it does not; a free slot
        aims at the next worker started in it. `during:effect_exec` kills a worker parked on a held
        call now — the request has left, and may still land."""
        w = self.slot(slot)
        if w is None:
            if boundary != "during:effect_exec":
                self.armed[slot] = boundary
            return
        if w.state != "live":
            return
        parked = [h for h in self.held if h.worker is w and h.awaited]
        if boundary != "during:effect_exec":
            w.crash_at = boundary
            return
        if not parked:
            return
        self.log.append({"rule": "crash_at_boundary", "boundary": boundary, "landmark": parked[0].landmark,
                         "occurrence": parked[0].attempt})
        self._kill(w)
        self.settle()

    def drain(self, slot: str, grace: float) -> None:
        w = self.slot(slot)
        if w is None or w.state != "live" or w.worker.draining:
            return
        w.worker.draining = True
        w.drain_deadline = self.clock.now() + timedelta(seconds=grace)
        self.log.append({"rule": "drain", "grace": grace})

    def tick(self, seconds: float) -> None:
        self.clock.advance(seconds)
        for w in self.live():
            if w.drain_deadline is not None and self.clock.now() >= w.drain_deadline:
                self._kill(w)  # the grace ran out first: indistinguishable from a kill (§12.3)
        self.run(self.clock.fire_due())
        self.settle()

    def tick_to(self, when: Any) -> None:
        self.tick(max(0.0, (when - self.clock.now()).total_seconds()) + 0.001)

    def timeout(self, h: Held) -> None:
        timers = [t for t in self.clock.timers if t[1] is h.worker and t[2] == "timeout"]
        if not timers:
            return
        self.log.append({"rule": "timeout", "landmark": h.landmark, "tool": h.decl is not None,
                         "occurrence": h.attempt})
        self.tick_to(min(t[0] for t in timers))

    def lease_expiry(self, slot: str) -> None:
        w = self.slot(slot)
        if w is None or w.state != "live":
            return
        row = self.run(self.journal.run_row(w.lease.run_id))
        parked = [h for h in self.held if h.worker is w and h.awaited]
        w.state = "paused"
        if parked:
            where = {"landmark": parked[0].landmark, "tool": parked[0].decl is not None,
                     "occurrence": parked[0].attempt}
        else:  # parked on a backoff: the pause lands before the next attempt of the step it last touched
            kind, name = w.at.get("kind"), w.at.get("name")
            where = {"landmark": f"{kind}:{name}" if kind else "lease:*", "tool": kind == "tool",
                     "occurrence": int(w.at.get("attempt_no") or 0) + 1}
        self.log.append({"rule": "lease_expiry", **where})
        deadlines = [d for d in (row.lease_expires_at, row.attempt_deadline) if d is not None]
        if deadlines:
            self.tick_to(max(deadlines))
        self.run(self.journal.reap())

    def zombie_resume(self, slot: str) -> None:
        w = self.workers.get(slot)
        if w is None or w.state != "paused":
            return
        w.state = "live"
        self.log.append({"rule": "zombie_resume"})
        for h in [h for h in self.held if h.worker is w and h.awaited and not h.landed]:
            self.land(h, "ok")  # the request it was holding lands, and its answer arrives
        self.settle()
        self.run(self.clock.fire_due(only=w))
        self.settle()

    def duplicate_response(self, h: Held) -> None:
        self.log.append({"rule": "duplicate_response", "landmark": h.landmark, "occurrence": h.attempt})
        self.land(h, "ok")
        self.settle()

    def deliver(self, run_id: Any, kind: str, which: str = "open") -> None:
        self.signals_tried += 1
        payload: dict[str, Any] = {"by": "sim"}
        type_ = kind
        if kind == "resolve":
            # A truthful human (§7.3): `completed` naming what the World applied for that step, or
            # `failed` when it applied nothing. A human who lies breaks S2/C3 by definition, and that
            # is the human's error, not the runtime's. `unknown` names a step that is not unresolved.
            st = fold(self.events(run_id))
            unresolved = [s.step_index for s in st.steps.values() if s.state == "RESOLVED_UNKNOWN"]
            step = unresolved[-1] if unresolved and which != "unknown" else st.next_step_index + 7
            applied = self.world.applied_counts()
            labels = [x.label for x in self.landings if x.run_id == run_id and x.step == step and applied.get(x.label)]
            type_, payload = "custom", human.signal_payload(
                step, "completed" if labels else "failed", evidence="sim",
                result={"external_ref": labels[-1]} if labels else None, by="sim",
            )
        if kind in ("approve", "reject"):
            approvals = list(fold(self.events(run_id)).approvals.values())
            open_ = [a for a in approvals if not a.terminal]
            decided = [a for a in approvals if a.terminal]
            named = {"open": open_, "stale": decided}.get(which, [])
            if which == "unknown":
                payload["approval_id"] = str(uuid7())
            elif named:
                payload["approval_id"] = str(named[-1].approval_id)
        row = SignalRow(signal_id=uuid7(), run_id=run_id, type=type_, payload=payload,
                        client_key=f"sim:{len(self.signals_sent)}")
        if self.run(self.journal.insert_signal(row)):
            self.signals_sent.append(row)
            self.log.append({"rule": "deliver_signal", "kind": kind, "which": which})

    def duplicate_signal(self, same_key: bool) -> None:
        self.signals_tried += 1
        last = self.signals_sent[-1]
        row = SignalRow(signal_id=uuid7(), run_id=last.run_id, type=last.type, payload=dict(last.payload),
                        client_key=last.client_key if same_key else f"sim:{len(self.signals_sent)}")
        if self.run(self.journal.insert_signal(row)):
            self.signals_sent.append(row)
        self.log.append({"rule": "duplicate_signal", "kind": last.type, "same_key": same_key})

    def stray_child(self, child: list[dict[str, Any]]) -> None:
        """§17.7's liveness rule needs a child whose parent is already terminal, and no program can
        leave one — a DELEGATE step cannot settle with a child open. So one is built the way
        `test_the_reaper_collects_a_child_that_outlived_its_parent` builds it: through the public
        transaction API, the only way a child comes to exist."""
        parent = self.run(self.keel.start(sim_agent, {"script": []})).run_id
        lease = self.run(self.journal.acquire(parent, "sim:constructor", timedelta(seconds=TTL)))
        child_id = uuid7()
        args = {"task": "stray", "script": child, "violate": False, "fail": False}

        async def build() -> None:
            async with self.journal.append(lease) as tx:
                await tx.append(RecoveryStarted(lease_epoch=lease.epoch, cause="RESUME", from_seq=1))
                seq = await tx.append(ChildSpawned(step_index=0, child_run_id=child_id, delegation_id=uuid7()))
                await tx.create_child(
                    RunRow(run_id=child_id, run_root_id=child_id, program="sim_child",
                           program_version=sim_child.version, keel_version="sim", phase="CREATED",
                           trace_id=parent, args=args, parent_run_id=parent),
                    RunCreated(program="sim_child", program_version=sim_child.version, args=args,
                               parent_run_id=parent),
                    DelegationRow(delegation_id=uuid7(), parent_run_id=parent, parent_step_index=0,
                                  child_run_id=child_id, role="worker", contract={}, budget_reserved={},
                                  spawned_seq=seq),
                )
                await tx.append(RunCompleted(result={"stray": True}))
            await self.journal.release(lease, phase="COMPLETED")

        self.run(build())
        self.stray_parents.add(parent)
        self.log.append({"rule": "stray_child"})

    def example(self, id_: str) -> dict[str, Any]:
        """What `to_fault_spec` takes: the generated registry and script, and the rules that did something."""
        return {"id": id_, "tools": [asdict(d) for d in self.decls.values()], "script": self.script,
                "rules": list(self.log)}

    # --- reads ------------------------------------------------------------------------------
    def events(self, run_id: Any) -> list[Any]:
        return self.run(self.journal.read(run_id))

    def run_ids(self) -> list[Any]:
        return list(self.journal._runs)

    def open_runs(self) -> list[Any]:
        return [r for r, row in self.journal._runs.items() if row.terminal_at is None]

    def claimable(self) -> bool:
        """Would `restart_worker` find work? The claim's candidate set after the reaper's sweeps,
        read from the rows — only so the machine does not spend its steps on restarts into nothing."""
        now = self.clock.now()
        pending = {s.run_id for s in self.journal._signals.values() if s.consumed_seq is None}
        for r in self.journal._runs.values():
            if r.terminal_at is not None:
                continue
            if r.lease_expires_at is not None and (r.lease_expires_at >= now or (r.attempt_deadline or now) > now):
                continue
            parent = self.journal._runs.get(r.parent_run_id)
            if (r.runnable_at is not None or r.run_id in pending or r.lease_expires_at is not None
                    or (r.wake_at is not None and r.wake_at <= now)
                    or (parent is not None and parent.terminal_at is not None)):
                return True
        return False

    def fingerprint(self) -> tuple:
        return (sum(len(v) for v in self.journal._events.values()), len(self.landings), len(self.errors),
                tuple(w.state for w in self.workers.values()), sum(self.world.applied_counts().values()),
                sum(self.billed.values()))

    # --- invariants (§12.4) -----------------------------------------------------------------
    def check(self) -> None:
        """Everything checked after every rule. Each failure names its invariant."""
        assert not self.errors, {"worker": self.errors}
        if self.fingerprint() == getattr(self, "_checked", None):
            return  # nothing a check reads has moved since the last one
        runs = {r: self.events(r) for r in self.run_ids()}
        states = {r: fold(evs) for r, evs in runs.items()}
        self.reached.update(e.type for evs in runs.values() for e in evs)
        self.reached.update(f"effect:{e.effect_class}:{e.status}" for e in self.journal._effects.values())
        started = {
            (r, e.step_index, e.attempt_no): e for r, evs in runs.items() for e in evs
            if e.type == "STEP_ATTEMPT_STARTED"
        }
        for r, evs in runs.items():
            st = states[r]
            # J2: seq contiguous; at most one open step.
            assert [e.seq for e in evs] == list(range(1, len(evs) + 1)), {"J2": f"{r}: seq gap"}
            open_steps = [s.step_index for s in st.steps.values() if not s.settled and s.state != RESOLVED_UNKNOWN]
            assert len(open_steps) <= 1, {"J2": f"{r}: open steps {open_steps}"}
            # J1: no event from an epoch older than one already appended — a fenced writer wrote nothing.
            epochs = [e.lease_epoch for e in evs[1:]]
            assert epochs == sorted(epochs), {"J1": f"{r}: epochs {epochs}"}
            # A terminal run stays terminal, in the phase it ended in.
            if r in self._terminal:
                assert st.phase == self._terminal[r], {"terminal": f"{r}: {self._terminal[r]} -> {st.phase}"}
            elif st.terminal:
                self._terminal[r] = st.phase
                self._c1(r, st)
            verdicts = invariants.verify(self.facts(r, evs, st))
            failed = {n: verdicts.findings[n].detail for n in ("S2", "S3", "S4", "S5", "S6", "S7", "C2")
                      if verdicts.as_dict().get(n) == "FAIL"}
            assert not failed, {str(r): failed, "counterexamples": verdicts.counterexamples()}
            # S8 (a): a parent terminal only once every child is. A constructed stray is the exception
            # it was built to be; L1 judges that the reaper closes it.
            if st.terminal and r not in self.stray_parents:
                open_children = [c for c, row in self.journal._runs.items()
                                 if row.parent_run_id == r and row.terminal_at is None]
                assert not open_children, {"S8": f"{r} {st.phase} with children open: {open_children}"}
            # S9, sim form (§12.4): the journal charges at least what the provider produced for this
            # run — completed, abandoned and cut attempts alike, streamed chunks included.
            assert st.charged.tokens_charged >= self.billed[r], {
                "S9": f"{r}: charged {st.charged.tokens_charged} < billed {self.billed[r]}"}
        # S1, per endpoint, against each tool's own claim.
        for decl in self.decls.values():
            prefix = decl.endpoint + "#"
            applied = {k: n for k, n in self.world.applied_counts().items() if k.startswith(prefix)}
            v = invariants.verify(invariants.TrialFacts(world_applied=applied, effect_class=decl.cls,
                                                        claims={decl.cls: decl.claim}))
            assert v.as_dict()["S1"] != "FAIL", {"S1": v.findings["S1"].detail, "tool": decl}
        # S4/S10 and S6, sharp: every landing belongs to an attempt the journal STARTED, before any
        # cancel acknowledgement of its run.
        for landing in self.landings:
            start = started.get((landing.run_id, landing.step, landing.attempt))
            assert start is not None, {"S4": f"{landing} has no STEP_ATTEMPT_STARTED"}
            assert start.ts.timestamp() <= landing.ts, {"S4": f"{landing} precedes its STARTED"}
            acks = [e.seq for e in runs[landing.run_id] if e.type == "CANCEL_ACKNOWLEDGED"]
            assert not acks or start.seq < min(acks), {"S6": f"{landing} started after the cancel"}
        # The World only grows.
        for label, n in self.world.applied_counts().items():
            assert n >= self._applied_high.get(label, 0), {"world": label}
            self._applied_high[label] = n
        self._checked = self.fingerprint()

    def _c1(self, run_id: Any, st: Any) -> None:
        # The Program, not its function: VERIFY restores a boundary's state through its model.
        replay = self.run(run_verify(self.journal, run_id, self.keel.resolve(st.program), tools=self.keel.tools))
        v = invariants.verify(invariants.TrialFacts(replay=replay.as_dict()))
        assert v.as_dict()["C1"] != "FAIL", {"C1": v.findings["C1"].detail, "run": str(run_id)}

    def facts(self, run_id: Any, evs: list[Any], st: Any) -> invariants.TrialFacts:
        effects = self.run(self.journal.effects(run_id))
        mine = [l for l in self.landings if l.run_id == run_id]
        labels = {l.label for l in mine}
        required = []
        if st.phase == "COMPLETED":
            for e in evs:
                decl = self.decls.get(e.body.name) if e.type == "STEP_INTENDED" and e.body.kind == "TOOL" else None
                if decl is not None and decl.cls != "PURE":
                    required.append(self.world.label_for(decl.endpoint, e.body.args) or f"{decl.endpoint}#never")
        applied = {k: n for k, n in self.world.applied_counts().items() if k in labels}
        by_endpoint = {d.endpoint: d for d in self.decls.values()}
        for label, n in applied.items():
            # S7's count, in its sim form: what Keel is answerable for under one approval. A second
            # application by a request no current holder was awaiting is §8.7's named residual for an
            # EXTERNAL bound effect ("can apply twice per approval … S7 reports it"); a receiver that
            # ignores an IDEMPOTENT key breaks the tool's stated assumption, and S1 already reports
            # that raw. Both stay in the World's own count, which S1 and C3 read.
            decl = by_endpoint.get(label.rpartition("#")[0])
            if decl is None or not decl.gated:
                continue
            if decl.cls == "IDEMPOTENT" and not decl.dedup:
                applied[label] = min(n, 1)
            elif decl.cls == "EXTERNAL":
                applied[label] = min(n, max(1, sum(1 for l in mine if l.label == label and l.current)))
        return invariants.TrialFacts(
            world_receipts=[{"endpoint": l.endpoint, "effect_key": l.effect_key, "logical_identity": l.label,
                             "ts": l.ts} for l in mine],
            world_applied=applied,
            sut_committed={e.external_ref for e in effects
                           if e.status in ("COMMITTED", "RESOLVED_COMMITTED") and e.external_ref},
            journal=[{"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(), "step_index": e.step_index,
                      "attempt_no": e.attempt_no, "body": e.body.model_dump(mode="json")} for e in evs],
            status=st.phase,
            required_effects=tuple(required),
            sut_effects=[{"effect_key": e.effect_key, "step_index": e.step_index, "status": e.status,
                          "external_ref": e.external_ref} for e in effects],
            gated_tools={d.name: d.endpoint for d in self.decls.values() if d.gated},
        )

    # --- teardown (§12.4: L1, L2, L3, C1, C3) -----------------------------------------------
    def quiesce(self, budget: int = 60) -> None:
        """No further faults: land what live workers are waiting on, wake the paused, restart into
        free slots, and let time pass, until nothing moves (L1 is "bounded by a step budget")."""
        self.journal_faults.clear()
        logged = len(self.log)
        try:
            self._quiesce(budget)
        finally:
            del self.log[logged:]  # teardown's own moves are not part of the counterexample

    def _quiesce(self, budget: int) -> None:
        idle = 0
        for _ in range(budget):
            moved = False
            for w in list(self.workers.values()):
                w.crash_at = None
                if w.state == "paused":
                    self.zombie_resume(w.slot)
                    moved = True
            ready = [h for h in self.completable() if h.worker.state == "live"]
            if ready:
                self.advance(len(ready))
                moved = True
            for slot in SLOTS:
                moved = self.restart_worker(slot) or moved
            if moved:
                idle = 0
                continue
            idle += 1
            if idle > 2:
                return
            self.tick(TTL + GRACE + 1)
        self.errors.append(f"not quiescent after {budget} rounds")

    def check_teardown(self) -> None:
        self.check()
        l_facts = []
        for r in self.run_ids():
            evs = self.events(r)
            st = fold(evs)
            self._c1(r, st) if not st.terminal else None
            pending = {s.type for s in self.journal._pending(r)}
            legitimate = (
                st.terminal
                or st.phase == "SUSPENDED"
                or (st.phase == "PAUSED" and not pending & {"resume", "cancel"})
                or (st.phase == "WAITING_APPROVAL" and not pending & {"approve", "reject", "cancel", "timer"})
                or (st.phase == "WAITING_CHILDREN" and self._children_waiting(r))
            )
            l_facts.append((r, st.phase, legitimate))
            # L3: no silent ambiguity.
            ambiguous = [s.step_index for s in st.steps.values() if s.state == "AMBIGUOUS"]
            assert not ambiguous or st.phase in ("SUSPENDED", "WAITING_RESOLUTION"), {"L3": f"{r}: {ambiguous}"}
        stuck = [(str(r), phase) for r, phase, ok in l_facts if not ok]
        v = invariants.verify(invariants.TrialFacts(
            status="COMPLETED" if not stuck else stuck[0][1],
            restarts=self.acquisitions, max_recoveries=self.acquisitions,
        ))
        assert v.as_dict()["L1"] != "FAIL", {"L1": stuck}
        assert v.as_dict()["L2"] != "FAIL", {"L2": v.findings["L2"].detail}
        self._c3()

    def _children_waiting(self, run_id: Any) -> bool:
        kids = [c for c, row in self.journal._runs.items() if row.parent_run_id == run_id and row.terminal_at is None]
        if not kids:
            return False
        for c in kids:
            st = fold(self.events(c))
            if st.phase not in ("SUSPENDED", "PAUSED", "WAITING_APPROVAL") and not (
                st.phase == "WAITING_CHILDREN" and self._children_waiting(c)
            ):
                return False
        return True

    def _c3(self) -> None:
        """C3: the journal's committed set == the World's applied set, modulo RESOLVED_UNKNOWN.

        Two more exemptions, both named by the document rather than chosen here: a landing no
        current lease holder was awaiting (§8.4, "S6/C3 may be violated … the verifier reports it"),
        and one whose step a takeover closed with STEP_CANCELLED ("effect may still fire", §7.4).

        An IDEMPOTENT attempt that landed and answered 5xx or nothing is no exemption: its row is
        AMBIGUOUS while a retry is pending and RESOLVED_UNKNOWN when none is left (§7.4 and §9.1 as
        amended after the property suite found it — `tests/property/regressions/test_k6_*`).
        """
        committed, rows, steps = set(), {}, {}
        for r in self.run_ids():
            for e in self.run(self.journal.effects(r)):
                rows[(r, e.step_index)] = e
                if e.status in ("COMMITTED", "RESOLVED_COMMITTED") and e.external_ref:
                    committed.add(e.external_ref)
            steps.update({(r, i): s for i, s in fold(self.events(r)).steps.items()})
        applied = {k for k, n in self.world.applied_counts().items() if n > 0}
        missing = sorted(committed - applied)
        unaccounted = sorted({
            l.label for l in self.landings
            if l.current and l.label in applied and l.label not in committed
            and getattr(rows.get((l.run_id, l.step)), "status", None) not in ("RESOLVED_UNKNOWN", "AMBIGUOUS")
            and getattr(steps.get((l.run_id, l.step)), "state", None) != "CANCELLED"
        })
        assert not missing and not unaccounted, {
            "C3": {"committed_not_applied": missing, "applied_not_committed": unaccounted,
                   "effects": {f"{k[1]}": (v.tool, v.effect_class, v.status) for k, v in rows.items()}},
        }

    def close(self) -> None:
        hooks.reset()
        for w in self.workers.values():
            if w.task is not None and not w.task.done():
                w.state = "dead"
                w.task.cancel()
        with contextlib.suppress(Exception):
            self.settle()
        with contextlib.suppress(Exception):
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        self.loop.close()


# --- §12.8: a counterexample becomes a fault spec ----------------------------------------------
class Inexpressible(fault_spec.CrashproofSpecError):
    """A rule sequence no single Crashproof mode can express. Said, not approximated."""


#: The fault-spec types whose firing needs the supervisor to restart the SUT.
def _entry(rule: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]] | None:
    """One rule's expression in each mode that has one: `{mode: (type, boundary, params)}`.
    `None` for a rule that is not a fault (the workload progressing, time, a restart)."""
    r = rule["rule"]
    tool_call = rule.get("tool", True)
    if r == "crash_at_boundary":
        b = rule["boundary"]
        if b == "during:effect_exec":
            return {m: ("kill", "after:tool_effect", {}) for m in ("shim", "proxy")}
        edge = {"before:effect_exec": "before:tool_call", "after:effect_exec": "after:tool_return"}.get(b)
        out = {"hook": ("kill", b, {})}
        if edge is not None:
            out.update({m: ("kill", edge, {}) for m in ("shim", "proxy")})
        return out
    if r == "timeout":
        if tool_call:
            return {m: ("tool_timeout", "before:tool_call", {}) for m in ("shim", "proxy")}
        return {"shim": ("model_timeout", "before:model_call", {})}
    if r == "lease_expiry":
        edge = "before:tool_call" if tool_call else "before:model_call"
        out = {"hook": ("pause_past_ttl", "before:effect_exec", {}), "shim": ("pause_past_ttl", edge, {})}
        if tool_call:
            out["proxy"] = ("pause_past_ttl", edge, {})
        return out
    if r == "duplicate_response":
        return {"proxy": ("tool_duplicate_response", "after:tool_effect", {})}
    if r == "truncate_stream":
        # The sim's k chunks are the provider's, which is what the shim counts (§11.2); model traffic
        # never crosses the proxy, and no hook fault cuts a stream.
        return {"shim": ("model_stream_truncate", f"during:model_stream(chunk={rule['k']})", {})}
    if r == "duplicate_signal":
        return {m: ("approval_delay", "supervisor", {"duplicate": True}) for m in ("hook", "shim", "proxy")}
    if r == "deliver_signal":
        if rule["kind"] in ("approve", "reject"):
            return {m: ("approval_delay", "supervisor", {"decision": rule["kind"]}) for m in ("hook", "shim", "proxy")}
        return {}  # cancel, pause, resume, custom: no fault type sends them (§14.3: no tier-1 cell issues a cancel)
    if r == "expire_approval":
        return {m: ("approval_expiry", "supervisor", {}) for m in ("hook", "shim", "proxy")}
    if r == "journal_fault":
        return {"hook": ("journal_unavailable", rule["boundary"], {})}
    if r == "drain":
        kind = "sigterm_grace_ok" if rule["grace"] > 5.0 else "sigterm_grace_too_short"
        return {"hook": (kind, "after:effect_exec", {}), "shim": (kind, "after:tool_effect", {})}
    if r == "complete_effect":
        outcome = rule["outcome"]
        if outcome == "error":
            return ({m: ("tool_500", "after:tool_effect", {}) for m in ("shim", "proxy")} if tool_call
                    else {"shim": ("model_500", "before:model_call", {})})
        if outcome == "dropped" and tool_call:
            return {"proxy": ("tool_dropped_response", "after:tool_effect", {})}
        return {}  # a refusal at the door is the workload's answer, and no fault type delivers it
    return None


def to_fault_spec(example: dict[str, Any], out_dir: Path | str | None = Path("bench/specs/regressions")) -> Path | dict[str, Any]:
    """§12.8: a shrunk example → `bench/specs/regressions/<id>.yaml`.

    `example` is `{id, tools, script, rules}` — the generated registry and script, and the rules
    that did something, as `Sim.log` records them. The mode is a property of the whole entry set:
    `hook` if any entry is hook-only, else `shim` if every entry has a shim form, else `proxy` — and
    an entry the chosen mode cannot express is an error naming it, never a quiet omission. The
    document is validated by `crashproof/faults/spec.py` before it is written. `out_dir=None`
    returns the document instead of writing it.
    """
    entries = [(rule, forms) for rule in example["rules"] if (forms := _entry(rule)) is not None]
    for rule, forms in entries:
        if not forms:
            raise Inexpressible(f"{rule} has no fault type in any mode")
    if any(set(forms) == {"hook"} for _, forms in entries):
        mode = "hook"
    elif all("shim" in forms for _, forms in entries):
        mode = "shim"
    else:
        mode = "proxy"
    faults = []
    for i, (rule, forms) in enumerate(entries):
        if mode not in forms:
            raise Inexpressible(f"{rule} cannot be expressed in {mode!r} mode, which the rest of the sequence needs "
                                f"(its modes: {sorted(forms)})")
        type_, boundary, params = forms[mode]
        landmark = "approval:*" if boundary == "supervisor" else rule.get("landmark", "lease:*")
        faults.append({
            "id": f"f{i}-{rule['rule']}",
            "type": type_,
            "trigger": {"boundary": boundary, "landmark": landmark, "occurrence": max(1, int(rule.get("occurrence", 1)))},
            "params": params,
        })
    variant = hashlib.sha256(json.dumps([example["tools"], example["script"]], sort_keys=True).encode()).hexdigest()[:12]
    restarts = sum(1 for f in faults if f["type"] in fault_spec.RESTART_CAUSING)
    doc = {
        "spec_version": 1,
        "name": f"regression-{example['id']}",
        "workload": "keel_sim",
        "workload_variant": variant,
        "mode": mode,
        "max_recoveries": max(3, restarts),
        "timeout": 120.0,
        "faults": faults,
    }
    fault_spec.from_doc(doc)  # refused here, loudly, or never written
    if out_dir is None:
        return doc
    header = "\n".join(
        [f"# {example['id']}: shrunk KeelMachine counterexample (§12.8), generated by tests/property/sim.py",
         "# The workload variant is the generated registry and script:"]
        + [f"#   tool   {json.dumps(t, sort_keys=True)}" for t in example["tools"]]
        + [f"#   script {json.dumps(example['script'], sort_keys=True)}"]
        + [f"#   rule   {json.dumps(r, sort_keys=True)}" for r in example["rules"]]
    )
    path = Path(out_dir) / f"{example['id']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + yaml.safe_dump(doc, sort_keys=False), encoding="utf8")
    return path
