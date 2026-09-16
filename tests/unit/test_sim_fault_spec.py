"""`sim.to_fault_spec` — a shrunk KeelMachine example becomes a spec Crashproof loads (§12.8)."""

from __future__ import annotations

import pytest

from crashproof.faults import spec
from tests.property.sim import Inexpressible, to_fault_spec

TOOLS = [{"name": "t0", "cls": "IDEMPOTENT", "resolution": "escalate", "dedup": True, "gated": False, "timeout": 1.0}]
SCRIPT = [{"op": "tool", "tool": "t0", "gated": False}]


def _example(*rules: dict) -> dict:
    return {"id": "rtest", "tools": TOOLS, "script": SCRIPT, "rules": list(rules)}


def test_a_black_box_sequence_round_trips_as_a_shim_spec(tmp_path) -> None:
    path = to_fault_spec(
        _example(
            {"rule": "crash_at_boundary", "boundary": "during:effect_exec", "landmark": "tool:t0", "occurrence": 1},
            {"rule": "timeout", "landmark": "tool:t0", "tool": True, "occurrence": 2},
            {"rule": "lease_expiry", "landmark": "tool:t0", "tool": True, "occurrence": 3},
            {"rule": "zombie_resume"},
            {"rule": "deliver_signal", "kind": "approve", "which": "open"},
        ),
        tmp_path,
    )
    assert path == tmp_path / "rtest.yaml"
    loaded = spec.load(path)
    assert loaded.mode == "shim"
    assert [(f.type, f.trigger.boundary, f.trigger.landmark, f.trigger.occurrence) for f in loaded.faults] == [
        ("kill", "after:tool_effect", "tool:t0", 1),
        ("tool_timeout", "before:tool_call", "tool:t0", 2),
        ("pause_past_ttl", "before:tool_call", "tool:t0", 3),
        ("approval_delay", "supervisor", "approval:*", 1),
    ]
    assert loaded.workload == "keel_sim" and loaded.workload_variant
    assert "# rtest" in path.read_text(encoding="utf8"), "the rules travel with the spec, as comments"


def test_one_hook_only_entry_makes_the_whole_spec_hook_mode(tmp_path) -> None:
    loaded = spec.load(to_fault_spec(
        _example(
            {"rule": "crash_at_boundary", "boundary": "before:effect_exec", "landmark": "tool:t0", "occurrence": 1},
            {"rule": "journal_fault", "boundary": "before:outcome_commit", "landmark": "tool:t0", "occurrence": 2},
        ),
        tmp_path,
    ))
    assert loaded.mode == "hook"
    assert [(f.type, f.trigger.boundary) for f in loaded.faults] == [
        ("kill", "before:effect_exec"), ("journal_unavailable", "before:outcome_commit"),
    ]


def test_what_no_mode_can_express_is_refused_by_name(tmp_path) -> None:
    # §12.7's own minimum needs `tool_duplicate_response`, which spec.py builds in no mode (§11.5).
    with pytest.raises(spec.CrashproofSpecError, match="tool_duplicate_response"):
        to_fault_spec(_example({"rule": "timeout", "landmark": "tool:t0", "tool": True, "occurrence": 1},
                               {"rule": "duplicate_response", "landmark": "tool:t0", "occurrence": 1}), tmp_path)
    # A mid-effect kill has no hook form, so it cannot share a spec with a journal fault.
    with pytest.raises(Inexpressible, match="hook"):
        to_fault_spec(_example(
            {"rule": "journal_fault", "boundary": "before:attempt_commit", "landmark": "tool:t0", "occurrence": 1},
            {"rule": "crash_at_boundary", "boundary": "during:effect_exec", "landmark": "tool:t0", "occurrence": 1},
        ), tmp_path)
    # A cancel is not a fault type anywhere (§14.3: no tier-1 cell issues one).
    with pytest.raises(Inexpressible, match="cancel"):
        to_fault_spec(_example({"rule": "deliver_signal", "kind": "cancel", "which": "none"}), tmp_path)
    assert not list(tmp_path.iterdir()), "nothing is written for a refused sequence"
