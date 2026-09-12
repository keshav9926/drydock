"""`crashproof verify` and the two fault-analysis views (§19.5, §28.6).

The command exists for one job the publication rule names: re-run the verifier over facts already
on disk and prove the verdict is a function of them. That is only possible if the trial directory
holds the facts rather than the live objects they were read from, so the round trip through
`facts.json` is the first thing checked here.

The views are diagnostics, and the property that makes them worth having is that they disagree
with a bare verdict in the useful direction: placement says *where* the kill landed, so a cell
whose faults all fired at the wrong boundary is visible as a harness defect rather than as a
runtime finding; the ledger says *which* effect, so a FAIL is a diagnosis rather than a count.
"""

from __future__ import annotations

import json

from crashproof.verifier import invariants, views

RUN_START = "2026-01-01T00:00:00+00:00"


def event(seq: int, kind: str, offset: float, step: int | None = None, attempt: int = 1):
    from datetime import UTC, datetime, timedelta

    ts = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset)
    return {
        "seq": seq, "type": kind, "ts": ts.isoformat(), "lease_epoch": 0,
        "step_index": step, "attempt_no": attempt, "body": {},
    }


def facts(**over) -> invariants.TrialFacts:
    from datetime import UTC, datetime

    base = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    defaults = dict(
        world_receipts=[
            {"endpoint": "issues.create", "effect_key": "k-1",
             "logical_identity": "issues.create#1", "ts": base + 3.0},
        ],
        world_applied={"issues.create#1": 1},
        sut_committed={"issues.create#1"},
        journal=[
            event(1, "RUN_CREATED", 0.0),
            event(2, "STEP_INTENT", 1.0, step=0),
            event(3, "STEP_ATTEMPT_STARTED", 2.0, step=0),
            event(4, "STEP_COMPLETED", 4.0, step=0),
            event(5, "RECOVERY_STARTED", 5.0),
        ],
        status="COMPLETED",
        required_effects=("issues.create#1",),
        claims={"EXTERNAL": "at_least_once"},
        effect_class="EXTERNAL",
        faults=[{
            "fault_id": "f1", "type": "kill", "boundary": "after", "landmark": "tool_effect",
            "occurrence": 1, "recovery_index": 0, "executed": True,
            "trigger_observed_at": base + 3.5,
        }],
        sut_effects=[{
            "effect_key": "k-1", "step_index": 0, "tool": "create_issue", "class": "EXTERNAL",
            "status": "COMMITTED", "external_ref": "issues.create#1", "resolution": None,
        }],
        reached_terminal=True,
    )
    return invariants.TrialFacts(**{**defaults, **over})


def test_facts_survive_the_trip_through_a_file_and_the_verdict_does_too() -> None:
    """`verify` is only possible if the directory holds the facts. A round trip that lost the
    committed set would turn S2 from PASS into N/A — a verdict quietly weakened by serialisation,
    which is the failure this check exists to make loud."""
    f = facts()
    reloaded = invariants.load(json.loads(json.dumps(invariants.dump(f), default=str)))
    assert reloaded.sut_committed == f.sut_committed
    assert reloaded.required_effects == f.required_effects, "a tuple, not a list, on the way back"
    assert invariants.verify(reloaded).as_dict() == invariants.verify(f).as_dict()


def test_the_verdict_is_byte_identical_on_a_second_run() -> None:
    """What `--recheck` asserts. Two runs over one set of facts must serialise identically,
    details and counterexamples included: a verdict that stayed PASS while its reason changed is
    still a verifier that is not a pure function of its inputs."""
    f = facts()

    def canonical() -> str:
        v = invariants.verify(f)
        return json.dumps(
            {"verdicts": v.as_dict(),
             "details": {n: x.detail for n, x in sorted(v.findings.items())},
             "counterexamples": v.counterexamples()},
            sort_keys=True, default=str,
        )

    assert canonical() == canonical()


def test_placement_says_which_attempt_was_open_when_the_kill_landed() -> None:
    """The diagnostic §11.2 requires beside every published cell. A kill at `after:tool_effect`
    has to land with the effect in the World and the step still open in the journal — the row
    below is what "it landed where it aimed" looks like, and any other shape is a mis-aimed
    schedule rather than a finding."""
    killed = facts(journal=[
        event(1, "RUN_CREATED", 0.0),
        event(2, "STEP_INTENT", 1.0, step=0),
        event(3, "STEP_ATTEMPT_STARTED", 2.0, step=0),
        event(4, "RECOVERY_STARTED", 6.0),
    ])
    row = views.placement(killed)[0]
    assert row["open_step"] == "0.1", "the attempt the fault interrupted"
    assert row["last_seq_before"] == 3 and row["first_seq_after"] == 4
    assert row["recovery_seq"] == 4, "a successor did come back for it"
    assert row["receipt_before"] == "issues.create#1", "the World has the effect"
    assert row["receipt_after"] is None, "and nothing happened after"


