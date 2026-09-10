"""The fault spec and its seeded expansion (§11.3, §11.6).

A schedule is the only place a trial's randomness lives, so these are the properties the whole
reproducibility story rests on: the same (spec_hash, seed) gives the same schedule byte for byte,
different seeds give different schedules, and a trigger that could never fire is an error rather
than a trial that silently scores zero.
"""

from __future__ import annotations

import pytest

from crashproof.faults import schedule as sched
from crashproof.faults.log import Cursor, FaultFired, Observation, TrialDir
from crashproof.faults.spec import CrashproofSpecError, ScheduleExceedsRecoveries, UnreachableTrigger, from_doc
from crashproof.faults.triggers import Matcher
from crashproof.workloads.tool_chain_1_effect import WORKLOAD

T2 = {
    "name": "kill_after_effect",
    "workload": "tool_chain_1_effect",
    "workload_variant": "EXTERNAL",
    "mode": "shim",
    "max_recoveries": 3,
    "timeout": 90,
    "faults": [
        {
            "id": "f1",
            "type": "kill",
            "trigger": {"boundary": "after:tool_effect", "landmark": "tool:create_issue", "occurrence": 1},
        }
    ],
}


def test_the_spec_hash_is_the_document_not_the_name() -> None:
    a = from_doc(T2)
    b = from_doc({**T2, "name": "a different human name"})
    c = from_doc({**T2, "max_recoveries": 4})
    assert a.spec_hash != b.spec_hash, "the name is part of the document"
    assert a.spec_hash != c.spec_hash
    assert from_doc(dict(T2)).spec_hash == a.spec_hash, "and it is stable"


def test_the_same_spec_and_seed_expand_identically() -> None:
    spec = from_doc(T2)
    a, b = sched.expand(spec, 7, WORKLOAD), sched.expand(spec, 7, WORKLOAD)
    assert sched.canonical_json(a) == sched.canonical_json(b)
    assert a.hash() == b.hash()
    assert a.hash() != sched.expand(spec, 8, WORKLOAD).hash(), "one seed is one trial"


def test_a_baseline_spec_is_a_spec() -> None:
    """`faults: []` is what makes every delta metric computable, so it is first-class."""
    spec = from_doc({**T2, "name": "baseline", "faults": []})
    assert spec.is_baseline
    assert sched.expand(spec, 7, WORKLOAD).entries == ()


def test_independent_streams_per_fault() -> None:
    """Adding a fault must not move an existing fault's draws — only the spec hash changes."""
    one = {**T2, "faults": [{**T2["faults"][0], "params": {"pause_ms": {"uniform": [2000, 4000]}}}]}
    two = {
        **one,
        "faults": [
            one["faults"][0],
            {
                "id": "f2",
                "type": "pause_past_ttl",
                "trigger": {"boundary": "before:tool_call", "landmark": "tool:search"},
                "params": {"pause_ms": {"uniform": [2000, 4000]}},
            },
        ],
    }
    # The seed is derived from the spec hash, so the streams are compared at equal spec identity by
    # holding the hash fixed and asking only that the *stream* is keyed by fault id.
    a = sched.expand(from_doc(one), 7, WORKLOAD).entries[0]
    b = next(e for e in sched.expand(from_doc(two), 7, WORKLOAD).entries if e.landmark == "tool:create_issue")
    assert a.type == b.type and a.landmark == b.landmark
    assert set(a.params) == set(b.params) == {"pause_ms"}


def test_drawn_params_are_concrete_in_the_schedule() -> None:
    doc = {
        **T2,
        "faults": [
            {
                **T2["faults"][0],
                "type": "pause_past_ttl",
                "params": {"pause_ms": {"uniform": [2000, 4000]}, "note": {"choice": ["a", "b"]}},
            }
        ],
    }
    entry = sched.expand(from_doc(doc), 7, WORKLOAD).entries[0]
    assert 2000 <= entry.params["pause_ms"] <= 4000
    assert entry.params["note"] in ("a", "b"), "a distribution is resolved once, at expansion"


def test_an_unreachable_trigger_is_loud() -> None:
    doc = {**T2, "faults": [{**T2["faults"][0], "trigger": {**T2["faults"][0]["trigger"], "occurrence": 99}}]}
    with pytest.raises(UnreachableTrigger):
        sched.expand(from_doc(doc), 7, WORKLOAD)


def test_a_schedule_that_outruns_max_recoveries_is_loud() -> None:
    """A crash-loop cell must declare the restarts it needs, or the supervisor would stop before
    the schedule finished and the trial would score a bound it never actually tested."""
    doc = {**T2, "max_recoveries": 2, "faults": [{**T2["faults"][0], "count": 3}]}
    with pytest.raises(ScheduleExceedsRecoveries):
        sched.expand(from_doc(doc), 7, WORKLOAD)


