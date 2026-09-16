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


# --- S7: approvals, judged against the World ----------------------------------
KEY = "ac35c47458aae53e26f5c95ce780d840"  # a real binds_effect_key: 32 hex, never a World label


def gated(decision: str | None = "granted", applied: int = 1, *, requested: bool = True,
          label: str | None = "deploy.service#1", **kw) -> TrialFacts:
    """A W5 trial as its facts.json has it: the approval names an effect key, the effect ledger maps
    that key to a World label, and the World counts the label."""
    journal = [STARTED]
    if requested:
        journal.append({"seq": 3, "type": "APPROVAL_REQUESTED", "ts": 99.0, "step_index": 3,
                        "body": {"step_index": 3, "approval_id": "a1", "binds_effect_key": KEY}})
    if decision is not None:
        journal.append({"seq": 4, "type": "APPROVAL_DECIDED", "ts": 99.5, "step_index": 3,
                        "body": {"step_index": 3, "approval_id": "a1", "decision": decision}})
    return facts(
        journal=journal,
        world_applied={"deploy.service#1": applied} if applied else {},
        world_receipts=[],
        required_effects=(),
        sut_effects=[{"effect_key": KEY, "external_ref": label}] if label is not None else [],
        gated_tools={"deploy_service": "deploy.service"},
        **kw,
    )


def test_one_granted_approval_and_one_deploy_passes_s7() -> None:
    assert verify(gated()).findings["S7"].verdict == "PASS"


def test_two_deploys_under_one_approval_fail_s7_though_s1_passes_against_the_claim() -> None:
    v = verify(gated(applied=2))
    assert v.findings["S1"].verdict == "PASS", "EXTERNAL is claimed at_least_once"
    assert v.findings["S7"].verdict == "FAIL"
    assert v.findings["S7"].counterexample == {"approval_id": {"a1": {"deploy.service#1": 2}}}


def test_a_deploy_under_an_expired_approval_fails_s7() -> None:
    v = verify(gated(decision="expired"))
    assert v.findings["S7"].verdict == "FAIL"
    assert "without a GRANTED approval" in v.findings["S7"].detail


def test_a_deploy_under_an_undecided_approval_fails_s7() -> None:
    v = verify(gated(decision=None))
    assert v.findings["S7"].verdict == "FAIL"
    assert v.findings["S7"].counterexample["approval_id"]["a1"]["decision"] == "undecided"


def test_a_gated_deploy_with_no_approval_at_all_fails_s7_rather_than_gating_nothing() -> None:
    """The violation that matters most. Driven by the APPROVAL_REQUESTED events alone, this trial
    read "this workload gates nothing" — and a cell folds that N/A into a PASS."""
    v = verify(gated(decision=None, requested=False, label=None))
    assert v.findings["S7"].verdict == "FAIL"
    assert "no GRANTED approval bound" in v.findings["S7"].detail


def test_an_unlabelled_grant_accounts_for_one_deploy_and_no_more() -> None:
    """Started, applied, never resolved to a label (escalated): the grant still accounts for the one
    application on the gated endpoint, and a second is unapproved."""
    assert verify(gated(label=None)).findings["S7"].verdict == "PASS"
    assert verify(gated(label=None, applied=2)).findings["S7"].verdict == "FAIL"
    assert verify(gated(decision="rejected", label=None)).findings["S7"].verdict == "FAIL"


def test_an_approval_decided_twice_fails_s7() -> None:
    f = gated()
    f.journal.append({"seq": 5, "type": "APPROVAL_DECIDED", "ts": 99.6, "step_index": 3,
                      "body": {"step_index": 3, "approval_id": "a1", "decision": "granted"}})
    assert verify(f).findings["S7"].counterexample == {"approval_id": {"a1": 2}}


def test_a_gated_step_resolved_by_assume_failed_fails_s7() -> None:
    """`assume_failed` re-fires under the one approval, so a bound EXTERNAL tool may only resolve by
    probe or escalate (§9.4) — a FAIL even when the World happens to show one application."""
    f = gated()
    f.journal.append({"seq": 6, "type": "STEP_RESOLVED", "ts": 101.0, "step_index": 4,
                      "body": {"resolution": "RESOLVED_FAILED", "method": "assume_failed"}})
    v = verify(f)
    assert v.findings["S7"].verdict == "FAIL" and v.findings["S7"].counterexample == {"step_index": 4}


def test_s7_without_a_journal_names_the_missing_input() -> None:
    f = gated()
    f.journal = None
    v = verify(f)
    assert v.findings["S7"].verdict == "N/A" and "no journal" in v.findings["S7"].detail