def test_placement_reports_a_fault_that_landed_between_steps() -> None:
    """A kill with no attempt open is a different window and a different recovery path, so the
    view has to distinguish it rather than print the last attempt it saw."""
    from datetime import UTC, datetime

    base = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    late = facts(faults=[{**facts().faults[0], "trigger_observed_at": base + 4.5}])
    row = views.placement(late)[0]
    assert row["open_step"] is None, "step 0 completed at seq 4, half a second before the fault"
    assert row["last_type_before"] == "STEP_COMPLETED"
    assert row["last_seq_before"] == 4


def test_the_ledger_judges_one_effect_at_a_time() -> None:
    f = facts()
    [row] = views.effect_ledger(f)
    assert row["identity"] == "issues.create#1"
    assert (row["world_receipts"], row["world_applied"]) == (1, 1)
    assert (row["started_seq"], row["outcome_seq"]) == (3, 4)
    assert row["S1"] == "PASS" and row["S2"] == "PASS" and row["S4"] == "PASS"
    assert row["C3"] == "N/A", "not built; absent rather than stubbed, so it cannot read as a pass"


def test_a_duplicate_is_a_fail_only_against_a_claim_that_forbids_it() -> None:
    """The Jepsen rule, one row at a time: an arm held to `at_least_once` has not violated S1 by
    applying twice, and the count is printed either way."""
    honest = views.effect_ledger(facts(world_applied={"issues.create#1": 2}))[0]
    assert honest["world_applied"] == 2 and honest["S1"] == "PASS"

    strict = views.effect_ledger(
        facts(world_applied={"issues.create#1": 2}, claims={"EXTERNAL": "effectively_once"})
    )[0]
    assert strict["S1"] == "FAIL"


def test_each_row_is_judged_against_its_own_effect_class() -> None:
    """The workload runs a PURE read beside the EXTERNAL write under test. Judging that read
    against the cell's EXTERNAL claim would hold the strictest band to the loosest promise — a
    PURE step applied twice violates `effectively_once` whatever the cell was aimed at."""
    f = facts(
        claims={"EXTERNAL": "at_least_once", "PURE": "effectively_once"},
        world_applied={"issues.create#1": 1, "kv.search#1": 2},
        world_receipts=[],
        sut_committed={"issues.create#1", "kv.search#1"},
        sut_effects=[
            {"effect_key": "k-1", "step_index": 0, "class": "EXTERNAL",
             "status": "COMMITTED", "external_ref": "issues.create#1", "resolution": None},
            {"effect_key": "k-0", "step_index": 1, "class": "PURE",
             "status": "COMMITTED", "external_ref": "kv.search#1", "resolution": None},
        ],
    )
    rows = {r["identity"]: r for r in views.effect_ledger(f)}
    assert rows["issues.create#1"]["claim"] == "at_least_once"
    assert rows["kv.search#1"]["claim"] == "effectively_once"
    assert rows["kv.search#1"]["S1"] == "FAIL", "twice, under a claim that forbids it"


def test_a_receipt_no_effect_row_claims_is_still_in_the_ledger() -> None:
    """A receipt nothing in the runtime admits to is the shape S4 exists to catch, so it cannot be
    a row the ledger simply does not print."""
    rows = views.effect_ledger(facts(sut_effects=[], sut_committed=set(), world_applied={}))
    assert [r["identity"] for r in rows] == ["issues.create#1"]
    assert rows[0]["world_receipts"] == 1 and rows[0]["world_applied"] == 0


def test_a_runtime_with_no_journal_gets_empty_columns_not_a_pass() -> None:
    [row] = views.effect_ledger(facts(journal=None, sut_committed=None, sut_effects=None))
    assert row["S2"] == "N/A" and row["S4"] == "N/A"
    assert row["started_seq"] is None and row["outcome_seq"] is None


def test_an_effect_the_runtime_opened_and_never_landed_is_still_a_row() -> None:
    """The EXTERNAL band's whole subject. A ledger that listed only what reached the World would
    never show the step that opened, did something unknowable, and left no identity behind."""
    rows = views.effect_ledger(facts(
        world_receipts=[], world_applied={}, sut_committed=set(),
        sut_effects=[{"effect_key": "k-9", "step_index": 0, "tool": "create_issue",
                      "class": "EXTERNAL", "status": "AMBIGUOUS", "external_ref": None,
                      "resolution": None}],
    ))
    assert [r["identity"] for r in rows] == ["(unresolved) k-9"]
    assert rows[0]["status"] == "AMBIGUOUS" and rows[0]["world_applied"] == 0


def test_verify_on_a_trial_directory(tmp_path) -> None:
    """The wiring, end to end: a directory with a `facts.json` in it verifies, and one without is
    refused rather than silently reported as clean."""
    from typer.testing import CliRunner

    from crashproof.cli.main import app

    runner = CliRunner()
    trial = tmp_path / "t-7"
    trial.mkdir()
    assert runner.invoke(app, ["verify", str(trial)]).exit_code == 2, "no facts, no verdict"

    (trial / "facts.json").write_text(json.dumps(invariants.dump(facts()), default=str), encoding="utf8")
    result = runner.invoke(app, ["verify", str(trial), "--recheck", "--placement", "--effects"])
    assert result.exit_code == 0, result.output
    assert "issues.create#1" in result.output
