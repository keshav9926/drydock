"""The fold, as properties (§12.6).

All run state is a pure fold over events, so the fold is the one place a projection bug can live —
and a projection bug is fixed by re-folding, never by editing events, which is only true if the
fold really is a fold: deterministic, incremental, and monotone over prefixes.

The input is always a *valid* journal, written by the real runtime. Random event lists would be
rejected by the fold and would test nothing.
"""

from __future__ import annotations

import asyncio

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from journals import CALLS, CLASSES, DEDUP, PAYLOADS, build, run_to_completion

from keel.core.hashing import canonical_json
from keel.journal.blobs import BLOB_THRESHOLD
from keel.state.fold import RunState, _apply, fold

PROP = settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
CRASH = st.sampled_from([False, True])

# §7.2's run machine, restricted to the MVP phases. SUSPENDED → RUNNING is a resume; a terminal
# phase has no successor but itself.
SUCCESSORS = {
    "CREATED": {"CREATED", "RUNNING"},
    "RUNNING": {"RUNNING", "COMPLETED", "FAILED", "SUSPENDED"},
    "SUSPENDED": {"SUSPENDED", "RUNNING"},
    "COMPLETED": {"COMPLETED"},
    "FAILED": {"FAILED"},
}


def _snapshot(state: RunState) -> str:
    """Canonical JSON, so equality is structural and dict order cannot hide a difference."""
    return canonical_json(
        {
            "phase": state.phase,
            "result": state.result,
            "error": state.error,
            "last_seq": state.last_seq,
            "epochs": state.epochs,
            "steps": [
                (s.step_index, s.kind, s.name, s.state, s.attempts, s.effect_key, s.result, s.error)
                for s in sorted(state.steps.values(), key=lambda s: s.step_index)
            ],
        }
    )


async def _events(effect_class: str, dedup: bool, calls: int, crash: bool, payload: int = 0):
    rig = build(
        effect_class=effect_class, dedup=dedup, tool_calls=calls,
        payload_bytes=payload, crash_after_effect=crash,
    )
    return await rig.keel.events(await run_to_completion(rig)), rig


@PROP
@given(effect_class=CLASSES, dedup=DEDUP, calls=CALLS, crash=CRASH)
def test_the_fold_is_deterministic(effect_class: str, dedup: bool, calls: int, crash: bool) -> None:
    """No wall clock, no dict-order dependence: the same events fold to the same projection, and
    to the same projection hash. C1 rests on this."""

    async def check() -> None:
        events, _ = await _events(effect_class, dedup, calls, crash)
        a, b = fold(events), fold(list(reversed(list(reversed(events)))))
        assert _snapshot(a) == _snapshot(b)
        assert a.projection_hash() == b.projection_hash()

    asyncio.run(check())


@PROP
@given(effect_class=CLASSES, dedup=DEDUP, calls=CALLS, crash=CRASH)
def test_incremental_equals_batch(effect_class: str, dedup: bool, calls: int, crash: bool) -> None:
    """`fold(events[:k+1]) == step(fold(events[:k]), events[k])` for every k. The property exists
    before projection checkpoints do, because it is what would make them safe (§12.6)."""

    async def check() -> None:
        events, _ = await _events(effect_class, dedup, calls, crash)
        incremental = RunState()
        for k, event in enumerate(events):
            _apply(incremental, event)
            incremental.last_seq = event.seq
            assert _snapshot(incremental) == _snapshot(fold(events[: k + 1]))

    asyncio.run(check())


@PROP
@given(effect_class=CLASSES, dedup=DEDUP, calls=CALLS, crash=CRASH)
def test_every_prefix_is_a_legal_predecessor(
    effect_class: str, dedup: bool, calls: int, crash: bool
) -> None:
    """Prefix monotonicity over the run machine: no prefix of a real journal folds to a phase the
    next prefix may not follow."""

    async def check() -> None:
        events, _ = await _events(effect_class, dedup, calls, crash)
        phases = [fold(events[:k]).phase for k in range(1, len(events) + 1)]
        for before, after in zip(phases, phases[1:], strict=False):
            assert after in SUCCESSORS[before], f"{before} -> {after}"

    asyncio.run(check())


@PROP
@given(payload=PAYLOADS, dedup=DEDUP)
def test_large_payloads_round_trip_through_the_blob_store(payload: int, dedup: bool) -> None:
    """Over 32 KiB a field is stored once, content-addressed, and referenced. The fold must not be
    able to tell: the projection is the same whether the value travelled inline or by hash."""

    async def check() -> None:
        events, rig = await _events("IDEMPOTENT", dedup, 1, False, payload=payload)
        big = payload > BLOB_THRESHOLD
        externalised = [e for e in events if e.env.blob_ids]
        assert bool(externalised) == big, f"{payload} bytes: blob_ids={[e.type for e in externalised]}"
        intended = next(
            e.body.args for e in events if e.type == "STEP_INTENDED" and e.step_index == 1
        )
        assert intended["body"] == "x" * payload, "the value read back is the value written"
        assert fold(events).steps[1].result["logical_identity"] == "svc.write#1"

    asyncio.run(check())
