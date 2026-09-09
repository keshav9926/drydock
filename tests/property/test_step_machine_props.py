"""The step machine and the per-class recovery table, as properties (§12.4, §8.3).

The single crash window — STARTED committed, effect applied, outcome never written — is opened for
every effect class, against a receiver that either honours idempotency or does not, and the claim
each class makes is checked against what the World actually did rather than against what the
runtime says it did.

    PURE / IDEMPOTENT   re-run under the same effect_key   ⇒ applied once iff the receiver dedups
    EXTERNAL + probe    ambiguity surfaced, then resolved  ⇒ never re-fired
    EXTERNAL + escalate ambiguity surfaced, then SUSPENDED ⇒ never re-fired, never guessed
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from journals import CALLS, CLASSES, DEDUP, RESOLUTIONS, Rig, build, run_to_completion

from keel.core.errors import IllegalTransition
from keel.events import RunCreated, StepAttemptStarted, StepCompleted, StepIntended
from keel.journal.memory import MemoryJournal, memory_run_row
from keel.state.fold import fold

SETTLED_FOREVER = {"COMPLETED", "RESOLVED_COMPLETED", "RESOLVED_FAILED", "CANCELLED"}
CRASH = st.sampled_from([False, True])
PROP = settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@PROP
@given(effect_class=CLASSES, dedup=DEDUP, resolution=RESOLUTIONS)
def test_a_crash_in_the_ambiguity_window_is_disposed_by_class(
    effect_class: str, dedup: bool, resolution: str
) -> None:
    async def check() -> None:
        rig = build(
            effect_class=effect_class, dedup=dedup, resolution=resolution, crash_after_effect=True
        )
        view = await rig.keel.get(await run_to_completion(rig))
        step = view.steps[1]
        receipts = rig.world.receipt_counts()["svc.write#1"]
        applied = rig.world.applied_counts()["svc.write#1"]

        if effect_class == "EXTERNAL":
            assert receipts == 1, "an EXTERNAL effect is never re-fired on the strength of a guess"
            assert applied == 1
            if resolution == "probe":
                assert step.state == "RESOLVED_COMPLETED" and view.phase == "COMPLETED"
            else:
                assert step.state == "RESOLVED_UNKNOWN"
                assert view.phase == "SUSPENDED", "escalate surfaces it, never retries it (L3)"
            return

        # PURE and IDEMPOTENT are safe to re-execute, so recovery re-runs the abandoned attempt.
        assert step.state == "COMPLETED"
        assert step.attempts == 2, "the abandoned attempt is closed and a new one is opened"
        assert receipts == 2, "the effect really was sent again"
        assert applied == (1 if dedup else 2), "what happens to it then is the receiver's choice"

    asyncio.run(check())


@PROP
@given(dedup=DEDUP, calls=CALLS)
def test_the_effect_key_is_stable_across_attempts(dedup: bool, calls: int) -> None:
    """The one thing a fence cannot buy. A fence cannot reach a third party; only a key the
    receiver honours can, and only if that key survives the crash unchanged (§8.4)."""

    async def check() -> None:
        rig = build(
            effect_class="IDEMPOTENT", dedup=dedup, tool_calls=calls, crash_after_effect=True
        )
        view = await rig.keel.get(await run_to_completion(rig))
        by_label: dict[str, set[str | None]] = {}
        for r in rig.world.receipts:
            by_label.setdefault(r.logical_identity, set()).add(r.effect_key)
        for label, keys in by_label.items():
            assert len(keys) == 1 and None not in keys, f"{label} was sent under {keys}"
        journaled = {s.effect_key for s in view.steps if s.kind == "TOOL"}
        assert journaled == {k for keys in by_label.values() for k in keys}

    asyncio.run(check())


@PROP
@given(effect_class=CLASSES, dedup=DEDUP, calls=CALLS, crash=CRASH)
def test_completed_steps_never_regress_and_at_most_one_step_is_open(
    effect_class: str, dedup: bool, calls: int, crash: bool
) -> None:
    """S5, and the sequential-step rule it rests on: at a crash at most one step can be missing an
    outcome, which is what makes the recovery table a table instead of a search."""

    async def check() -> None:
        events = await _journal(effect_class, dedup, calls, crash)
        frozen: dict[int, str] = {}
        for k in range(len(events) + 1):
            state = fold(events[:k])
            open_steps = [
                s for s in state.steps.values() if not s.settled and s.state != "RESOLVED_UNKNOWN"
            ]
            assert len(open_steps) <= 1, f"{len(open_steps)} steps open at prefix {k}"
            for step in state.steps.values():
                was = frozen.get(step.step_index)
                assert was is None or step.state == was, f"step {step.step_index}: {was}→{step.state}"
                if step.state in SETTLED_FOREVER:
                    frozen[step.step_index] = step.state

    asyncio.run(check())


@PROP
@given(effect_class=CLASSES, dedup=DEDUP, calls=CALLS, crash=CRASH)
def test_no_unjournaled_effect(effect_class: str, dedup: bool, calls: int, crash: bool) -> None:
    """S4: every World receipt is covered by a durably committed STEP_ATTEMPT_STARTED. The
    write-ahead rule is absolute — an effect taken in the world with no record that it was ever
    attempted is the one failure this design refuses to have."""

    async def check() -> None:
        rig = build(
            effect_class=effect_class, dedup=dedup, tool_calls=calls, crash_after_effect=crash
        )
        events = await rig.keel.events(await run_to_completion(rig))
        tool_steps = {
            e.step_index for e in events if e.type == "STEP_INTENDED" and e.body.kind == "TOOL"
        }
        starts = [e for e in events if e.type == "STEP_ATTEMPT_STARTED" and e.step_index in tool_steps]
        assert len(rig.world.receipts) <= len(starts)
        if rig.world.receipts:
            assert starts, "a receipt with no attempt behind it"

    asyncio.run(check())


async def _journal(effect_class: str, dedup: bool, calls: int, crash: bool):
    rig: Rig = build(
        effect_class=effect_class, dedup=dedup, tool_calls=calls, crash_after_effect=crash
    )
    return await rig.keel.events(await run_to_completion(rig))


# --- the guards the database enforces, seen from the writer's side -----------
async def test_the_journal_refuses_a_second_intent_started_or_outcome() -> None:
    """Partial unique indexes in Postgres, the same checks in memory. A runtime bug that would
    double-issue a step is a transaction that will not commit, never a silent overwrite."""
    j = MemoryJournal()
    row = memory_run_row(
        run_id=uuid.uuid4(), program="p", program_version="1", keel_version="0",
        args={}, budget={}, model_config={},
    )
    await j.create_run(row, RunCreated(program="p", program_version="1"), runnable_at=None)
    lease = await j.acquire(row.run_id, "w", timedelta(seconds=10))
    assert lease is not None

    async with j.append(lease) as tx:
        await tx.append(StepIntended(step_index=0, kind="TOOL", name="write"))
        await tx.append(StepAttemptStarted(
            step_index=0, attempt_no=1, lease_epoch=lease.epoch, started_at=j.clock.now()))
        await tx.append(StepCompleted(step_index=0, attempt_no=1, result={"ok": True}))

    for duplicate in (
        StepIntended(step_index=0, kind="TOOL", name="write"),
        StepAttemptStarted(step_index=0, attempt_no=1, lease_epoch=lease.epoch, started_at=j.clock.now()),
        StepCompleted(step_index=0, attempt_no=1, result={"ok": True}),
    ):
        with pytest.raises(IllegalTransition):
            async with j.append(lease) as tx:
                await tx.append(duplicate)

    events = await j.read(row.run_id)
    assert [e.type for e in events[1:]] == [
        "STEP_INTENDED", "STEP_ATTEMPT_STARTED", "STEP_COMPLETED"
    ], "a refused append leaves nothing behind"