def test_expiry_forbids_the_deploy_for_every_arm_through_logical_correctness() -> None:
    """S7 needs a journal; the forbidden label on the spec does not. A runtime with no journal that
    deploys under an expired wait is still not logically correct."""
    from crashproof.runner.bench import Matrix

    m = Matrix.load("bench/specs/w5.yaml")
    spec = next(c.spec for c in m.cells() if c.trigger == "approval_expiry@supervisor")
    common = dict(world_receipts=[], sut_committed=None, required_effects=(), status="COMPLETED",
                  expected_status="COMPLETED", expected_world_state=dict(spec.expected_world_state),
                  faults=[], t_restarts=[], wall_ms=1, model_calls=None, tokens=None,
                  storage_bytes=None, detect_ms=None, verdicts={})
    assert metrics.compute(world_applied={}, **common).logical_correctness == 1
    assert metrics.compute(world_applied={"deploy.service#1": 1}, **common).logical_correctness == 0


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


# --- S6 and the week-2 metrics (§12.4, §14.3 #19-#21) -----------------------------------------
def _cancelled(started_seq: int, *, labelled: bool = True) -> TrialFacts:
    """A cancel acknowledged at seq 10; the deploy's attempt STARTED at `started_seq`."""
    journal = [
        {"seq": 8, "type": "SIGNAL_RECEIVED", "ts": 50.0, "step_index": None, "body": {"signal_type": "cancel"}},
        {"seq": 10, "type": "CANCEL_ACKNOWLEDGED", "ts": 50.1, "step_index": 4, "body": {"step_index": 4}},
        {"seq": started_seq, "type": "STEP_ATTEMPT_STARTED", "ts": 49.0, "step_index": 4, "body": {}},
        {"seq": 20, "type": "RUN_CANCELLED", "ts": 51.0, "step_index": None, "body": {}},
    ]
    return facts(
        journal=journal, status="CANCELLED", required_effects=(),
        world_receipts=[{"logical_identity": "deploy.service#1", "ts": 50.5, "endpoint": "deploy.service"}],
        world_applied={"deploy.service#1": 1},
        sut_effects=[{"effect_key": "k", "step_index": 4, "external_ref": "deploy.service#1" if labelled else None}],
    )


def test_s6_allows_an_effect_in_flight_at_cancel_and_fails_one_started_after_it() -> None:
    before = verify(_cancelled(started_seq=7)).findings["S6"]
    assert before.verdict == "PASS" and "1 receipt(s) in flight" in before.detail
    after = verify(_cancelled(started_seq=12)).findings["S6"]
    assert after.verdict == "FAIL" and after.counterexample["after"] == ["deploy.service#1"]


def test_s6_is_n_a_with_no_journal_and_with_no_cancel() -> None:
    assert verify(facts(journal=None)).findings["S6"].verdict == "N/A"
    no_cancel = verify(facts()).findings["S6"]
    assert no_cancel.verdict == "N/A" and "nothing was cancelled" in no_cancel.detail


def test_approval_binding_violations_counts_what_s7_judges() -> None:
    from crashproof.verifier.invariants import approval_binding_violations as abv

    assert abv(gated()) == 0
    assert abv(gated(applied=3)) == 2, "two deploys beyond the one approved"
    assert abv(gated(decision="rejected")) == 1, "an applied deploy nobody granted"
    assert abv(gated(decision=None, requested=False, label=None)) == 1, "a gated deploy with no approval at all"
    assert abv(facts()) is None, "a workload that gates nothing has nothing to count"
    assert abv(facts(journal=None, gated_tools={"deploy_service": "deploy.service"})) is None


def _compute(**kw) -> metrics.Metrics:
    base = dict(
        world_applied={"deploy.service#1": 1}, world_receipts=[], sut_committed=None, required_effects=(),
        status="COMPLETED", expected_status="COMPLETED", expected_world_state={"deploy.service#1": 1},
        faults=[], t_restarts=[], wall_ms=1, model_calls=None, tokens=None, storage_bytes=None,
        detect_ms=None, verdicts={},
    )
    return metrics.compute(**{**base, **kw})


def test_wait_durability_is_the_wait_surviving_a_kill_and_nothing_else() -> None:
    killed = [{"type": "kill_while_waiting", "executed": True, "trigger_observed_at": 1.0}]
    assert _compute().wait_durability is None, "no kill during a wait: nothing to measure"
    assert _compute(faults=killed, t_restarts=[2.0]).wait_durability == 1
    wrong_world = _compute(faults=killed, t_restarts=[2.0], world_applied={"deploy.service#1": 2})
    assert wrong_world.wait_durability == 0, "survived, but deployed twice"


def test_cancel_latency_runs_from_the_drain_to_the_later_of_terminal_and_last_receipt() -> None:
    f = _cancelled(started_seq=7)
    m = _compute(journal=f.journal, world_receipts=f.world_receipts)
    assert m.cancel_latency_ms == 1000.0, "drained at 50.0, cancelled at 51.0, last receipt at 50.5"
    assert _compute(journal=[]).cancel_latency_ms is None
