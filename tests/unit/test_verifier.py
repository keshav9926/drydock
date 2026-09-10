"""The verifier, which is the one component whose bugs would be invisible in the published table.

A wrong runtime produces a wrong result and someone notices. A wrong *verifier* produces a
confident result and nobody does — so the rules that stop it flattering either side are tested
directly: judged against claims, N/A where an input is missing, and never a proportion for safety.
"""

from __future__ import annotations

from crashproof.verifier import metrics
from crashproof.verifier.invariants import TrialFacts, verify

STARTED = {"seq": 5, "type": "STEP_ATTEMPT_STARTED", "ts": 100.0, "step_index": 3, "body": {}}
COMPLETED = {"seq": 6, "type": "STEP_COMPLETED", "ts": 101.0, "step_index": 3, "body": {}}


def facts(**kw) -> TrialFacts:
    base = dict(
        world_receipts=[{"logical_identity": "issues.create#1", "ts": 100.5, "endpoint": "issues.create"}],
        world_applied={"issues.create#1": 1},
        sut_committed={"issues.create#1"},
        journal=[STARTED, COMPLETED],
        status="COMPLETED",
        required_effects=("issues.create#1",),
        claims={"EXTERNAL": "at_least_once", "IDEMPOTENT": "effectively_once"},
        effect_class="EXTERNAL",
    )
    return TrialFacts(**{**base, **kw})


# --- S1: the Jepsen rule -----------------------------------------------------
def test_a_duplicate_is_not_a_violation_when_the_arm_claimed_it_might_be() -> None:
    v = verify(facts(world_applied={"issues.create#1": 2}))
    assert v.findings["S1"].verdict == "PASS"
    assert "at_least_once" in v.findings["S1"].detail
    assert "issues.create#1" in v.findings["S1"].detail, "and the duplicate is published anyway"


def test_the_same_duplicate_is_a_violation_when_the_arm_claimed_it_could_not_happen() -> None:
    v = verify(facts(effect_class="IDEMPOTENT", world_applied={"issues.upsert#1": 2},
                     sut_committed={"issues.upsert#1"}, required_effects=("issues.upsert#1",)))
    assert v.findings["S1"].verdict == "FAIL"
    assert v.findings["S1"].counterexample == {"applied": {"issues.upsert#1": 2}}


def test_receipts_are_not_effects() -> None:
    """Two requests and one application is a receiver doing its job, not a runtime failing."""
    v = verify(facts(
        effect_class="IDEMPOTENT",
        world_applied={"issues.upsert#1": 1},
        world_receipts=[
            {"logical_identity": "issues.upsert#1", "ts": 100.5, "endpoint": "issues.upsert"},
            {"logical_identity": "issues.upsert#1", "ts": 103.0, "endpoint": "issues.upsert"},
        ],
        sut_committed={"issues.upsert#1"},
        required_effects=("issues.upsert#1",),
    ))
    assert v.findings["S1"].verdict == "PASS"


# --- S2, S3: lost and phantom ------------------------------------------------
def test_an_effect_the_runtime_claims_but_the_world_never_saw_is_lost() -> None:
    v = verify(facts(sut_committed={"issues.create#1", "issues.create#2"}))
    assert v.findings["S2"].verdict == "FAIL"
    assert v.findings["S2"].counterexample == {"lost": ["issues.create#2"]}


def test_a_runtime_that_cannot_say_what_it_committed_gets_na_not_a_pass() -> None:
    v = verify(facts(sut_committed=None))
    assert v.findings["S2"].verdict == "N/A"
    assert v.findings["S1"].verdict == "PASS", "S1 needs only the World, so it still answers"


def test_completing_without_the_required_effect_is_a_phantom_completion() -> None:
    v = verify(facts(world_applied={}, sut_committed=set()))
    assert v.findings["S3"].verdict == "FAIL"
    assert v.findings["S3"].counterexample == {"missing": ["issues.create#1"]}


def test_a_run_that_did_not_complete_claims_nothing() -> None:
    v = verify(facts(status="SUSPENDED", world_applied={}, sut_committed=set(),
                     expected_status="SUSPENDED"))
    assert v.findings["S3"].verdict == "PASS"


# --- S4, S5: the journal-only invariants -------------------------------------
def test_a_receipt_with_no_attempt_behind_it_is_unjournaled() -> None:
    """The write-ahead rule seen from outside: an action taken in the world with no record that it
    was ever attempted is the one failure the design refuses to have."""
    v = verify(facts(world_receipts=[{"logical_identity": "issues.create#1", "ts": 99.0}]))
    assert v.findings["S4"].verdict == "FAIL"


def test_s4_and_s5_are_na_without_a_journal() -> None:
    v = verify(facts(journal=None))
    assert v.findings["S4"].verdict == "N/A" and v.findings["S5"].verdict == "N/A"
    assert v.findings["S3"].verdict == "PASS", "the N/As are named individually, never bundled"


