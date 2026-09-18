"""Keel's own crash-window enumeration, run against Keel (§14.5, §28.6).

The benchmark matrix breaks a runtime where it touches the outside world, because that is the same
instant in every runtime and therefore the only fair place to compare them. It cannot reach the
windows that decide whether Keel's journal protocol is correct: those are inside a single
transaction, and nothing outside the process can get between the intent and its commit.

These cells do. Each one names a boundary inside the write path, fires a fault there, and asks two
questions in order:

    the window    at the instant of the fault, does the journal hold what the protocol says?
    the recovery  after a successor takes the run, do the invariants hold?

The first is what makes this a conformance suite rather than a second benchmark. "The run finished
correctly" is a weaker statement than "the journal was in exactly the state the recovery table
enumerates when the power went out", and only the second one tells you the table is right.

**These are Keel conformance cells and never enter a cross-runtime table.** There is no other
runtime to run them against — a boundary only one runtime exposes is not a fair column (§14.5).
They carry no `n`, no confidence interval and no confirmation tier, because with `MemoryJournal`
and a `FakeClock` they are deterministic: a cell passes or it fails, and a flake is a bug.

A boundary whose fault cannot be delivered in this mode is `N/A` with the reason named, never
skipped and never folded into a pass — the same discipline the matrix applies to a runtime that
cannot supply an invariant's inputs. Three of them are, and each says why.

Run: `uv run pytest tests/conformance -q`. The table lands in `bench/keel_conformance/table.md`.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from crashproof.adapters.keel import KeelAdapter
from crashproof.verifier import invariants
from crashproof.workloads.tool_chain_1_effect import build_world, required_effects
from crashproof.world.server import WorldServer
from keel import Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.core.errors import StoreUnavailable
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider
from keel.replay.verify import verify as run_verify
from keel.runtime import hooks
from keel.state.fold import fold

TTL = 2.0
TABLE = Path(__file__).resolve().parents[2] / "bench" / "keel_conformance" / "table.md"

#: The step each class is exercised on, and the registration that puts it there. `tool_chain_1_effect`
#: is model → search → model → create_issue → model, so the PURE read is step 1 and the write under
#: test is step 3 whichever band it is registered as.
UNDER_TEST = {
    "PURE": (1, "EXTERNAL"),
    "IDEMPOTENT": (3, "IDEMPOTENT"),
    "EXTERNAL": (3, "EXTERNAL"),
}

#: What the journal and the World must hold at the instant the fault lands — the recovery table
#: read backwards. `no row` means the step was never journaled, `running` an attempt with no
#: outcome, `settled` an outcome that is durable. `sent` means the request reached the World.
WINDOW: dict[str, tuple[str, str]] = {
    # Nothing is issued until the intent commits, so a crash before it costs exactly nothing.
    "before:intent_commit": ("no row", "untouched"),
    # Attempt 1's STARTED shares the intent's transaction — the write-ahead barrier — so this
    # boundary is INTENT+STARTED committed together with no outcome, and no crash can land between
    # them. That is the property the INTENDED/RUNNING split in §8.3 rests on.
    "after:intent_commit": ("running", "untouched"),
    "after:attempt_commit": ("running", "untouched"),
    "before:effect_exec": ("running", "untouched"),
    # The window the whole design exists for: the World has the effect and the journal does not.
    "after:effect_exec": ("running", "sent"),
    "before:outcome_commit": ("running", "sent"),
    "after:outcome_commit": ("settled", "sent"),
    "before:lease_release": ("settled", "sent"),
    # Timer-driven rather than boundary-pinned: it fires wherever the heartbeat period lands, so
    # the cell asserts the recovery and prints the placement rather than pinning a window. Reaching
    # it at all needs the run to outlive one heartbeat period, which is what the hold below buys.
    "before:lease_heartbeat": ("any", "any"),
    # Week 2 (§4.10). These three are reached by a *gated* run and judged on its APPROVAL step
    # rather than on a tool step: the park is durable and the lease not yet released; the drain's
    # one transaction, before and after. `settled` at `after:signal_consume` is the decision —
    # consumed and journaled — with the gated effect not yet started.
    "during:approval_wait": ("running", "untouched"),
    "before:signal_consume": ("running", "untouched"),
    "after:signal_consume": ("settled", "untouched"),
    # Delegation (§7.6.1). Before the spawn transaction nothing exists — no step, no child, no
    # row; a crash there costs exactly nothing and the successor spawns once. After it the parent
    # is parked with N children that all exist and none of which has run: the lease is still held,
    # so the reaper reclaims the park as a wait, never as an abandoned attempt.
    "before:child_spawn": ("no row", "untouched"),
    "during:child_wait": ("running", "untouched"),
    # Continuation segments (§4.9). Before the boundary's one transaction nothing of it exists — no
    # SEGMENT_STARTED, no plan snapshot — while the segment it closes has already put to the World.
    "before:segment_write": ("no segment", "sent"),
    # STREAMS (§10.7): STARTED(n) + STEP_CHUNK(n, 1), no outcome — the recovery table's streamed
    # row. A model step has sent nothing to the World; a streaming *tool* emits its answer after the
    # call, so for the three tool classes the request has landed (`sent`, set in the runner).
    "during:stream(chunk=1)": ("running", "untouched"),
}

#: The boundaries only a gated run reaches. Their cells run `gated_tool_chain`, park, are granted
#: through the inbox, and arm the fault on the *successor's* drain — so the class under test is the
#: gated EXTERNAL effect and the window is read on the APPROVAL step (index 0).
GATED_BOUNDARIES = ("during:approval_wait", "before:signal_consume", "after:signal_consume")
APPROVAL_STEP = 0
#: The boundaries only a delegating run reaches. Their cells run `orchestrator`, whose one step
#: is a DELEGATE (index 0) fanning out two `research_child` runs. The window is read on that step;
#: S8 is judged from the whole tree of journals, which only these cells hold.
DELEGATION_BOUNDARIES = ("before:child_spawn", "during:child_wait")
DELEGATE_STEP = 0
#: The boundary only a continuing run reaches. Its cells run `long_horizon` (W3's Keel form) at four
#: rounds with a `Continue(state)` after two, a compaction and a plan item per two — so the boundary
#: under test carries a plan snapshot and a `compact_seq`, and C2 has something to rebuild.
SEGMENT_BOUNDARIES = ("before:segment_write",)
SEGMENT_ARGS = {"iterations": 4, "continue_every": 2, "compact_every": 2, "plan_every": 2, "sleep_at": None}
#: The stream boundary (§10.7, §14.5), per class: a streamed MODEL step (`tool_chain` with the input's
#: `stream`, W7's form) and a STREAMS tool of each class — `search` PURE with `partial_ok` (W7's
#: `fetch_log` shape), `create_issue` IDEMPOTENT and EXTERNAL — each emitting its answer after the
#: call. The fault lands once the first STEP_CHUNK batch is durable. S9 is judged here: chunks are
#: the one thing that can raise a charge above its reservation.
STREAM_BOUNDARIES = ("during:stream(chunk=1)",)
STREAM_STEP = {"MODEL": 0, "PURE": 1, "IDEMPOTENT": 3, "EXTERNAL": 3}

#: A fault that is not a crash leaves a different window, and the difference is the point rather
#: than an exception to the rule. An ordinary `raise` before the effect runs is a tool failure: the
#: engine catches it, records STEP_FAILED, and there is no ambiguity to dispose of — which is
#: exactly why the same `raise` one boundary later is N/A rather than a cell.
WINDOW_OVERRIDE: dict[tuple[str, str], tuple[str, str]] = {
    ("before:effect_exec", "raise"): ("settled", "untouched"),
}

#: The one boundary reached by a timer rather than by the write path, and the two numbers that
#: make it reachable at all. A lease may not be shorter than the longest tool timeout it has to
#: cover (`LeaseTooShort`), so the period cannot be driven below a third of a second by shortening
#: the TTL — and the run is milliseconds long, so without a hold the boundary never fires and the
#: cell is void rather than passing. The hold is spent once: an unbounded one would hold the
#: successor's re-attempt too, which is a different fault.
HEARTBEAT_TTL = 1.2
HEARTBEAT_HOLD_MS = 600.0

#: `(boundary, fault)` and why a pair is not run. Absent means it runs.
NOT_APPLICABLE: dict[tuple[str, str], str] = {
    ("before:attempt_commit", "crash"):
        "fires only for attempt >= 2; `tool_chain_1_effect` has no retryable first attempt and "
        "`NO_RETRY` is the default policy, so the boundary is unreachable in this workload",
    ("before:attempt_commit", "journal_error"):
        "same: the boundary is unreachable in this workload",
    ("after:effect_exec", "raise"):
        "an ordinary exception here is indistinguishable from the tool's own, so the engine "
        "records STEP_FAILED and closes the very window the boundary exists to open. A fault that "
        "produces an outcome is not a crash; `hooks.Crash` is what this boundary takes",
    ("before:lease_heartbeat", "sleep"):
        "a pause the event loop can serve is not a pause. In one process the zombie and its "
        "successor share a loop, so the fence is proven directly in tests/unit/test_fence.py "
        "rather than through a sleep no scheduler will honour",
}

#: Which faults each boundary admits (§14.5), before the N/A table is applied.
FAULTS: dict[str, tuple[str, ...]] = {
    "before:intent_commit": ("crash", "journal_error"),
    "after:intent_commit": ("crash",),
    "before:attempt_commit": ("crash", "journal_error"),
    "after:attempt_commit": ("crash",),
    "before:effect_exec": ("crash", "raise"),
    "after:effect_exec": ("crash", "raise"),
    "before:outcome_commit": ("crash", "journal_error"),
    "after:outcome_commit": ("crash",),
    "before:lease_heartbeat": ("crash", "sleep"),
    "before:lease_release": ("crash",),
    # A journal error *after* the park has committed is a no-op nobody would see, so the wait
    # boundary takes a crash only; the drain takes both, because a store that blinks mid-drain is
    # exactly the outage the `Abandon` path exists for.
    "during:approval_wait": ("crash",),
    "before:signal_consume": ("crash", "journal_error"),
    "after:signal_consume": ("crash", "journal_error"),
    # The spawn transaction takes both — a store that blinks at the instant the parent commits N
    # children is the outage the `Abandon` path exists for; the park after it takes a crash only,
    # for the same reason the approval wait does.
    "before:child_spawn": ("crash", "journal_error"),
    "during:child_wait": ("crash",),
    # §14.5 names `os._exit(137)` and `blob_write_fail`; in-process both are a `StoreUnavailable`
    # raised before the boundary's transaction, which is exactly where a failed blob write lands.
    "before:segment_write": ("crash", "journal_error"),
    # §14.5: `os._exit(137)` and `raise`. A raise mid-stream is the live break — the stream stopped
    # and the worker did not — so it is disposed as an unknown outcome, never as the tool's error.
    "during:stream(chunk=1)": ("crash", "raise"),
}

#: Invariants every cell is judged on, whatever its boundary. The same functions the benchmark
#: verifier calls — the sim drifting from the runtime is the standing risk here, and sharing the
#: judge is the mitigation (§28.6).
#: S7 and S8 are in the grid for every cell and N/A wherever the workload gates or delegates
#: nothing — the same "never omitted from the grid" rule the matrix follows (§15.11 rule 3).
#: S9 is N/A outside the stream cells: the verifier has no budget form yet, so it is judged in its
#: sim form (§12.4) where a chunk can move a charge, and nowhere it would be a free pass.
JUDGED = ("S1", "S3", "S4", "S5", "S7", "S8", "S9", "L1", "C1", "C2")


@dataclass(frozen=True, slots=True)
class Cell:
    boundary: str
    fault: str
    effect_class: str

    @property
    def id(self) -> str:
        return f"{self.boundary}|{self.fault}|{self.effect_class}"

    @property
    def na(self) -> str:
        return NOT_APPLICABLE.get((self.boundary, self.fault), "")


CELLS = [
    Cell(boundary, fault, klass)
    for boundary in FAULTS
    for fault in FAULTS[boundary]
    # The write-path boundaries are exercised per effect class; the gated and delegating ones
    # have one shape each — a gated EXTERNAL effect, a fan-out of PURE children — and would say
    # nothing more three times over.
    for klass in (
        ("GATED",) if boundary in GATED_BOUNDARIES
        else ("DELEGATED",) if boundary in DELEGATION_BOUNDARIES
        else ("SEGMENTED",) if boundary in SEGMENT_BOUNDARIES
        else tuple(STREAM_STEP) if boundary in STREAM_BOUNDARIES
        else tuple(UNDER_TEST)
    )
]


@dataclass(slots=True)
class Result:
    cell: Cell
    fired: bool = False
    window: str = ""
    window_ok: bool = True
    verdicts: dict[str, str] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)
    applied: int = 0
    receipts: int = 0
    status: str = ""
    disposal: str = ""
    recovered: bool = False
    landed_at: str = ""

    @property
    def failed(self) -> list[str]:
        bad = [n for n, v in self.verdicts.items() if v == "FAIL"]
        return bad + ([] if self.window_ok else ["window"])


RESULTS: dict[str, Result] = {}


# --- the runner ---------------------------------------------------------------
def _keel(clock: FakeClock, variant: str) -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue_tool(variant)],
        programs=[demo.tool_chain],
        clock=clock,
    )


def _arm(cell: Cell, step: int, landed: list[str], snap: Any = None) -> None:
    """One hook, one firing. A boundary that fires twice would make the window ambiguous, and a
    fault that keeps firing after the crash would be measuring the successor as well. `snap` reads
    the window at the instant of the fault, for a fault the worker survives and goes on from."""
    spent: list[bool] = []
    # `during:stream(chunk=1)` is the hook `during:stream` with `chunk=1` in its detail (§24.5).
    name, _, chunk = cell.boundary.partition("(chunk=")

    def hook(boundary: str, detail: dict[str, Any]) -> None:
        if spent or boundary != name:
            return
        # Lease boundaries carry no step; step boundaries must land on the one under test, because
        # the PURE read fires the same boundary two steps earlier and killing there measures a
        # different window (the trap the day-2 demo already paid for).
        if "step_index" in detail and detail["step_index"] != step:
            return
        if chunk and detail.get("chunk") != int(chunk.rstrip(")")):
            return
        spent.append(True)
        landed.append(f"step={detail.get('step_index', '-')} attempt={detail.get('attempt_no', '-')}")
        if snap is not None:
            snap()
        if cell.fault == "crash":
            raise hooks.Crash(f"power cut at {boundary}")
        if cell.fault == "journal_error":
            raise StoreUnavailable(f"store unavailable at {boundary}")
        raise RuntimeError(f"hook raised at {boundary}")

    hooks.install(hook)


async def _work(k: Keel, worker_id: str, lease: Any, ttl: float = TTL) -> None:
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=ttl).execute(lease)


async def run_cell(cell: Cell) -> Result:
    step, variant = UNDER_TEST[cell.effect_class]
    result = Result(cell=cell)
    identity = _identity(cell.effect_class, variant)
    world = build_world()
    if cell.boundary == "before:lease_heartbeat":
        world.hold(identity.split("#")[0], HEARTBEAT_HOLD_MS, times=1)
    server = WorldServer(world, port=0)
    await server.start()
    previous_url = demo.WORLD_URL
    demo.WORLD_URL = server.base_url
    try:
        clock = FakeClock()
        # The heartbeat runs on the real clock, so the one timer-driven cell needs the run to
        # outlive one heartbeat period — a short TTL and a held response, together.
        ttl = HEARTBEAT_TTL if cell.boundary == "before:lease_heartbeat" else TTL
        k = _keel(clock, variant)
        handle = await k.start(demo.tool_chain, {"task": "file an issue"})

        landed: list[str] = []
        _arm(cell, step, landed)
        lease = await k.journal.claim("w1", timedelta(seconds=ttl))
        assert lease is not None
        await _work(k, "w1", lease, ttl)
        hooks.reset()
        result.fired = bool(landed)
        result.landed_at = landed[0] if landed else ""

        # The window, read before anyone recovers: this is the whole point of the cell.
        state = fold(await k.events(handle.run_id))
        result.window = _window(state, step, world, identity)
        expected_journal, expected_world = WINDOW_OVERRIDE.get(
            (cell.boundary, cell.fault), WINDOW[cell.boundary]
        )
        result.window_ok = (
            not result.fired
            or expected_journal == "any"
            or result.window == f"{expected_journal}/{expected_world}"
        )

        # The successor. Time passes, the lease lapses, the reaper says so, and someone else picks
        # the run up from the journal alone — no handoff, no supervisor telling it where to resume.
        clock.advance(ttl + 2)
        await k.journal.reap()
        successor = await k.journal.acquire(handle.run_id, "w2", timedelta(seconds=TTL))
        if successor is not None:
            result.recovered = True
            await _work(k, "w2", successor)

        events = await k.events(handle.run_id)
        final = fold(events)
        result.status = final.phase
        # How the successor disposed of the step the fault interrupted. This is §8.3's per-class
        # table demonstrated rather than asserted: the same window resolved by probe for EXTERNAL,
        # re-fired under the same key for IDEMPOTENT, and simply re-run for PURE.
        row = final.steps.get(step)
        result.disposal = row.state if row else "—"
        result.applied = world.applied_counts().get(identity, 0)
        result.receipts = sum(1 for r in world.receipts if r.logical_identity == identity)

        replay = await run_verify(k.journal, handle.run_id, demo.tool_chain.fn, tools=k.tools)
        verdicts = invariants.verify(
            invariants.TrialFacts(
                world_receipts=[
                    {"endpoint": r.endpoint, "effect_key": r.effect_key,
                     "logical_identity": r.logical_identity, "ts": r.ts}
                    for r in world.receipts
                ],
                world_applied=world.applied_counts(),
                sut_committed={
                    e.external_ref
                    for e in (await k.journal.effects(handle.run_id))
                    if e.status in ("COMMITTED", "RESOLVED_COMMITTED") and e.external_ref
                },
                journal=[
                    {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(),
                     "step_index": e.step_index, "attempt_no": e.attempt_no,
                     "body": e.body.model_dump(mode="json")}
                    for e in events
                ],
                status=_status(final.phase),
                required_effects=required_effects(variant),
                claims=KeelAdapter.claims,
                effect_class=cell.effect_class,
                faults=[{"type": cell.fault, "boundary": cell.boundary, "executed": result.fired}],
                restarts=1 if result.recovered else 0,
                replay=replay.as_dict(),
            )
        )
        result.verdicts = {n: v for n, v in verdicts.as_dict().items() if n in JUDGED}
        result.details = {n: f.detail for n, f in verdicts.findings.items() if n in JUDGED}
        return result
    finally:
        demo.WORLD_URL = previous_url
        hooks.reset()
        await server.stop()


async def run_gated_cell(cell: Cell) -> Result:
    """The three week-2 boundaries, reached by a gated run (§4.10, §7.5).

    Shape: w1 parks on `ctx.approve`; the human grants through the inbox; a successor drains the
    grant and the fault lands on *its* boundary. `during:approval_wait` is the exception — it fires
    on w1, at the instant the park is durable and the lease not yet released. Whatever the window,
    the last successor must finish the run with the gated effect applied exactly once and the
    approval requested and decided exactly once each: S7 is the whole subject of these cells.
    """
    result = Result(cell=cell)
    identity = "issues.create#1"
    world = build_world()
    server = WorldServer(world, port=0)
    await server.start()
    previous_url = demo.WORLD_URL
    demo.WORLD_URL = server.base_url
    try:
        clock = FakeClock()
        k = Keel(
            journal=MemoryJournal(clock=clock),
            provider=ScriptedProvider(demo.SCRIPT),
            tools=[demo.search, demo.create_issue_tool("EXTERNAL")],
            programs=[demo.gated_tool_chain],
            clock=clock,
        )
        handle = await k.start(demo.gated_tool_chain, {"title": "conformance"})
        landed: list[str] = []

        # w1: the park. Only the wait boundary is armed here.
        if cell.boundary == "during:approval_wait":
            _arm(cell, APPROVAL_STEP, landed)
        lease = await k.journal.claim("w1", timedelta(seconds=TTL))
        assert lease is not None
        await _work(k, "w1", lease)
        hooks.reset()

        async def snapshot() -> None:
            # The window, on the APPROVAL step, at the instant of the fault — read before anyone
            # is granted anything, or the successor's own work would be mistaken for the window.
            state = fold(await k.events(handle.run_id))
            result.fired = bool(landed)
            result.landed_at = landed[0] if landed else ""
            result.window = _window(state, APPROVAL_STEP, world, identity)
            expected_journal, expected_world = WINDOW[cell.boundary]
            result.window_ok = (
                not result.fired or result.window == f"{expected_journal}/{expected_world}"
            )

        if cell.boundary == "during:approval_wait":
            await snapshot()  # the fault landed on w1, at the park

        # The human grants. One row; whoever comes next drains it.
        from keel.core.ids import uuid7
        from keel.journal.protocol import SignalRow

        assert await k.journal.insert_signal(
            SignalRow(signal_id=uuid7(), run_id=handle.run_id, type="approve", payload={"by": "cell"})
        )

        # w2: the drain. The signal boundaries are armed here and land on this successor.
        if cell.boundary != "during:approval_wait":
            _arm(cell, APPROVAL_STEP, landed)
        clock.advance(TTL + 2)
        await k.journal.reap()
        successor = await k.journal.acquire(handle.run_id, "w2", timedelta(seconds=TTL))
        if successor is not None:
            await _work(k, "w2", successor)
        hooks.reset()
        if cell.boundary != "during:approval_wait":
            await snapshot()  # the fault landed on w2, at the drain

        # w3: whoever comes after the fault. For the wait boundary this is the drain itself.
        clock.advance(TTL + 2)
        await k.journal.reap()
        last = await k.journal.acquire(handle.run_id, "w3", timedelta(seconds=TTL))
        if last is not None:
            result.recovered = True
            await _work(k, "w3", last)

        events = await k.events(handle.run_id)
        final = fold(events)
        result.status = final.phase
        row = final.steps.get(APPROVAL_STEP)
        result.disposal = row.state if row else "—"
        result.applied = world.applied_counts().get(identity, 0)
        result.receipts = sum(1 for r in world.receipts if r.logical_identity == identity)

        replay = await run_verify(k.journal, handle.run_id, demo.gated_tool_chain.fn, tools=k.tools)
        verdicts = invariants.verify(
            invariants.TrialFacts(
                world_receipts=[
                    {"endpoint": r.endpoint, "effect_key": r.effect_key,
                     "logical_identity": r.logical_identity, "ts": r.ts}
                    for r in world.receipts
                ],
                world_applied=world.applied_counts(),
                sut_committed={
                    e.external_ref
                    for e in (await k.journal.effects(handle.run_id))
                    if e.status in ("COMMITTED", "RESOLVED_COMMITTED") and e.external_ref
                },
                journal=[
                    {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(),
                     "step_index": e.step_index, "attempt_no": e.attempt_no,
                     "body": e.body.model_dump(mode="json")}
                    for e in events
                ],
                status=_status(final.phase),
                required_effects=(identity,),
                claims=KeelAdapter.claims,
                effect_class="EXTERNAL",
                faults=[{"type": cell.fault, "boundary": cell.boundary, "executed": result.fired}],
                restarts=2 if result.recovered else 1,
                replay=replay.as_dict(),
                # S7 reads "applied under this approval" through the effect ledger's World label.
                sut_effects=[
                    {"effect_key": e.effect_key, "external_ref": e.external_ref}
                    for e in await k.journal.effects(handle.run_id)
                ],
                gated_tools={"create_issue": identity.rpartition("#")[0]},
            )
        )
        judged = (*JUDGED, "S7")
        result.verdicts = {n: v for n, v in verdicts.as_dict().items() if n in judged}
        result.details = {n: f.detail for n, f in verdicts.findings.items() if n in judged}
        # The cells' own claim, beyond the verifier's: one request, one decision, whatever the
        # crash. A second APPROVAL_REQUESTED would mint a second approval id and make S7 vacuous.
        requested = sum(1 for e in events if e.type == "APPROVAL_REQUESTED")
        decided = sum(1 for e in events if e.type == "APPROVAL_DECIDED")
        if (requested, decided) != (1, 1):
            result.verdicts["S7"] = "FAIL"
            result.details["S7"] = f"APPROVAL_REQUESTED x{requested}, APPROVAL_DECIDED x{decided}"
        return result
    finally:
        demo.WORLD_URL = previous_url
        hooks.reset()
        await server.stop()


async def run_delegation_cell(cell: Cell) -> Result:
    """The two delegation boundaries, reached by a fanning-out run (§7.6.1, §17).

    Shape: w1 runs `orchestrator`, whose only step delegates two `research_child` runs, and the
    fault lands on w1 — before the spawn transaction, or at the park after it. A successor takes
    the parent from the journal alone; the children run; the parent wakes on their results and
    finishes. Two claims, judged from every journal in the tree: the spawn happened exactly once
    per ordinal whatever the crash, and S8 — every child terminal before the parent, no child
    receipt after the parent's terminal event.
    """
    result = Result(cell=cell)
    world = build_world()
    server = WorldServer(world, port=0)
    await server.start()
    previous_url = demo.WORLD_URL
    demo.WORLD_URL = server.base_url
    try:
        clock = FakeClock()
        k = Keel(
            journal=MemoryJournal(clock=clock),
            provider=ScriptedProvider(demo.SCRIPT),
            tools=[demo.search, demo.create_issue_tool("EXTERNAL")],
            programs=[demo.orchestrator, demo.research_child],
            clock=clock,
        )
        handle = await k.start(demo.orchestrator, {"tasks": ["a", "b"]})
        landed: list[str] = []

        _arm(cell, DELEGATE_STEP, landed)
        lease = await k.journal.claim("w1", timedelta(seconds=TTL))
        assert lease is not None
        await _work(k, "w1", lease)
        hooks.reset()
        result.fired = bool(landed)
        result.landed_at = landed[0] if landed else ""

        # The window, on the DELEGATE step, before anyone recovers. `sent` is any World traffic at
        # all: the children have not run, so there must be none.
        state = fold(await k.events(handle.run_id))
        result.window = _window(state, DELEGATE_STEP, world, None)
        expected_journal, expected_world = WINDOW[cell.boundary]
        result.window_ok = not result.fired or result.window == f"{expected_journal}/{expected_world}"

        # The successor: the lease lapses, the reaper says so, w2 takes the parent from the journal.
        clock.advance(TTL + 2)
        await k.journal.reap()
        successor = await k.journal.acquire(handle.run_id, "w2", timedelta(seconds=TTL))
        if successor is not None:
            result.recovered = True
            await _work(k, "w2", successor)

        # The children, then the parent on their results.
        for i, child in enumerate(await k.journal.children(handle.run_id)):
            child_lease = await k.journal.acquire(child.run_id, f"c{i}", timedelta(seconds=TTL))
            if child_lease is not None:
                await _work(k, f"c{i}", child_lease)
        receipts_before_parent_finished = len(world.receipts)
        last = await k.journal.acquire(handle.run_id, "w3", timedelta(seconds=TTL))
        if last is not None:
            await _work(k, "w3", last)

        events = await k.events(handle.run_id)
        final = fold(events)
        result.status = final.phase
        row = final.steps.get(DELEGATE_STEP)
        result.disposal = row.state if row else "—"
        result.applied = sum(world.applied_counts().values())
        result.receipts = len(world.receipts)

        replay = await run_verify(k.journal, handle.run_id, demo.orchestrator.fn, tools=k.tools)
        verdicts = invariants.verify(
            invariants.TrialFacts(
                world_receipts=[
                    {"endpoint": r.endpoint, "effect_key": r.effect_key,
                     "logical_identity": r.logical_identity, "ts": r.ts}
                    for r in world.receipts
                ],
                world_applied=world.applied_counts(),
                sut_committed=set(),
                journal=[
                    {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(),
                     "step_index": e.step_index, "attempt_no": e.attempt_no,
                     "body": e.body.model_dump(mode="json")}
                    for e in events
                ],
                status=_status(final.phase),
                required_effects=(),
                claims=KeelAdapter.claims,
                effect_class="PURE",
                faults=[{"type": cell.fault, "boundary": cell.boundary, "executed": result.fired}],
                restarts=1 if result.recovered else 0,
                replay=replay.as_dict(),
            )
        )
        result.verdicts = {n: v for n, v in verdicts.as_dict().items() if n in JUDGED}
        result.details = {n: f.detail for n, f in verdicts.findings.items() if n in JUDGED}

        # The cells' own claims. Spawned once per ordinal, whatever the crash: a second
        # CHILD_SPAWNED for an ordinal would be two children under one contract.
        ordinals = sorted(e.body.child_ordinal for e in events if e.type == "CHILD_SPAWNED")
        children = await k.journal.children(handle.run_id)
        if ordinals != [0, 1] or len(children) != 2:
            result.verdicts["S5"] = "FAIL"
            result.details["S5"] = f"CHILD_SPAWNED ordinals {ordinals}, {len(children)} child rows"
        # S8, from the whole tree (§12.4): each child's journal has one RUN_CREATED at epoch 0,
        # every child is terminal once the parent is, and the World saw nothing after the parent
        # finished. Counted, not timestamped: the journals run on a FakeClock and the World on the
        # wall clock, and an ordering across the two would be an ordering of nothing.
        problems: list[str] = []
        for child in children:
            child_events = await k.events(child.run_id)
            born = [e for e in child_events if e.type == "RUN_CREATED"]
            if len(born) != 1 or born[0].lease_epoch != 0:
                problems.append(f"{child.run_id}: {len(born)} RUN_CREATED")
            child_state = fold(child_events)
            if not child_state.terminal:
                problems.append(f"{child.run_id}: {child_state.phase} after the parent finished")
        if final.terminal and len(world.receipts) != receipts_before_parent_finished:
            problems.append("a child receipt after the parent's terminal event")
        if not final.terminal:
            problems.append(f"the parent ended {final.phase}")
        result.verdicts["S8"] = "FAIL" if problems else "PASS"
        result.details["S8"] = "; ".join(problems) if problems else (
            f"{len(children)} children, each born once at epoch 0 and terminal before the parent"
        )
        return result
    finally:
        demo.WORLD_URL = previous_url
        hooks.reset()
        await server.stop()


async def run_segment_cell(cell: Cell) -> Result:
    """`before:segment_write` (§4.9, §14.5): the instant before SEGMENT_STARTED and its plan snapshot
    commit, on the boundary `long_horizon` asks for with `Continue(state)` after two rounds.

    The claims: nothing of the boundary exists at the fault (a torn boundary is impossible); the
    successor replays the closed segment from memo, the program returns the same `Continue(state)`,
    and the boundary is written once; step indices continue across it; every put applied once; and
    C2 — the plan and the context rebuilt from the boundary alone equal the fold from seq 1.
    """
    from crashproof.world.services import Endpoint, World
    from keel.providers.scripted import Decision

    result = Result(cell=cell)
    rounds = int(SEGMENT_ARGS["iterations"])
    world = World([Endpoint(id="kv.put", service="kv", kind="write", dedup=True, natural=True,
                            logical_identity=("key", "value"))])
    server = WorldServer(world, port=0)
    await server.start()
    previous_url = demo.WORLD_URL
    demo.WORLD_URL = server.base_url
    try:
        clock = FakeClock()
        k = Keel(
            journal=MemoryJournal(clock=clock),
            provider=ScriptedProvider(
                [Decision(tool="kv_put", args={"key": "counter", "value": i}) for i in range(rounds)]
                + [Decision(text="counted")]
            ),
            tools=[demo.kv_put],
            programs=[demo.long_horizon],
            clock=clock,
        )
        handle = await k.start(demo.long_horizon, dict(SEGMENT_ARGS))
        landed: list[str] = []
        _arm(cell, -1, landed)  # the boundary carries no step index: its first write is the one
        lease = await k.journal.claim("w1", timedelta(seconds=TTL))
        assert lease is not None
        await _work(k, "w1", lease)
        hooks.reset()
        result.fired = bool(landed)
        result.landed_at = landed[0] if landed else ""

        state = fold(await k.events(handle.run_id))
        journal = "no segment" if state.segment is None else f"segment {state.segment.segment_no}"
        result.window = f"{journal}/{'sent' if world.receipts else 'untouched'}"
        result.window_ok = not result.fired or result.window == "/".join(WINDOW[cell.boundary])

        clock.advance(TTL + 2)
        await k.journal.reap()
        successor = await k.journal.acquire(handle.run_id, "w2", timedelta(seconds=TTL))
        if successor is not None:
            result.recovered = True
            await _work(k, "w2", successor)

        events = await k.events(handle.run_id)
        final = fold(events)
        result.status = final.phase
        result.disposal = f"segments={sum(1 for e in events if e.type == 'SEGMENT_STARTED')}"
        result.applied = sum(world.applied_counts().values())
        result.receipts = len(world.receipts)
        required = tuple(f"kv.put#{i + 1}" for i in range(rounds))

        replay = await run_verify(k.journal, handle.run_id, demo.long_horizon, tools=k.tools)
        verdicts = invariants.verify(
            invariants.TrialFacts(
                world_receipts=[
                    {"endpoint": r.endpoint, "effect_key": r.effect_key,
                     "logical_identity": r.logical_identity, "ts": r.ts}
                    for r in world.receipts
                ],
                world_applied=world.applied_counts(),
                sut_committed={
                    e.external_ref
                    for e in (await k.journal.effects(handle.run_id))
                    if e.status in ("COMMITTED", "RESOLVED_COMMITTED") and e.external_ref
                },
                journal=[
                    {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(),
                     "step_index": e.step_index, "attempt_no": e.attempt_no,
                     "body": e.body.model_dump(mode="json")}
                    for e in events
                ],
                status=_status(final.phase),
                required_effects=required,
                claims=KeelAdapter.claims,
                effect_class="IDEMPOTENT",
                faults=[{"type": cell.fault, "boundary": cell.boundary, "executed": result.fired}],
                restarts=1 if result.recovered else 0,
                replay=replay.as_dict(),
            )
        )
        result.verdicts = {n: v for n, v in verdicts.as_dict().items() if n in JUDGED}
        result.details = {n: f.detail for n, f in verdicts.findings.items() if n in JUDGED}
        # The cell's own claims beyond the verifier's: one boundary, written once, and every round
        # applied once — a second SEGMENT_STARTED{1} would be refused, a re-put deduplicated.
        segments = [e.body.segment_no for e in events if e.type == "SEGMENT_STARTED"]
        if segments != [1] or world.applied_counts() != dict.fromkeys(required, 1):
            result.verdicts["C2"] = "FAIL"
            result.details["C2"] = f"segments {segments}, applied {world.applied_counts()}"
        return result
    finally:
        demo.WORLD_URL = previous_url
        hooks.reset()
        await server.stop()


class _Billing(ScriptedProvider):
    """The provider's side of S9 (§12.4, sim form): every answer it produced is billed — streamed
    and cut, crashed, or completed — at its full usage, which is what the provider would charge."""

    def __init__(self, script: Any) -> None:
        super().__init__(script)
        self.billed = 0

    async def complete(self, req: Any) -> Any:
        resp = await super().complete(req)
        self.billed += resp.usage.input_tokens + resp.usage.output_tokens
        return resp


def _streamed(spec: Any, **extra: Any) -> Any:
    """The same registration with STREAMS: the call, then its answer emitted a field at a time."""
    import json

    from keel.core.protocols import Modifier
    from keel.effects.registry import tool

    @tool(effect=spec.effect_class, resolution=spec.resolution, timeout=spec.timeout,
          idempotency=spec.idempotency, modifiers=(Modifier.STREAMS,), name=spec.name, **extra)
    async def run(args: Any, tctx: Any) -> Any:
        result = await spec.run(args, tctx)
        for piece in json.dumps(result, sort_keys=True).split(","):
            await tctx.emit(piece)
        return result

    if spec.probe is not None:
        run.probe_hook(spec.probe)
    return run


async def run_stream_cell(cell: Cell) -> Result:
    """`during:stream(chunk=k)` (§10.7, §14.5): the instant a STREAMS attempt's first STEP_CHUNK batch
    is durable and its outcome is not.

    The claims: at the fault the journal holds STARTED + chunks and no outcome; a crash is disposed by
    the class exactly as STARTED alone would be (MODEL and PURE a new attempt, IDEMPOTENT the same key,
    EXTERNAL AMBIGUOUS and its probe); a raise — the stream broken on a live worker — is an unknown
    outcome, retried or resolved, except PURE's `partial_ok`, which completes with what arrived; no
    chunk of an attempt that did not complete is ever the result; and S9, the charge never below
    what the provider billed, abandoned attempts included.
    """
    from keel.runtime.retry import RetryPolicy

    klass = cell.effect_class
    step = STREAM_STEP[klass]
    variant = "EXTERNAL" if klass == "MODEL" else ("IDEMPOTENT" if klass == "IDEMPOTENT" else "EXTERNAL")
    result = Result(cell=cell)
    identity = None if klass == "MODEL" else _identity(klass, variant)
    world = build_world()
    server = WorldServer(world, port=0)
    await server.start()
    previous_url = demo.WORLD_URL
    demo.WORLD_URL = server.base_url
    try:
        clock = FakeClock()
        search, create = demo.search, demo.create_issue_tool(variant)
        if klass == "PURE":
            search = _streamed(search, partial_ok=True)
        elif klass != "MODEL":
            create = _streamed(create)
        provider = _Billing(demo.SCRIPT)
        k = Keel(journal=MemoryJournal(clock=clock), provider=provider, tools=[search, create],
                 programs=[demo.tool_chain], clock=clock)
        # One retry for model and tool alike: a stream broken on a live worker is an unknown outcome,
        # and whether it recovers is what the cell shows — under NO_RETRY it would only fail the run.
        policy = RetryPolicy(max_attempts=2, base_s=0.0)
        handle = await k.start(demo.tool_chain, {"task": "file an issue", "stream": klass == "MODEL"})

        async def work(worker_id: str, lease: Any) -> None:
            with contextlib.suppress(BaseException):
                await k.worker(worker_id=worker_id, lease_ttl=TTL, retry=policy, model_retry=policy).execute(lease)

        landed: list[str] = []
        chunked: list[bool] = []

        def snap() -> None:
            # Read at the instant of the fault, synchronously: a raise leaves the worker alive, and what
            # it does next — the outcome, a retry — is the disposal, not the window.
            log = list(k.journal._events[handle.run_id])
            result.window = _window(fold(log), step, world, identity)
            chunked.append(any(e.type == "STEP_CHUNK" and e.step_index == step for e in log))

        _arm(cell, step, landed, snap)
        lease = await k.journal.claim("w1", timedelta(seconds=TTL))
        assert lease is not None
        await work("w1", lease)
        hooks.reset()
        result.fired = bool(landed)
        result.landed_at = landed[0] if landed else ""
        expected = "running/" + ("untouched" if klass == "MODEL" else "sent")
        result.window_ok = not result.fired or (result.window == expected and chunked == [True])

        clock.advance(TTL + 2)
        await k.journal.reap()
        successor = await k.journal.acquire(handle.run_id, "w2", timedelta(seconds=TTL))
        if successor is not None:
            result.recovered = True
            await work("w2", successor)

        events = await k.events(handle.run_id)
        final = fold(events)
        result.status = final.phase
        row = final.steps.get(step)
        result.disposal = (row.state if row else "—") + (
            " partial" if row is not None and isinstance(row.result, dict) and row.result.get("partial") else ""
        )
        result.applied = world.applied_counts().get(identity, 0) if identity else sum(world.applied_counts().values())
        result.receipts = sum(1 for r in world.receipts if identity is None or r.logical_identity == identity)

        replay = await run_verify(k.journal, handle.run_id, demo.tool_chain.fn, tools=k.tools)
        verdicts = invariants.verify(
            invariants.TrialFacts(
                world_receipts=[
                    {"endpoint": r.endpoint, "effect_key": r.effect_key,
                     "logical_identity": r.logical_identity, "ts": r.ts}
                    for r in world.receipts
                ],
                world_applied=world.applied_counts(),
                sut_committed={
                    e.external_ref
                    for e in (await k.journal.effects(handle.run_id))
                    if e.status in ("COMMITTED", "RESOLVED_COMMITTED") and e.external_ref
                },
                journal=[
                    {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(),
                     "step_index": e.step_index, "attempt_no": e.attempt_no,
                     "body": e.body.model_dump(mode="json")}
                    for e in events
                ],
                status=_status(final.phase),
                required_effects=required_effects(variant),
                claims=KeelAdapter.claims,
                effect_class="EXTERNAL" if klass == "MODEL" else klass,
                faults=[{"type": cell.fault, "boundary": cell.boundary, "executed": result.fired}],
                restarts=1 if result.recovered else 0,
                replay=replay.as_dict(),
            )
        )
        result.verdicts = {n: v for n, v in verdicts.as_dict().items() if n in JUDGED}
        result.details = {n: f.detail for n, f in verdicts.findings.items() if n in JUDGED}
        # S9, sim form (§12.4): Σ charged ≥ Σ provider-billed, every attempt that asked counted.
        charged = final.charged.tokens_charged
        result.verdicts["S9"] = "PASS" if charged >= provider.billed > 0 else "FAIL"
        result.details["S9"] = f"charged {charged} >= billed {provider.billed}"
        # The cell's own claim beyond the verifier's: the answer is never a stream's partial text. A
        # completed streamed step's result is the one outcome; `partial` only where PURE allowed it.
        if row is not None and isinstance(row.result, dict) and row.result.get("partial") and klass != "PURE":
            result.verdicts["S3"] = "FAIL"
            result.details["S3"] = f"a partial result became step {step}'s outcome"
        return result
    finally:
        demo.WORLD_URL = previous_url
        hooks.reset()
        await server.stop()


def _identity(effect_class: str, variant: str) -> str:
    """The logical identity of the effect this cell aims at. The two bands run against different
    endpoints — `issues.create` honours nothing, `issues.upsert` deduplicates — so the identity is
    the variant's, never a constant."""
    return "kv.search#1" if effect_class == "PURE" else required_effects(variant)[0]


