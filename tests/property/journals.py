"""Valid journals, produced by driving the real runtime (§12.6).

Random event lists would be rejected by the fold and would prove nothing, so the input to every
property here is a journal the runtime actually wrote: `MemoryJournal` + `FakeClock` + the scripted
provider + a real World. The only fake is the receiver, and it is the same World the benchmark uses.

The crash is `asyncio.CancelledError` raised inside the tool after the effect has landed. That is
the shape of the window this project exists for — STARTED committed, effect applied, outcome never
written — and raising it needs no sleeps, no threads and no wall clock, so a property test can
produce it a hundred times a second and shrink it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from hypothesis import strategies as st

from crashproof.world.services import Endpoint, World
from keel.client import Keel, Program, program
from keel.core.clock import FakeClock
from keel.core.protocols import EffectClass, Idempotency, ProbeResult
from keel.effects.registry import ToolCtx, tool
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import Decision, ScriptedProvider

ENDPOINT = "svc.write"

# sampled_from, never st.booleans(): shrink order is part of the meaning. Hypothesis shrinks toward
# PURE, `escalate` and `dedup: true`, so a surviving EXTERNAL / dedup:false example is load-bearing.
CLASSES = st.sampled_from(["PURE", "IDEMPOTENT", "EXTERNAL"])
DEDUP = st.sampled_from([True, False])
RESOLUTIONS = st.sampled_from(["escalate", "probe"])
CALLS = st.integers(min_value=1, max_value=3)
PAYLOADS = st.sampled_from([0, 64, 40 * 1024])  # the last crosses the 32 KiB blob threshold


@dataclass(slots=True)
class Rig:
    keel: Keel
    world: World
    clock: FakeClock
    program: Program
    tool_calls: int
    crash_pending: list[bool] = field(default_factory=list)


def build(
    *,
    effect_class: str = "EXTERNAL",
    dedup: bool = False,
    natural: bool = True,
    resolution: str = "probe",
    tool_calls: int = 1,
    payload_bytes: int = 0,
    crash_after_effect: bool = False,
    crash_before_effect: bool = False,
) -> Rig:
    """One rig: a World with one write endpoint, one tool of the given class, and a program that
    calls it `tool_calls` times with a model turn between each."""
    world = World([Endpoint(id=ENDPOINT, service="svc", kind="write", dedup=dedup, natural=natural,
                            logical_identity=("title",))])
    crash = [crash_after_effect]
    crash_first = [crash_before_effect]
    cls = EffectClass[effect_class]
    sends_key = cls is EffectClass.IDEMPOTENT  # F1 for the band that claims a key; F0 otherwise

    @tool(
        effect=cls,
        resolution=resolution,  # type: ignore[arg-type]
        timeout=1.0,
        idempotency=Idempotency.KEY if sends_key else Idempotency.NONE,
        name="write",
    )
    async def write(args: dict[str, Any], tctx: ToolCtx) -> dict[str, Any]:
        if crash_first[0]:
            # The other side of the same window: STARTED is committed, the request never left.
            crash_first[0] = False
            raise asyncio.CancelledError
        result = world.receive(ENDPOINT, args, effect_key=tctx.effect_key if sends_key else None)
        if crash[0]:
            crash[0] = False  # only the first attempt dies; the successor must be able to finish
            raise asyncio.CancelledError
        return result

    @write.probe_hook
    async def _probe(effect_key: str, args: dict[str, Any], tctx: Any) -> ProbeResult:
        label = world.label_for(ENDPOINT, args)
        found = world.lookup(label) if label else None
        if found is None:
            return ProbeResult("ABSENT", evidence=f"nothing applied at {ENDPOINT}")
        return ProbeResult("COMMITTED", evidence=label, result=found, external_ref=label)

    @program(name=f"prop_{effect_class}_{tool_calls}", version="1.0")
    async def agent(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": args.get("task", "go")}]
        for _ in range(tool_calls + 2):
            resp = await ctx.model(messages, name="decide")
            if not resp.tool_calls:
                return {"answer": resp.text}
            call = resp.tool_calls[0]
            result = await ctx.tool(call.name, **call.args)
            messages = [*messages, {"role": "tool_result", "content": result}]
        return {"answer": "step limit"}

    body = "x" * payload_bytes
    script = [
        Decision(text=f"call {i}", tool="write", args={"title": f"issue-{i}", "body": body})
        for i in range(tool_calls)
    ] + [Decision(text="done")]

    clock = FakeClock()
    keel = Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(script),
        tools=[write],
        programs=[agent],
        clock=clock,
    )
    return Rig(keel=keel, world=world, clock=clock, program=agent, tool_calls=tool_calls,
               crash_pending=crash)


async def run_to_completion(rig: Rig) -> Any:
    """Start, crash if the rig is armed, let the lease lapse, and let a successor finish."""
    from datetime import timedelta

    handle = await rig.keel.start(rig.program, {"task": "go"})
    ttl = timedelta(seconds=2)
    while True:
        lease = await rig.keel.journal.claim("w", ttl)
        if lease is None:
            break
        try:
            await rig.keel.worker(worker_id="w", lease_ttl=2.0).execute(lease)
        except asyncio.CancelledError:
            pass  # the process died here; nothing was released and nothing was appended
        rig.clock.advance(4.0)  # past max(lease_expires_at, attempt_deadline)
        await rig.keel.journal.reap()
    return handle.run_id