def test_an_attempt_after_a_settled_step_regresses_it() -> None:
    reopened = [STARTED, COMPLETED, {"seq": 7, "type": "STEP_ATTEMPT_STARTED", "ts": 102.0,
                                     "step_index": 3, "body": {}}]
    v = verify(facts(journal=reopened))
    assert v.findings["S5"].verdict == "FAIL"
    assert v.findings["S5"].counterexample == {"step_index": 3, "seq": 7}


def test_a_resolved_absent_step_may_be_attempted_again() -> None:
    """§7.4's at-least-once edge is a legal transition, not a regression: the receiver said the
    effect never landed, so a second attempt is the recovery table doing its job."""
    journal = [
        STARTED,
        {"seq": 6, "type": "STEP_RESOLVED", "ts": 101.0, "step_index": 3,
         "body": {"resolution": "RESOLVED_FAILED", "method": "probe"}},
        {"seq": 7, "type": "STEP_ATTEMPT_STARTED", "ts": 102.0, "step_index": 3, "body": {}},
        {"seq": 8, "type": "STEP_COMPLETED", "ts": 103.0, "step_index": 3, "body": {}},
    ]
    assert verify(facts(journal=journal)).findings["S5"].verdict == "PASS"


# --- L1, L2 ------------------------------------------------------------------
def test_a_timeout_is_a_liveness_failure() -> None:
    v = verify(facts(status="UNKNOWN", timed_out=True))
    assert v.findings["L1"].verdict == "FAIL"


def test_a_legitimately_suspended_run_has_recovered() -> None:
    """An ambiguity surfaced is a recovered run. Surfacing is what `escalate` is for, and scoring
    it as a failure would reward the runtimes that guess."""
    v = verify(facts(status="SUSPENDED", expected_status="SUSPENDED"))
    assert v.findings["L1"].verdict == "PASS"


def test_restarts_past_the_bound_are_a_liveness_failure() -> None:
    v = verify(facts(restarts=4, max_recoveries=3))
    assert v.findings["L2"].verdict == "FAIL"


# --- metrics -----------------------------------------------------------------
def test_duplicate_effects_and_receipts_are_counted_apart() -> None:
    m = metrics.compute(
        world_applied={"issues.upsert#1": 1},
        world_receipts=[
            {"logical_identity": "issues.upsert#1", "ts": 100.0},
            {"logical_identity": "issues.upsert#1", "ts": 103.0},
        ],
        sut_committed={"issues.upsert#1"},
        required_effects=("issues.upsert#1",),
        status="COMPLETED",
        expected_status="COMPLETED",
        expected_world_state={"issues.upsert#1": 1},
        faults=[],
        t_restarts=[],
        wall_ms=1000,
        model_calls=3,
        tokens=100,
        storage_bytes=None,
        detect_ms=None,
        verdicts={"L1": "PASS", "L2": "PASS"},
    )
    assert (m.duplicate_effects, m.duplicate_receipts) == (0, 1)
    assert m.logical_correctness == 1 and m.recovery_rate == 1


def test_a_probe_counts_as_the_first_live_act() -> None:
    """In the EXTERNAL band, asking the receiver what happened is the entire live act after a
    crash. A definition counting only effects would report no recovery for the band that recovers
    most carefully."""
    m = metrics.compute(
        world_applied={"issues.create#1": 1},
        world_receipts=[{"logical_identity": "issues.create#1", "ts": 100.0}],
        world_probes=[{"logical_identity": "issues.create#1", "ts": 105.0}],
        sut_committed={"issues.create#1"},
        required_effects=("issues.create#1",),
        status="COMPLETED",
        expected_status="COMPLETED",
        expected_world_state={"issues.create#1": 1},
        faults=[{"trigger_observed_at": 101.0}],
        t_restarts=[103.0],
        wall_ms=5000,
        model_calls=3,
        tokens=100,
        storage_bytes=None,
        detect_ms=None,
        verdicts={"L1": "PASS", "L2": "PASS"},
    )
    assert m.recovery_latency_ms == 4000.0, "fault at 101, first live act at 105"
    assert m.time_to_first_live_step_ms == 2000.0
    assert m.restart_latency_ms == 2000.0, "harness-owned, printed, never compared across arms"


def test_a_wrong_world_is_not_partially_correct() -> None:
    m = metrics.compute(
        world_applied={"issues.create#1": 2},
        world_receipts=[],
        sut_committed=None,
        required_effects=("issues.create#1",),
        status="COMPLETED",
        expected_status="COMPLETED",
        expected_world_state={"issues.create#1": 1},
        faults=[],
        t_restarts=[],
        wall_ms=1,
        model_calls=None,
        tokens=None,
        storage_bytes=None,
        detect_ms=None,
        verdicts={},
    )
    assert m.logical_correctness == 0
    assert m.lost_effects is None, "an unexposed committed set is not zero lost effects"