def _status(phase: str) -> str:
    return {"COMPLETED": "COMPLETED", "FAILED": "FAILED", "CANCELLED": "CANCELLED"}.get(phase, phase)


def _window(state: Any, step: int, world: Any, identity: str | None) -> str:
    """`journal/world` at the instant of the fault, in the vocabulary the recovery table uses.

    `sent` is about the effect *under test*, not about traffic in general. The PURE read two steps
    earlier has already reached the World by the time the write is attempted, and reading any
    receipt as evidence would report every window after step 1 as `sent`. `identity=None` is the
    delegation cells' case, where the parent itself sends nothing and *any* receipt is a child that
    ran before it should have.
    """
    row = state.steps.get(step)
    if row is None:
        journal = "no row"
    elif row.state in ("RUNNING", "INTENDED"):
        journal = "running"
    else:
        journal = "settled"
    sent = any(identity is None or r.logical_identity == identity for r in world.receipts)
    return f"{journal}/{'sent' if sent else 'untouched'}"


# --- the cells ----------------------------------------------------------------
@pytest.fixture(autouse=True)
def _no_hook_leaks():
    """A hook is process-global. One cell forgetting to remove it would silently arm every cell
    after it, so removal is the fixture's job rather than each cell's."""
    hooks.reset()
    yield
    hooks.reset()


