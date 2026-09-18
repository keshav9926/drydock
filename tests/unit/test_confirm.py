"""The confirmation tier's selection and its plan (§15.3).

What must hold: safety never selects anything; a binary estimate that is not unanimous does, and
takes Keel's cell at the same (variant, location, fault) with it; a continuous or count metric
selects only under a claim `compare()` itself makes; every confirmed fault cell brings its baseline;
and the plan names the spec file, the host and the exact `bench` command, on seeds no screening row
can have.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from crashproof.report.confirm import plan, select
from crashproof.runner.bench import Matrix

SEEDS = range(7, 37)


def row(cell: str, seed: int, spec_hash: str = "h", **metrics) -> dict:
    base = dict(recovery_rate=1, logical_correctness=1, replay_divergence=0, duplicate_effects=0,
                duplicate_receipts=0, missing_required=0, recovery_latency_ms=2000.0, extra_model_calls=0,
                extra_tokens=0, wall_clock_overhead_ms=0.0, wait_durability=None)
    return {
        "workload": "tool_chain_1_effect", "workload_variant": cell.split(".")[2], "cell_id": cell,
        "spec_hash": spec_hash, "seed": seed, "valid": True, "wall_ms": 2000.0, "recovery_mechanism": "self",
        "verdicts": {"S1": "PASS"}, "metrics": {**base, **metrics},
    }


def cell(name: str, **metrics) -> list[dict]:
    return [row(name, s, **metrics) for s in SEEDS]


KEEL = "keel.default.EXTERNAL.after:tool_effect"
DBOS = "dbos.native.EXTERNAL.after:tool_effect"


def test_a_non_unanimous_binary_cell_is_confirmed_with_keels_twin_and_their_baselines() -> None:
    rows = (
        cell(KEEL) + cell("keel.default.EXTERNAL.baseline") + cell("dbos.native.EXTERNAL.baseline")
        + [row(DBOS, s, recovery_rate=0 if s < 9 else 1) for s in SEEDS]
        + cell("dbos.native.EXTERNAL.before:tool_call") + cell("keel.default.EXTERNAL.before:tool_call")
    )
    picks = select(rows, [])
    assert set(picks) == {DBOS, KEEL, "dbos.native.EXTERNAL.baseline", "keel.default.EXTERNAL.baseline"}
    assert picks[DBOS] == ["recovery_rate 28/30 at screening: not unanimous"]
    assert "Keel's arm" in picks[KEEL][0] and picks["keel.default.EXTERNAL.baseline"][0].startswith("τ₀")


def test_safety_and_an_unclaimed_estimate_select_nothing() -> None:
    """A duplicate is a FAIL with a counterexample, not an interval to tighten; a latency gap
    compare() calls too noisy is not a claim."""
    rows = cell(KEEL) + [
        {**row(DBOS, s, duplicate_effects=1, recovery_latency_ms=2000.0 + (s % 3 - 1) * 50), "verdicts": {"S1": "FAIL"}}
        for s in SEEDS
    ]
    assert select(rows, [("keel.*", "dbos.*")]) == {}


def test_a_claimed_difference_confirms_both_arms_of_it() -> None:
    rows = cell(KEEL) + cell(DBOS, extra_model_calls=2) + cell("keel.default.EXTERNAL.baseline")
    assert select(rows, []) == {}, "unanimous and unclaimed: nothing"
    picks = select(rows, [("keel.*", "dbos.*")])
    assert set(picks) == {KEEL, DBOS, "keel.default.EXTERNAL.baseline"}
    assert any("claimed: `keel.*` vs `dbos.*` on extra_model_calls — B higher" in w for w in picks[DBOS])


def test_the_plan_names_the_spec_the_host_and_the_command_on_fresh_seeds(tmp_path) -> None:
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "m.yaml").write_text(yaml.safe_dump({
        "workload": "tool_chain_1_effect", "mode": "shim", "seeds": {"count": 30, "base": 7},
        "variants": [{"id": "EXTERNAL"}], "triggers": ["after:tool_effect"],
        "adapters": [{"name": "keel", "configs": [{"id": "default"}]},
                     {"name": "restate", "configs": [{"id": "pydantic_ai"}]}],
    }), encoding="utf8")
    hashes = {c.id: c.spec.spec_hash for c in Matrix.load(specs / "m.yaml").cells()}
    restate = "restate.pydantic_ai.EXTERNAL.after:tool_effect"
    rows = [row(c, s, hashes[c], **({"recovery_rate": s % 2} if c == restate else {}))
            for c in hashes for s in SEEDS]
    doc = plan([("bench/results/x/results.jsonl", rows)], [], specs=specs)

    assert doc["confirmation"]["seed_range"] == [100_000, 100_299]
    [source] = doc["sources"]
    assert {c["cell"] for c in source["confirm"]} == set(hashes), "both arms and both baselines"
    assert all(c["spec"] == (specs / "m.yaml").as_posix() for c in source["confirm"])
    by_host = {c["host"]: c for c in source["commands"]}
    assert by_host["wsl"]["command"] == (
        f"uv run crashproof bench --matrix {(specs / 'm.yaml').as_posix()} "
        "--cells 'restate.pydantic_ai.EXTERNAL.after:tool_effect' --cells 'restate.pydantic_ai.EXTERNAL.baseline' "
        "--seeds 300 --base-seed 100000 --out bench/results/x_confirm_wsl"
    )
    assert doc["total"] == {"cells": 4, "trials": 1200, "estimate_hours": round(4 * 300 * 5.0 / 3600, 1)}


def test_confirm_refuses_a_base_seed_the_tier_rule_would_read_as_screening(tmp_path) -> None:
    from typer.testing import CliRunner

    from crashproof.cli.main import app

    results = tmp_path / "results.jsonl"
    results.write_text("", encoding="utf8")
    out = CliRunner().invoke(app, ["confirm", str(results), "--base-seed", "37", "--out", str(tmp_path / "p.yaml")])
    assert out.exit_code == 2 and not Path(tmp_path / "p.yaml").exists()
