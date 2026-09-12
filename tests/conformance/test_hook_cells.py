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
}

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
}

#: Invariants every cell is judged on, whatever its boundary. The same functions the benchmark
#: verifier calls — the sim drifting from the runtime is the standing risk here, and sharing the
#: judge is the mitigation (§28.6).
JUDGED = ("S1", "S3", "S4", "S5", "L1", "C1")


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
    for klass in UNDER_TEST
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


def _arm(cell: Cell, step: int, landed: list[str]) -> None:
    """One hook, one firing. A boundary that fires twice would make the window ambiguous, and a
    fault that keeps firing after the crash would be measuring the successor as well."""
    spent: list[bool] = []

    def hook(boundary: str, detail: dict[str, Any]) -> None:
        if spent or boundary != cell.boundary:
            return
        # Lease boundaries carry no step; step boundaries must land on the one under test, because
        # the PURE read fires the same boundary two steps earlier and killing there measures a
        # different window (the trap the day-2 demo already paid for).
        if "step_index" in detail and detail["step_index"] != step:
            return
        spent.append(True)
        landed.append(f"step={detail.get('step_index', '-')} attempt={detail.get('attempt_no', '-')}")
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


def _identity(effect_class: str, variant: str) -> str:
    """The logical identity of the effect this cell aims at. The two bands run against different
    endpoints — `issues.create` honours nothing, `issues.upsert` deduplicates — so the identity is
    the variant's, never a constant."""
    return "kv.search#1" if effect_class == "PURE" else required_effects(variant)[0]


def _status(phase: str) -> str:
    return {"COMPLETED": "COMPLETED", "FAILED": "FAILED", "CANCELLED": "CANCELLED"}.get(phase, phase)


def _window(state: Any, step: int, world: Any, identity: str) -> str:
    """`journal/world` at the instant of the fault, in the vocabulary the recovery table uses.

    `sent` is about the effect *under test*, not about traffic in general. The PURE read two steps
    earlier has already reached the World by the time the write is attempted, and reading any
    receipt as evidence would report every window after step 1 as `sent`.
    """
    row = state.steps.get(step)
    if row is None:
        journal = "no row"
    elif row.state in ("RUNNING", "INTENDED"):
        journal = "running"
    else:
        journal = "settled"
    sent = any(r.logical_identity == identity for r in world.receipts)
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
    result = await run_cell(cell)
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
    from datetime import UTC, datetime

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
        "| boundary | fault | class | window | disposal | applied | receipts | status "
        "| S1 | S3 | S4 | S5 | L1 | C1 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in CELLS:
        r = RESULTS[cell.id]
        if cell.na:
            lines.append(
                f"| `{cell.boundary}` | `{cell.fault}` | {cell.effect_class} | N/A | "
                + " | ".join(["—"] * 4)
                + " | "
                + " | ".join(["N/A"] * 6)
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
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')}. "
        f"{len(ran)} cells run, {len(CELLS) - len(ran)} N/A, {len(failed)} failed.",
        "",
        "The seven remaining boundaries — `before/after:signal_consume`, `during:approval_wait`,",
        "`before:child_spawn`, `during:child_wait`, `before:segment_write` and",
        "`during:stream(chunk=k)` — are absent rather than stubbed, and arrive with the mechanisms",
        "they name (§28.6). §29.2's *all seventeen hook boundaries* is the honest completion date.",
        "",
    ]
    return "\n".join(lines)


def _mark(verdict: str) -> str:
    return {"PASS": "PASS", "FAIL": "**FAIL**"}.get(verdict, "N/A")
