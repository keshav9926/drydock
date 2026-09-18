"""§20.7's audit trail, as the SQL it is — against a real Postgres, with no worker running.

One gated effect is driven the ordinary way (a model turn decides, the Policy gates, a human
approves, a worker executes) and then every one of §20.7's six questions is asked of the tables
alone. S7's query is shown both ways: silent on a run the runtime kept honest, and returning the
violation it exists for — a gated effect that started with no approval at all — on a journal written
by hand, because the runtime will not write one.

    KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel uv run pytest tests/integration -q
"""

from __future__ import annotations

import contextlib
import os
from datetime import timedelta
from typing import Any

import pytest

from keel import EffectClass, Keel, program, tool
from keel.core.protocols import EffectClass as EC
from keel.events import StepAttemptStarted, StepIntended
from keel.journal.audit import audit_effect, s7_violations
from keel.journal.postgres import PostgresJournal
from keel.journal.protocol import EffectRow
from keel.providers.protocol import ModelResponse, Usage
from keel.runtime.policy import StaticPolicy

DSN = os.environ.get("KEEL_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set KEEL_TEST_DSN to run integration tests")

TTL = 2.0


class Decider:
    name = "fake"

    async def count_tokens(self, req: Any) -> int:
        return 1

    async def complete(self, req: Any) -> ModelResponse:
        return ModelResponse(text="ship it", usage=Usage(input_tokens=3, output_tokens=2),
                             provider_meta={"model": "fake-1", "model_version": "2026-09"})


@tool(effect=EffectClass.EXTERNAL, timeout=1.0, name="ship")
async def ship(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    return {"shipped": args["svc"], "external_ref": f"ship#{args['svc']}"}


@program(name="shipper", version="1.0")
async def shipper(ctx: Any, args: dict[str, Any]) -> Any:
    await ctx.model([{"role": "user", "content": "ship api?"}], name="decide")
    return await ctx.tool("ship", svc="api")


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
    yield j
    await j.close()


async def _work(k: Keel, worker_id: str) -> None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)


async def test_the_six_questions_are_answered_from_the_tables(journal: PostgresJournal) -> None:
    k = Keel(journal=journal, provider=Decider(), tools=[ship], programs=[shipper],
             policy=StaticPolicy(require_approval={"ship"}))
    handle = await k.start(shipper, {})
    await _work(k, "worker-a")
    view = await k.get(handle.run_id)
    assert view.phase == "WAITING_APPROVAL"
    [approval] = [a for a in (await k.events(handle.run_id)) if a.type == "APPROVAL_REQUESTED"]
    assert await k.approve(handle.run_id, approval.body.approval_id, by="keshav", client_key="click-1")
    await _work(k, "worker-b")

    [effect] = await journal.effects(handle.run_id)
    a = await audit_effect(journal, effect.effect_key)
    assert a is not None

    # Who decided it? The model turn before it, with the model that answered.
    assert (a["decided_by"]["kind"], a["decided_by"]["name"], a["decided_by"]["step_index"]) == ("MODEL", "decide", 0)
    assert a["decided_by"]["provider_meta"]["model_version"] == "2026-09"
    # Was it allowed? Gated by the Policy, and started.
    assert a["allowed"] == {"policy_verdict": "require_approval", "started": True, "refused": None}
    # Who approved it? The decision, and the inbox row it came from.
    [who] = a["approved_by"]
    assert (who["decision"], who["by"], who["client_key"], who["signal_type"]) == ("granted", "keshav", "click-1", "approve")
    # Which process, when, under which code?
    [attempt] = a["executed"]["attempts"]
    assert (attempt["worker_id"], attempt["lease_epoch"], attempt["outcome"]) == ("worker-b", 2, "STEP_COMPLETED")
    assert a["executed"]["program_version"] == shipper.version
    # Did it happen?
    assert a["happened"]["status"] == "COMMITTED" and a["happened"]["external_ref"] == "ship#api"
    # What did the model see?
    assert a["model_saw"]["messages"][0]["content"] == "ship api?"

    assert await s7_violations(journal) == [], "the runtime kept this run honest"
    assert await audit_effect(journal, "0" * 32) is None


async def test_s7_returns_a_gated_effect_that_started_with_no_approval(journal: PostgresJournal) -> None:
    """The violation §20.7 says matters most, written by hand: the runtime refuses to write it."""
    k = Keel(journal=journal, tools=[ship], programs=[shipper])
    handle = await k.start(shipper, {})
    lease = await journal.claim("forger", timedelta(seconds=TTL))
    key = "f" * 32
    async with journal.append(lease) as tx:
        now = await tx.now()
        seq = await tx.append(StepIntended(step_index=0, kind="TOOL", name="ship", args_hash="h", effect_key=key,
                                           effect_class="EXTERNAL", policy_verdict="require_approval"))
        await tx.write_effect(EffectRow(effect_key=key, run_id=handle.run_id, run_root_id=handle.run_id,
                                        step_index=0, tool="ship", effect_class=str(EC.EXTERNAL),
                                        status="INTENDED", intent_seq=seq))
        started = await tx.append(StepAttemptStarted(step_index=0, attempt_no=1, lease_epoch=lease.epoch, started_at=now))
        await tx.update_effect(key, status="STARTED", started_seq=started, attempt_no=1)

    [v] = await s7_violations(journal)
    assert (v["effect_key"], v["granted"], v["status"]) == (key, 0, "STARTED")
