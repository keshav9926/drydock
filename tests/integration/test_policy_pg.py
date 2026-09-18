"""Policy against a real Postgres (§20.2, §20.3).

`tests/unit/test_policy.py` proves the verdicts on the MemoryJournal. These prove what only Postgres
can refuse: the Policy-inserted APPROVAL and its bound TOOL pass `events_intent_once` and
`events_approval_once` at adjacent indices, a denied call's DENIED effects row and its attempt-0
STEP_FAILED commit together, and a child's capability set round-trips through RUN_CREATED's payload.

    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import contextlib
import os
from datetime import timedelta
from typing import Any

import pytest

from keel import Keel
from keel.journal.postgres import PostgresJournal
from keel.replay.verify import verify
from keel.runtime.policy import StaticPolicy
from keel.state.fold import fold
from tests.unit.test_policy import CALLS, child, deploy, deployer, look, parent, quick, self_gated

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = 2.0


@pytest.fixture
async def journal():
    j = PostgresJournal(DSN)
    await j.migrate()
    pool = await j._ready()
    async with pool.connection() as conn:
        await conn.execute(
            "TRUNCATE artifacts, replays, recoveries, delegations, signals, effects, events,"
            " runs, blobs, programs RESTART IDENTITY CASCADE"
        )
    CALLS.clear()
    yield j
    await j.close()


def _keel(journal: PostgresJournal, policy: Any) -> Keel:
    return Keel(journal=journal, tools=[look, deploy, quick],
                programs=[deployer, self_gated, parent, child], policy=policy)


async def _work(k: Keel, worker_id: str) -> bool:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is None:
        return False
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
    return True


async def test_a_policy_gate_parks_then_runs_the_bound_call_once(journal: PostgresJournal) -> None:
    k = _keel(journal, StaticPolicy(require_approval={"deploy"}))
    handle = await k.start(deployer, {})
    await _work(k, "w1")
    row = await journal.run_row(handle.run_id)
    assert (row.phase, row.lease_expires_at, row.runnable_at) == ("WAITING_APPROVAL", None, None)

    [approval] = fold(await k.events(handle.run_id)).approvals.values()
    assert await k.approve(handle.run_id, approval.approval_id, by="keshav")
    await _work(k, "w2")

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED" and CALLS == ["look", "deploy"]
    verdicts = [(e.body.kind, e.body.policy_verdict) for e in events if e.type == "STEP_INTENDED"]
    assert verdicts == [("TOOL", "allow"), ("APPROVAL", "require_approval"), ("TOOL", "require_approval")]
    assert approval.binds_effect_key == state.steps[2].effect_key
    assert (await verify(journal, handle.run_id, deployer, tools=k.tools)).ok


async def test_a_deny_commits_the_refusal_and_a_denied_row(journal: PostgresJournal) -> None:
    k = _keel(journal, StaticPolicy(allowed_tools={"look"}))
    handle = await k.start(deployer, {})
    await _work(k, "w1")

    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED" and state.result["refused"].startswith("PolicyDenied")
    assert {r.tool: r.status for r in await journal.effects(handle.run_id)} == {"look": "COMMITTED", "deploy": "DENIED"}
    assert CALLS == ["look"]


async def test_a_child_is_held_to_its_contract(journal: PostgresJournal) -> None:
    k = _keel(journal, StaticPolicy(allowed_tools={"look"}))
    handle = await k.start(parent, {"grant": ["look"]})
    for _ in range(6):
        if not await _work(k, "w"):
            break
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED" and state.result["result"]["refused"].startswith("PolicyDenied")
    [kid] = await journal.children(handle.run_id)
    assert (await k.events(kid.run_id))[0].body.policy == {"allowed_tools": ["look"]}
    assert CALLS == []
