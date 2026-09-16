"""The day-7 demo, line by line (§26.3, §28.7).

§28.7 names the risk in one phrase: *a demo that only works on the author's machine*. The
mitigation it names is this test — CI runs the demo on every commit and diffs the printed lines.

It runs against two recorded trials rather than against a live database, and that is the stronger
form rather than the cheaper one. The narration is a pure function of `(row, facts)`, so a fixture
pair pins exactly what a reader would see; and because the fixtures are real trial artefacts — one
Keel run that crashed at `after:tool_effect` and recovered, one LangGraph run that did the same
cell — a change to the narration shows up as a diff of the *script*, not as a database error.

Everything that legitimately varies between two runs of the same command is canonicalised away:
ids, hashes, ports, pids, timestamps, elapsed times, paths. What is left is the behaviour, which
is the only thing a golden file should be able to break on.

To accept a deliberate change: `UPDATE_GOLDEN=1 uv run pytest tests/unit/test_demo.py -q`, then
read the diff before committing it. The point of a golden file is that someone looks at it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from crashproof.demo import canonicalise, narrate
from crashproof.runner.trial import TrialRow
from crashproof.verifier import invariants

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "demo"
ARMS = ("keel", "langgraph")


def load(arm: str) -> tuple[TrialRow, invariants.TrialFacts]:
    where = GOLDEN / arm
    row = TrialRow(**json.loads((where / "result.json").read_text(encoding="utf8")))
    facts = invariants.load(json.loads((where / "facts.json").read_text(encoding="utf8")))
    return row, facts


@pytest.mark.parametrize("arm", ARMS)
def test_the_demo_prints_what_it_printed_last_time(arm: str) -> None:
    row, facts = load(arm)
    produced = "\n".join(narrate(row, facts, row_path="<results>", canonical=True)) + "\n"
    golden = GOLDEN / f"{arm}.txt"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_text(produced, encoding="utf8")
    assert golden.exists(), f"no golden for {arm}; run with UPDATE_GOLDEN=1 and read the result"
    assert produced == golden.read_text(encoding="utf8")


def test_the_two_arms_disagree_where_the_demo_says_they_do() -> None:
    """The contrast is the demo, so it is worth asserting rather than eyeballing.

    Same fault, same landmark, same World, same seed. One arm sends the request once and resolves
    the open step by asking the receiver; the other sends it twice. Neither has failed an invariant
    — the second declares `at_least_once` — and the difference is a count, printed.
    """
    keel_row, keel_facts = load("keel")
    lg_row, lg_facts = load("langgraph")

    assert keel_row.spec_hash == lg_row.spec_hash, "the same spec, or it is not a contrast"
    assert keel_row.seed == lg_row.seed

    target = keel_facts.required_effects[0]
    assert keel_facts.world_applied[target] == 1
    assert lg_facts.world_applied[target] == 2
    assert keel_row.metrics["duplicate_effects"] == 0
    assert lg_row.metrics["duplicate_effects"] == 1
    assert keel_row.recovery_mechanism == "self" and lg_row.recovery_mechanism == "harness"
    assert lg_row.verdicts["S1"] == "PASS", "at_least_once was declared; the duplicate is the cost"
    assert keel_facts.journal is not None and lg_facts.journal is None


def test_canonicalising_removes_the_weather_and_keeps_the_behaviour() -> None:
    """A golden file that breaks on a clock gets deleted; one that ignores a changed timeout
    proves nothing. Both halves are the test."""
    assert canonicalise("run 0192f8c1-0000-7000-8000-0000000000ab") == "run <uuid>"
    assert canonicalise("at 2026-09-13T07:02:11+00:00") == "at <ts>"
    assert canonicalise("keel worker pid 41822 on :8600") == "keel worker pid <pid> on :<port>"
    assert canonicalise("elapsed 41 ms") == "elapsed <ms> ms"
    assert canonicalise("keel_commit a212a20") == "keel_commit <sha>"
    assert canonicalise("keel_commit a212a20-dirty") == "keel_commit <sha>"
    assert canonicalise("key=8e3f31de50e8") == "key=<hash>"

    # Kept, and each for a reason: a config pin is identical on every run of the cell, so a change
    # to it is a change to the cell; a seq is the write-ahead protocol itself. Both must be able to
    # break the golden file, or it is not checking anything worth checking.
    for stable in ("lease_ttl 2.0 s > create_issue timeout 1.0 s", "seq 14", "replayed_steps=4"):
        assert canonicalise(stable) == stable


def test_the_approval_half_prints_the_park_it_read_and_nothing_it_did_not() -> None:
    """The line used to assert a released lease and a NULL runnable_at whenever an approval
    existed, without reading either — the scripted-screenshot failure the demo exists to prevent."""
    from crashproof.demo import _approval_lines

    def e(seq: int, kind: str, **body) -> dict:
        return {"seq": seq, "type": kind, "body": body}

    requested = e(15, "APPROVAL_REQUESTED", step_index=3, binds_effect_key="1860a3451aadfb25")
    parked = _approval_lines([requested, e(16, "RUN_WAITING", reason="approval")])
    assert "RUN_WAITING{approval} seq 16" in parked[1]
    assert not any("lease released" in line or "runnable_at" in line for line in parked)
    assert "no RUN_WAITING" in _approval_lines([requested])[1]