@pytest.mark.parametrize("cell", CELLS, ids=lambda c: c.id)
async def test_cell(cell: Cell) -> None:
    if cell.na:
        RESULTS[cell.id] = Result(cell=cell, verdicts=dict.fromkeys(JUDGED, "N/A"))
        pytest.skip(cell.na)
    runner = (
        run_gated_cell if cell.boundary in GATED_BOUNDARIES
        else run_delegation_cell if cell.boundary in DELEGATION_BOUNDARIES
        else run_segment_cell if cell.boundary in SEGMENT_BOUNDARIES
        else run_stream_cell if cell.boundary in STREAM_BOUNDARIES
        else run_cell
    )
    result = await runner(cell)
    RESULTS[cell.id] = result
    assert result.fired, "the fault never fired; a cell that did not test what it claims is void"
    assert result.window_ok, (
        f"{cell.boundary} left the journal at {result.window}, "
        f"not {'/'.join(WINDOW[cell.boundary])} — the recovery table describes a state the "
        f"runtime does not actually reach"
    )
    assert not result.failed, f"{result.failed}: {result.details}"


def teardown_module(module: Any) -> None:
    """Write the table, but only from a run that produced all of it.

    A partial table is worse than none: it is indistinguishable from a complete one on the page,
    and the cells a `-k` filter left out would read as cells that do not exist.
    """
    if len(RESULTS) != len(CELLS):
        return
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_text(render(), encoding="utf8")


