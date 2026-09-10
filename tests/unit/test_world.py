"""The World is the instrument, so its ordering is tested before anything is measured with it.

The one that must never be cut (§28.2): the receipt is written and fsynced **before** the response
is computed. If it were not, `after:tool_effect` would be a guess and every cell built on it would
inherit the ambiguity — the harness would be measuring itself.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from crashproof.workloads.tool_chain_1_effect import WORKLOAD, build_world
from crashproof.world import oracle
from crashproof.world.client import WorldClient
from crashproof.world.server import WorldServer

ISSUE = {"title": "CI flake: test_retry", "body": "see search hits"}


@pytest.fixture
def world():
    return build_world()


@pytest.fixture
async def served(world):
    server = WorldServer(world, port=0)
    await server.start()
    try:
        yield WorldClient(server.base_url)
    finally:
        await server.stop()


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf8").splitlines() if x.strip()]


async def test_receipt_is_durable_before_the_response_is_computed(tmp_path: Path) -> None:
    log = tmp_path / "receipts.jsonl"
    world = build_world(log_path=log)
    world.hold("issues.create", 400)
    server = WorldServer(world, port=0)
    await server.start()
    client = WorldClient(server.base_url)
    try:
        call = asyncio.create_task(client.acall("issues.create", ISSUE))
        for _ in range(200):  # wait for the receipt, NOT for the answer
            if _lines(log):
                break
            await asyncio.sleep(0.005)
        assert not call.done(), "the response is still held; this is the crash window"
        [receipt] = _lines(log)
        assert receipt["endpoint"] == "issues.create"
        assert receipt["logical_identity"] == "issues.create#1"
        assert world.applied_counts() == {"issues.create#1": 1}, "applied before the caller heard"
        assert (await call)["external_ref"] == "issues.create#1"
    finally:
        await server.stop()


def test_dedup_false_applies_every_request(world) -> None:
    world.receive("issues.create", ISSUE)
    world.receive("issues.create", ISSUE)
    assert world.applied_counts()["issues.create#1"] == 2, "a receiver that honours nothing"
    assert world.receipt_counts()["issues.create#1"] == 2


def test_natural_dedup_applies_once_and_returns_the_identical_result(world) -> None:
    first = world.receive("issues.upsert", ISSUE, effect_key="k1")
    second = world.receive("issues.upsert", ISSUE, effect_key="k1")
    assert world.receipt_counts()["issues.upsert#1"] == 2
    assert world.applied_counts()["issues.upsert#1"] == 1
    # a duplicate re-fire must not perturb the caller's next request (§13.2)
    assert first == second


def test_key_dedup_applies_once_per_presented_key(world) -> None:
    world.set_dedup("issues.create", dedup=True, natural=False)
    world.receive("issues.create", ISSUE, effect_key="k1")
    world.receive("issues.create", ISSUE, effect_key="k1")
    assert world.applied_counts()["issues.create#1"] == 1
    world.receive("issues.create", ISSUE, effect_key="k2")
    assert world.applied_counts()["issues.create#1"] == 2, "a different key is a different effect"


def test_unkeyed_request_at_a_keyed_endpoint_applies_unconditionally(world) -> None:
    """§13.2, stated as a rule so F0 measures raw re-fire on every endpoint."""
    world.set_dedup("issues.create", dedup=True, natural=False)
    world.receive("issues.create", ISSUE)
    world.receive("issues.create", ISSUE)
    assert world.applied_counts()["issues.create#1"] == 2
    assert [r.effect_key for r in world.receipts] == [None, None]


def test_reads_are_receipted_but_never_applied(world) -> None:
    hits = world.receive("kv.search", {"q": "flaky test in ci"})
    world.receive("kv.search", {"q": "flaky test in ci"})
    assert hits["hits"]
    assert world.receipt_counts()["kv.search#1"] == 2
    assert world.applied_counts() == {}


def test_distinct_identities_get_distinct_landmarks(world) -> None:
    world.receive("issues.create", ISSUE)
    world.receive("issues.create", {**ISSUE, "title": "another"})
    assert sorted(world.applied_counts()) == ["issues.create#1", "issues.create#2"]


def test_probe_answers_by_identity_and_by_key(world) -> None:
    absent = oracle.probe(world, endpoint="issues.create", args=ISSUE)
    assert absent["verdict"] == "ABSENT" and absent["result"] is None

    world.receive("issues.create", ISSUE)
    by_identity = oracle.probe(world, endpoint="issues.create", args=ISSUE)
    assert by_identity["verdict"] == "COMMITTED"
    assert by_identity["result"]["title"] == ISSUE["title"]
    assert by_identity["external_ref"] == "issues.create#1"

    world.receive("issues.upsert", ISSUE, effect_key="k9")
    assert oracle.probe(world, effect_key="k9")["verdict"] == "COMMITTED"
    assert oracle.probe(world, effect_key="never-sent")["verdict"] == "ABSENT"


def test_probing_a_never_seen_identity_does_not_consume_a_landmark(world) -> None:
    """An occurrence number is a landmark — `required_effects` and fault triggers are written in
    them. Handing one to an identity that only ever got asked about would renumber the effect that
    really arrives, and a correct run would fail 'no phantom completion' for a question."""
    assert oracle.probe(world, endpoint="issues.create", args={"title": "ghost"})["verdict"] == "ABSENT"
    assert world.label_for("issues.create", {"title": "ghost"}) is None
    assert world.applied_counts() == {} and world.receipt_counts() == {}

    landed = world.receive("issues.create", ISSUE)
    assert landed["logical_identity"] == "issues.create#1", "the ghost took no number"


async def test_client_and_oracle_over_http(served: WorldClient) -> None:
    created = await served.acall("issues.create", ISSUE)
    assert created["logical_identity"] == "issues.create#1"
    assert await served.aapplied() == {"issues.create#1": 1}
    assert await served.areceipts() == {"issues.create#1": 1}
    assert (await served.aprobe("issues.create", ISSUE))["verdict"] == "COMMITTED"
    assert (await served.astate())["endpoints"]["issues.upsert"] == {
        "dedup": True, "natural": True, "kind": "write"
    }


async def test_idempotency_key_travels_over_http(served: WorldClient) -> None:
    key = "0123456789abcdef0123456789abcdef"
    await served.acall("issues.upsert", ISSUE, effect_key=key)
    await served.acall("issues.upsert", ISSUE, effect_key=key)
    assert (await served.areceipts())["issues.upsert#1"] == 2
    assert (await served.aapplied())["issues.upsert#1"] == 1
    assert [r["effect_key"] for r in (await served.astate())["log"]] == [key, key]


def test_the_workload_declares_both_bands() -> None:
    assert WORKLOAD.variant("EXTERNAL").key_source == "none"
    assert WORKLOAD.variant("IDEMPOTENT").key_source == "framework"
    endpoints = {e.id: e for e in WORKLOAD.world.endpoints}
    assert (endpoints["issues.create"].dedup, endpoints["issues.create"].natural) == (False, False)
    assert (endpoints["issues.upsert"].dedup, endpoints["issues.upsert"].natural) == (True, True)
    assert WORKLOAD.spec_hash and len(WORKLOAD.spec_hash) == 16
