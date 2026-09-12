"""`model_reask_alternate`: the only black-box way to see replay divergence (§13.3, §28.5).

A runtime that re-asks a question whose answer it did not persist gets the node's declared
`alternate` decision and takes a different path. A runtime that memoized never re-asks, never sees
the alternate, and is invisible to this fault *by being correct* — which is the finding, not a gap.

The end-to-end proof is the `reask_alternate` cell. This file holds the fast parts: the pieces that
would fail silently and take the whole column with them.
"""

from __future__ import annotations

import pytest

from crashproof.faults.spec import CrashproofSpecError, from_doc
from crashproof.verifier.metrics import Metrics, compute
from crashproof.workloads.spec import Workload
from crashproof.workloads.tool_chain_1_effect import WORKLOAD, build_world

AFTER_EFFECT = {"boundary": "after:tool_effect", "landmark": "tool:create_issue"}
BEFORE_MODEL = {"boundary": "before:model_call", "landmark": "model:*", "recovery_index": 1}


def _spec(*faults):
    return from_doc({"name": "x", "workload": "w", "mode": "shim", "faults": list(faults)})


def test_a_modifier_alone_is_a_spec_error() -> None:
    """It fires only when a later incarnation re-asks. With nothing to cause that incarnation the
    trigger is unreachable — and the trial would score as though nothing went wrong, because
    nothing did."""
    with pytest.raises(CrashproofSpecError, match="modifier"):
        _spec({"id": "f1", "type": "model_reask_alternate", "trigger": BEFORE_MODEL})


def test_a_modifier_composed_with_a_kill_is_a_cell() -> None:
    spec = _spec(
        {"id": "f1", "type": "kill", "trigger": AFTER_EFFECT},
        {"id": "f2", "type": "model_reask_alternate", "trigger": BEFORE_MODEL},
    )
    assert [f.type for f in spec.faults] == ["kill", "model_reask_alternate"]


def test_the_provider_is_a_pure_function_of_content_and_the_flag() -> None:
    """No ask counter anywhere: a re-asked fingerprint is the *same* question, not the nth one.
    Two calls with the flag set give the same answer, or the cell would measure a counter."""
    node = WORKLOAD.node_for((("search", 1),))
    normal = Workload.decision_of(node)
    alternate = Workload.decision_of(node, alternate=True)

    assert normal["tool_calls"][0]["args"]["title"] != alternate["tool_calls"][0]["args"]["title"]
    assert Workload.decision_of(node, alternate=True) == alternate
    assert Workload.decision_of(node) == normal

    # A node with no declared alternate answers the same either way — the alternate is per node,
    # so arming the flag does not make every decision change.
    plain = WORKLOAD.node_for((("search", 1), ("create_issue", 1)))
    assert Workload.decision_of(plain, alternate=True) == Workload.decision_of(plain)


def test_identities_separate_doing_it_twice_from_doing_something_else() -> None:
    """A label is an ordinal: the second *different* issue is still `issues.create#2`, and the
    first one is `#1` whichever title arrived first. Divergence has to read the content."""
    w = build_world()
    w.receive("issues.create", {"title": "A", "body": "x"})
    w.receive("issues.create", {"title": "A", "body": "x"})
    w.receive("issues.create", {"title": "B", "body": "x"})

    assert w.applied_counts() == {"issues.create#1": 2, "issues.create#2": 1}
    assert w.applied_identities() == [
        ["issues.create", '["A"]', 2],
        ["issues.create", '["B"]', 1],
    ]


def _metrics(identities, baseline_identities):
    base = Metrics()
    base.raw = {"applied_order": baseline_identities, "model_calls": 3}
    return compute(
        world_applied={},
        world_receipts=[],
        sut_committed=None,
        required_effects=(),
        status="COMPLETED",
        expected_status="COMPLETED",
        expected_world_state={},
        faults=[],
        t_restarts=[],
        wall_ms=0,
        model_calls=3,
        tokens=None,
        storage_bytes=None,
        detect_ms=None,
        verdicts={},
        baseline=base,
        applied_identities=identities,
    )


def test_replay_divergence_sees_both_shapes_and_needs_a_baseline() -> None:
    clean = [["issues.create", '["A"]', 1]]
    assert _metrics(clean, clean).replay_divergence == 0
    # Did it again.
    assert _metrics([["issues.create", '["A"]', 2]], clean).replay_divergence == 1
    # Did something else — the shape `duplicate_effects` cannot see, because these are two
    # different issues and neither was applied twice.
    diverged = [["issues.create", '["A"]', 1], ["issues.create", '["B"]', 1]]
    m = _metrics(diverged, clean)
    assert m.replay_divergence == 1 and m.duplicate_effects == 0

    # Without a baseline there is nothing to have diverged from, and `0` would be a lie.
    assert _metrics(clean, None).replay_divergence is None