def render() -> str:
    lines = [
        "# Keel conformance (`hook` mode, deterministic, pass/fail)",
        "",
        "Keel's own crash-window enumeration, run against Keel. **Never unioned with the",
        "cross-runtime matrix**: a boundary only one runtime exposes is not a fair column (§14.5).",
        "No `n`, no confidence interval, no confirmation tier — with `MemoryJournal` and a",
        "`FakeClock` these are deterministic, so a cell passes or it fails and a flake is a bug.",
        "",
        "`window` is what the journal and the World held at the instant of the fault, which is the",
        "§8.3 recovery table read backwards, and `disposal` is how the successor closed the step",
        "the fault interrupted — the per-class column of that same table, demonstrated rather than",
        "asserted. `applied` and `receipts` are what the World actually did and what it was asked",
        "to do, printed whatever the verdicts say: the gap between them is what the receiver's",
        "idempotency bought, and the runtime gets no credit for it.",
        "",
        "| boundary | fault | class | window | disposal | applied | receipts | status | "
        + " | ".join(JUDGED) + " |",
        "|" + "---|" * (8 + len(JUDGED)),
    ]
    for cell in CELLS:
        r = RESULTS[cell.id]
        if cell.na:
            lines.append(
                f"| `{cell.boundary}` | `{cell.fault}` | {cell.effect_class} | N/A | "
                + " | ".join(["—"] * 4)
                + " | "
                + " | ".join(["N/A"] * len(JUDGED))
                + " |"
            )
            continue
        verdicts = " | ".join(_mark(r.verdicts.get(n, "N/A")) for n in JUDGED)
        lines.append(
            f"| `{cell.boundary}` | `{cell.fault}` | {cell.effect_class} | {r.window} | "
            f"{r.disposal} | {r.applied} | {r.receipts} | {r.status} | {verdicts} |"
        )

    na = sorted(NOT_APPLICABLE.items())
    lines += ["", "## N/A, with the reason", "",
              "A fault this mode cannot deliver is named, never skipped and never folded into a",
              "pass — the same discipline the matrix applies to a runtime that cannot supply an",
              "invariant's inputs.", "",
              "| boundary | fault | why |", "|---|---|---|"]
    lines += [f"| `{b}` | `{f}` | {why} |" for (b, f), why in na]

    ran = [RESULTS[c.id] for c in CELLS if not c.na]
    failed = [r for r in ran if r.failed]
    lines += [
        "",
        "## Provenance",
        "",
        # No timestamp. These cells are deterministic, so the table is a function of the code
        # that produced it — and a generated file that changes on every test run is a file whose
        # diff nobody reads. The commit that changed it is the date.
        f"{len(ran)} cells run, {len(CELLS) - len(ran)} N/A, {len(failed)} failed. "
        f"Regenerate with `uv run pytest tests/conformance -q`.",
        "",
        "All seventeen boundaries exist: the ten of the write path (§28.6), the three the inbox and",
        "approvals brought with them (§4.10), the two delegation brought (§4.11), the continuation",
        "boundary (§4.9), and `during:stream(chunk=k)` with STREAMS (§10.7) — §29.2's *all seventeen",
        "hook boundaries*.",
        "",
        "S8 is judged here and nowhere else yet: these cells hold every journal in the tree, and the",
        "matrix's collector reads one per trial, so the matrix prints N/A with that reason (§15.11).",
        "C2 is N/A wherever the workload never crosses a continuation boundary. S9 is judged in its",
        "sim form (§12.4: Σ charged ≥ Σ provider-billed, abandoned attempts included) on the stream",
        "cells only — the one boundary where a chunk can move a charge — and is N/A elsewhere.",
        "",
    ]
    return "\n".join(lines)


def _mark(verdict: str) -> str:
    return {"PASS": "PASS", "FAIL": "**FAIL**"}.get(verdict, "N/A")
