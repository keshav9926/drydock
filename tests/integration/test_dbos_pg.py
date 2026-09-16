"""The DBOS arm's program against a real Postgres, in-process (§13.4).

One W1 workflow per `agent_code`, run end to end through DBOS's own start, step checkpoints and
introspection — no subprocess, no shim, no fault. What it pins is the part a unit test cannot: that
the adapter's template is a DBOS system database a `DBOSClient` can read, that a finished run's steps
name the World label the adapter reports as committed, and that the F1 key really is
`workflow_id:step_id`.

    docker compose up -d postgres
    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")


@pytest.mark.parametrize("agent_code", ["native", "pydantic_ai"])
async def test_one_w1_workflow_runs_end_to_end(tmp_path: Path, monkeypatch, agent_code: str) -> None:
    pytest.importorskip("dbos")
    from dbos import DBOS, SetWorkflowID

    from crashproof.adapters.base import SutHandle
    from crashproof.adapters.dbos import BUILDERS, DBOSAdapter, workflow_id_for
    from crashproof.workloads.spec import load_named
    from crashproof.world.client import WorldClient
    from crashproof.world.server import WorldServer
    from crashproof.world.services import world_from_endpoints

    monkeypatch.setenv("KEEL_DSN", DSN)
    workload = load_named("tool_chain_1_effect")
    world = world_from_endpoints(workload.endpoint_decls())
    server = WorldServer(world, port=0)
    await server.start()
    trial_dir = tmp_path / f"t-{agent_code}"
    (trial_dir / "sut").mkdir(parents=True)
    adapter = DBOSAdapter(workload, "IDEMPOTENT", agent_code=agent_code)
    handle = SutHandle(trial_dir=trial_dir, dependency=None, world_url=server.base_url)  # type: ignore[arg-type]
    try:
        handle.dependency = await adapter.start_dependency(handle)
        DBOS(config={"name": "crashproof", "system_database_url": handle.dependency.dsn, "run_admin_server": False})
        workflow = BUILDERS[agent_code](workload, "IDEMPOTENT", WorldClient(server.base_url), None)
        DBOS.launch()
        with SetWorkflowID(workflow_id_for(trial_dir)):
            wf = await DBOS.start_workflow_async(workflow, workload.input)
        assert (await wf.get_result())["answer"].startswith("Created issue ")

        result = await adapter.collect(handle)
        assert result.status == "COMPLETED"
        assert result.committed_effects == {"issues.upsert#1"}
        assert world.applied_counts() == {"issues.upsert#1": 1}
        # The key the IDEMPOTENT tool presented is DBOS's own step identity, and PURE sent none.
        keys = {r.endpoint: r.effect_key for r in world.receipts}
        assert keys["kv.search"] is None
        assert keys["issues.upsert"].startswith(f"{workflow_id_for(trial_dir)}:")
    finally:
        # DBOS.destroy shuts the loop's default executor down, which psycopg's async connect needs,
        # so the database goes first.
        await adapter.stop_dependency(handle)
        await server.stop()
        DBOS.destroy(destroy_registry=True)
