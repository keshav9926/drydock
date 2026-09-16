"""One W1 trial through the Restate arm, against a real `restate-server` (§22.3).

Not in the default suite: it needs Linux (restate-sdk has no Windows wheel), the restate-server binary
and a few seconds of server per trial.

    CRASHPROOF_RESTATE_TESTS=1 uv run pytest tests/integration/test_restate_arm.py -q

The binary is `$CRASHPROOF_RESTATE_BIN`, `restate-server` on PATH, or `~/.restate-bin/restate-server`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRASHPROOF_RESTATE_TESTS") != "1", reason="set CRASHPROOF_RESTATE_TESTS=1 to run the Restate arm"
)


@pytest.mark.parametrize("variant", ["EXTERNAL", "IDEMPOTENT"])
async def test_one_invocation_end_to_end(tmp_path: Path, variant: str) -> None:
    pytest.importorskip("restate")
    pytest.importorskip("pydantic_ai")
    from crashproof.adapters.restate import RestateAdapter, restate_bin
    from crashproof.faults.spec import from_doc
    from crashproof.runner.trial import run_trial
    from crashproof.workloads.spec import load_named

    if not Path(restate_bin()).exists():
        pytest.skip(f"no restate-server at {restate_bin()}")
    workload = load_named("tool_chain_1_effect")
    spec = from_doc({"name": "baseline", "workload": workload.workload, "workload_variant": variant, "faults": []})
    row = await run_trial(
        adapter=RestateAdapter(workload, variant), workload=workload, variant=variant, spec=spec, seed=7,
        out_dir=tmp_path,
    )
    label = workload.variant(variant).required_effects[0]
    assert row.status == "COMPLETED", row.result
    assert row.metrics["raw"]["world_applied"] == {label: 1}
    # Restate's own journal says the effect's run completed; it documents no replayer, so C1 is N/A.
    assert row.metrics["raw"]["sut_committed"] == [label]
    assert row.verdicts["S1"] == row.verdicts["S2"] == row.verdicts["L1"] == "PASS"
    assert row.verdicts["C1"] == "N/A"
    assert row.key_source == workload.variant(variant).key_source
    assert row.config_pin["extra"]["platform"].startswith("linux")