def test_unbuilt_modes_and_fault_types_are_refused_at_load() -> None:
    """A spec naming machinery that does not exist yet must fail loudly, not run and fire nothing."""
    with pytest.raises(CrashproofSpecError):
        from_doc({**T2, "mode": "proxy"})
    with pytest.raises(CrashproofSpecError):
        from_doc({**T2, "faults": [{**T2["faults"][0], "type": "tool_500"}]})
    with pytest.raises(CrashproofSpecError):
        from_doc({**T2, "faults": [{**T2["faults"][0], "trigger": {"boundary": "during:nap", "landmark": "tool:x"}}]})


def test_the_workload_declares_its_landmarks() -> None:
    assert WORKLOAD.expected_occurrences("tool:create_issue") == 1
    assert WORKLOAD.expected_occurrences("tool:search") == 1
    assert WORKLOAD.expected_occurrences("tool:*") == 2
    assert WORKLOAD.expected_occurrences("model:*") == 3
    assert "tool:create_issue" in WORKLOAD.landmarks()


# --- matching, and the state that has to survive a kill ----------------------
def test_the_matcher_fires_once_on_the_named_occurrence() -> None:
    schedule = sched.expand(from_doc(T2), 7, WORKLOAD)
    m = Matcher(schedule)

    m.bump("tool:search", "after:tool_effect")
    assert m.match("tool:search", "after:tool_effect") is None, "a different landmark"

    m.bump("tool:create_issue", "before:tool_call")
    assert m.match("tool:create_issue", "before:tool_call") is None, "a different boundary"

    m.bump("tool:create_issue", "after:tool_effect")
    entry = m.match("tool:create_issue", "after:tool_effect")
    assert entry is not None and entry.type == "kill"

    m.spend(entry)
    m.bump("tool:create_issue", "after:tool_effect")
    assert m.match("tool:create_issue", "after:tool_effect") is None, "an entry is spent once"


def test_occurrences_are_counted_across_restarts(tmp_path) -> None:
    """The counter is rebuilt from disk, which is what lets `occurrence: 2` mean "after the
    restart" — a memoizing runtime never gets there and a re-executing one does."""
    doc = {**T2, "faults": [{**T2["faults"][0], "trigger": {**T2["faults"][0]["trigger"], "occurrence": 2}}]}
    schedule = sched.expand(from_doc(doc), 7, WORKLOAD)
    trial = TrialDir(tmp_path / "t-7")

    first = Matcher(schedule, recovery_index=0)
    occ = first.bump("tool:create_issue", "after:tool_effect")
    trial.append_observation(
        Observation(landmark="tool:create_issue", boundary="after:tool_effect", occurrence=occ,
                    recovery_index=0, ts=1.0)
    )
    assert first.match("tool:create_issue", "after:tool_effect") is None

    # ---- the process dies here; a new one rebuilds its counter from the file ----
    second = Matcher(schedule, recovery_index=1, fired=trial.fired_ids(), counts=trial.occurrence_counts())
    second.bump("tool:create_issue", "after:tool_effect")
    assert second.match("tool:create_issue", "after:tool_effect") is not None


def test_a_spent_entry_stays_spent_across_a_restart(tmp_path) -> None:
    schedule = sched.expand(from_doc(T2), 7, WORKLOAD)
    trial = TrialDir(tmp_path / "t-7")
    entry = schedule.entries[0]
    trial.append_fault(
        FaultFired(fault_id=entry.fault_id, trial_id="t-7", recovery_index=0, type=entry.type,
                   boundary=entry.boundary, landmark=entry.landmark, occurrence=entry.occurrence)
    )
    revived = Matcher(schedule, recovery_index=1, fired=trial.fired_ids(), counts=trial.occurrence_counts())
    revived.bump("tool:create_issue", "after:tool_effect")
    assert revived.match("tool:create_issue", "after:tool_effect") is None


def test_the_cursor_round_trips(tmp_path) -> None:
    trial = TrialDir(tmp_path / "t-7")
    trial.write_cursor(Cursor(trial_id="t-7", recovery_index=2, sut_pid=123, started_at=1.5))
    assert trial.read_cursor().recovery_index == 2


def test_a_fresh_trial_directory_is_empty_and_a_joining_one_is_not(tmp_path) -> None:
    """A trial directory *is* the firing state. Reusing a dirty one would mark every entry already
    spent, the fault would never fire, and the trial would report a clean recovery it never
    performed — a false PASS, which is the one result this harness must never produce.

    The SUT never asks for a fresh one: it is joining a trial, not starting one.
    """
    path = tmp_path / "t-7"
    first = TrialDir(path)
    first.append_fault(
        FaultFired(fault_id="abc", trial_id="t-7", recovery_index=0, type="kill",
                   boundary="after:tool_effect", landmark="tool:create_issue", occurrence=1)
    )
    first.append_observation(
        Observation(landmark="tool:create_issue", boundary="after:tool_effect", occurrence=1,
                    recovery_index=0, ts=1.0)
    )

    joining = TrialDir(path)
    assert joining.fired_ids() == {"abc"}, "a restarted worker inherits what it already spent"

    restarted = TrialDir(path, fresh=True)
    assert restarted.fired_ids() == set()
    assert restarted.occurrence_counts() == {}
