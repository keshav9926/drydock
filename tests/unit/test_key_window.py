"""§9.1's crash-open half and §9.7's `max_elapsed`: an IDEMPOTENT re-send is bounded, and past the
bound the attempt that may have landed goes to a human — the live half's `key_window_expired` path.

Recovery re-runs an abandoned attempt even under `NO_RETRY` (recovery is not retry, §8.3), so the
retry policy cannot bound it: its own count does (`MAX_ABANDONED_ATTEMPTS`), and so does the
receiver's key window, measured by the store's clock from the step's first STARTED. Driven through
the property suite's `Sim`: the real worker, engine, reaper and `MemoryJournal` on a fake clock.
"""

from __future__ import annotations

import pytest

from keel.runtime.steps import MAX_ABANDONED_ATTEMPTS
from keel.state.fold import fold
from tests.property import sim as sim_module
from tests.property.sim import TTL, Sim, SimRetry, ToolDecl

ONE_CALL = [{"op": "tool", "tool": "t0", "gated": False}]


def _sim(retry: str = "none", timeout: float = 5.0) -> Sim:
    return Sim([ToolDecl("t0", cls="IDEMPOTENT", dedup=True, timeout=timeout)], ONE_CALL, retry=retry)


def _crash_mid_effect(sim: Sim, slot: str) -> None:
    """Start a worker in `slot`, kill it with the request in flight, and let the lease lapse."""
    assert sim.restart_worker(slot)
    assert any(h.worker.state == "live" for h in sim.completable()), "the attempt is in flight"
    sim.crash(slot, "during:effect_exec")
    sim.tick(TTL + 2)


def _events(sim: Sim, type_: str) -> list:
    return [e for e in sim.events(sim.root) if e.type == type_]


def _effect_row(sim: Sim):
    [row] = [e for e in sim.run(sim.journal.effects(sim.root)) if e.step_index == 0]
    return row


def test_an_attempt_abandoned_below_the_count_is_re_sent_under_the_same_key() -> None:
    sim = _sim()
    try:
        for k in range(MAX_ABANDONED_ATTEMPTS - 1):
            _crash_mid_effect(sim, ("W0", "W1")[k % 2])
        assert sim.restart_worker("W0")
        sim.advance(1)
        state = fold(sim.events(sim.root))
        assert state.phase == "COMPLETED", state.phase
        assert state.steps[0].abandoned == MAX_ABANDONED_ATTEMPTS - 1
        keys = {e.body.effect_key for e in _events(sim, "STEP_INTENDED")}
        assert len(keys) == 1 and _effect_row(sim).attempt_no == MAX_ABANDONED_ATTEMPTS
        sim.check()
    finally:
        sim.close()


@pytest.mark.parametrize("lands", [True, False])
def test_the_count_bounds_recovery_and_a_human_settles_what_may_have_landed(lands: bool) -> None:
    """Under `NO_RETRY`: the third abandoned attempt is not re-sent. The step goes AMBIGUOUS then
    RESOLVED_UNKNOWN{key_window_expired}, the row RESOLVED_UNKNOWN, the run SUSPENDED — and a truthful
    human's `resolve` settles it whichever way the World says it went, with C1/C3 holding."""
    sim = _sim()
    try:
        for k in range(MAX_ABANDONED_ATTEMPTS):
            if k == MAX_ABANDONED_ATTEMPTS - 1:
                assert sim.restart_worker("W0")
                [held] = [h for h in sim.completable() if h.worker.state == "live"]
                sim.crash("W0", "during:effect_exec")
                if lands:
                    sim.complete(held, "ok")  # the request had left; it lands with nobody awaiting it
                sim.tick(TTL + 2)
            else:
                _crash_mid_effect(sim, "W0")
        assert sim.restart_worker("W1")
        state = fold(sim.events(sim.root))
        assert state.phase == "SUSPENDED", state.phase
        step = state.steps[0]
        assert (step.state, step.method) == ("RESOLVED_UNKNOWN", "key_window_expired")
        [amb] = _events(sim, "STEP_AMBIGUOUS")
        assert (amb.attempt_no, amb.body.cause) == (MAX_ABANDONED_ATTEMPTS, "crash")
        [res] = _events(sim, "STEP_RESOLVED")
        assert "a count of their own" in res.body.evidence["reason"]
        assert [e.body.error for e in _events(sim, "STEP_FAILED")] == ["attempt_abandoned"] * (MAX_ABANDONED_ATTEMPTS - 1)
        assert len(_events(sim, "STEP_ATTEMPT_STARTED")) == MAX_ABANDONED_ATTEMPTS, "no fourth send"
        assert _effect_row(sim).status == "RESOLVED_UNKNOWN"
        sim._c3()
        sim.check()

        sim.deliver(sim.root, "resolve", "open")
        assert sim.restart_worker("W0")
        state = fold(sim.events(sim.root))
        assert state.steps[0].state == ("RESOLVED_COMPLETED" if lands else "RESOLVED_FAILED")
        assert state.phase == ("COMPLETED" if lands else "FAILED"), state.phase
        assert sim.world.applied_counts() == ({"t0.call#1": 1} if lands else {})
        sim.check()
        sim.quiesce()
        sim.check_teardown()
    finally:
        sim.close()


def test_a_recovery_past_max_elapsed_goes_to_a_human_on_the_first_abandonment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sim_module.POLICIES, "window", SimRetry(max_attempts=1, max_elapsed_s=10.0))
    sim = _sim(retry="window")
    try:
        _crash_mid_effect(sim, "W0")  # the successor arrives TTL + 2 s after the first STARTED
        assert sim.restart_worker("W1")
        state = fold(sim.events(sim.root))
        assert state.phase == "SUSPENDED" and state.steps[0].method == "key_window_expired"
        [res] = _events(sim, "STEP_RESOLVED")
        assert "key window is spent" in res.body.evidence["reason"]
        assert len(_events(sim, "STEP_ATTEMPT_STARTED")) == 1
        sim.check()
    finally:
        sim.close()


@pytest.mark.parametrize("answer_after_s, expect", [(0.0, "COMPLETED"), (3.0, "SUSPENDED")])
def test_a_live_retry_is_refused_outside_the_key_window(
    monkeypatch: pytest.MonkeyPatch, answer_after_s: float, expect: str
) -> None:
    """The receiver applies and answers 5xx: an unknown outcome. Inside the window the policy's
    retry re-sends under the key (the World dedups it); a retry that would start past `max_elapsed`
    is not sent, and the step is the live half's RESOLVED_UNKNOWN."""
    monkeypatch.setitem(
        sim_module.POLICIES, "window", SimRetry(max_attempts=3, base_s=0.5, max_backoff_s=4.0, max_elapsed_s=2.0)
    )
    sim = _sim(retry="window")
    try:
        assert sim.restart_worker("W0")
        sim.tick(answer_after_s)
        [held] = sim.completable()
        sim.complete(held, "error")
        sim.tick(1.0)  # an in-process backoff (0.5 s at the top of its window) comes due
        if expect == "COMPLETED":
            sim.advance(1)
        state = fold(sim.events(sim.root))
        assert state.phase == expect, state.phase
        started = len(_events(sim, "STEP_ATTEMPT_STARTED"))
        assert started == (2 if expect == "COMPLETED" else 1)
        if expect == "SUSPENDED":
            assert state.steps[0].method == "key_window_expired" and _effect_row(sim).status == "RESOLVED_UNKNOWN"
        assert sim.world.applied_counts() == {"t0.call#1": 1}
        sim._c3()
        sim.check()
    finally:
        sim.close()
