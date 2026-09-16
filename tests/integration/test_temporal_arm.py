"""One W1 trial through the Temporal arm, against a real `temporal server start-dev` (§22.3).

Not in the default suite: it needs the Temporal CLI binary and a few seconds of dev server per trial.

    CRASHPROOF_TEMPORAL_TESTS=1 uv run pytest tests/integration/test_temporal_arm.py -q

The binary is `$CRASHPROOF_TEMPORAL_BIN`, `temporal` on PATH, or `~/.temporalio/bin/temporal`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRASHPROOF_TEMPORAL_TESTS") != "1", reason="set CRASHPROOF_TEMPORAL_TESTS=1 to run the Temporal arm"
)


@pytest.mark.parametrize("variant", ["EXTERNAL", "IDEMPOTENT"])
async def test_one_workflow_end_to_end(tmp_path: Path, variant: str) -> None:
    pytest.importorskip("temporalio")
    pytest.importorskip("pydantic_ai")
    from crashproof.adapters.temporal import TemporalAdapter, temporal_bin
    from crashproof.faults.spec import from_doc
    from crashproof.runner.trial import run_trial
    from crashproof.workloads.spec import load_named

    if not Path(temporal_bin()).exists():
        pytest.skip(f"no Temporal CLI at {temporal_bin()}")
    workload = load_named("tool_chain_1_effect")
    spec = from_doc({"name": "baseline", "workload": workload.workload, "workload_variant": variant, "faults": []})
    row = await run_trial(
        adapter=TemporalAdapter(workload, variant), workload=workload, variant=variant, spec=spec, seed=7,
        out_dir=tmp_path,
    )
    label = workload.variant(variant).required_effects[0]
    assert row.status == "COMPLETED", row.result
    assert row.metrics["raw"]["world_applied"] == {label: 1}
    # Temporal's own history says the effect's activity completed, and its Replayer reproduces it.
    assert row.metrics["raw"]["sut_committed"] == [label]
    assert row.verdicts["S2"] == row.verdicts["C1"] == row.verdicts["L1"] == "PASS"
    assert row.key_source == workload.variant(variant).key_source
