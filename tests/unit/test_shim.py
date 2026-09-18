"""The firing order, which is the whole reliability argument (§11.7).

    1. observe — append the row, fsync, then count it
    2. match   — against live entries
    3. record  — append the fault row, fsync
    4. execute — os._exit, freeze

Step 3 before step 4 is what makes "each entry fires at most once per trial" true across a kill: if
the process dies inside step 4 the row is already durable. If the order were 4-then-3 a killed
worker would leave no record, the restarted one would fire the same entry again, and a one-fault
cell would quietly become a crash-loop.

The kill is monkeypatched here for the obvious reason. The real thing is exercised by every trial.
"""

from __future__ import annotations

import pytest

from crashproof.faults import process
from crashproof.faults.injectors.base import Injector
from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import expand
from crashproof.faults.spec import from_doc

SPEC = {
    "name": "t2",
    "workload": "tool_chain_1_effect",
    "mode": "shim",
    "max_recoveries": 3,
    "faults": [
        {
            "id": "f1",
            "type": "kill",
            "trigger": {"boundary": "after:tool_effect", "landmark": "tool:create_issue"},
        }
    ],
}


@pytest.fixture
def killed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(process, "die_now", lambda: calls.append("kill"))
    monkeypatch.setattr(process, "freeze_self", lambda marker=None: calls.append("freeze"))
    return calls


def _injector(tmp_path, spec_doc=None, recovery_index=0) -> Injector:
    spec = from_doc(spec_doc or SPEC)
    trial = TrialDir(tmp_path / "t-7")
    return Injector(
        trial, expand(spec, 7), trial_id="t-7", recovery_index=recovery_index,
        sut_ref=lambda: {"run_id": "r1", "seq": 14},
    )


def test_the_fault_row_is_durable_before_the_fault_happens(tmp_path, killed) -> None:
    inj = _injector(tmp_path)
    inj.at("tool:create_issue", "after:tool_effect")

    assert killed == ["kill"], "the fault ran"
    [row] = inj.trial.faults()
    assert row.fault_id and row.type == "kill" and row.recovery_index == 0
    assert row.trigger_observed_at > 0 and row.sut_ref == {"run_id": "r1", "seq": 14}
    assert inj.trial.faults_path.exists(), "and its record outlives the process it killed"


def test_an_observation_is_recorded_even_when_nothing_fires(tmp_path, killed) -> None:
    """The counter has to survive the kill that is coming, so every observation is durable — not
    only the ones that matched."""
    inj = _injector(tmp_path)
    inj.at("tool:search", "before:tool_call")
    assert killed == []
    assert [(o.landmark, o.boundary) for o in inj.trial.observations()] == [
        ("tool:search", "before:tool_call")
    ]
    assert inj.trial.faults() == []


def test_a_restarted_injector_does_not_refire_a_spent_entry(tmp_path, killed) -> None:
    """The reason firing state lives in the directory: the process that spent it is gone."""
    first = _injector(tmp_path)
    first.at("tool:create_issue", "after:tool_effect")
    assert killed == ["kill"]

    second = Injector(
        TrialDir(tmp_path / "t-7"),
        expand(from_doc(SPEC), 7),
        trial_id="t-7",
        recovery_index=1,
    )
    second.at("tool:create_issue", "after:tool_effect")
    assert killed == ["kill"], "one entry, one firing, across a restart"
    assert len(second.trial.faults()) == 1


def test_an_entry_aimed_at_a_later_incarnation_waits_for_it(tmp_path, killed) -> None:
    """`occurrence` counts across the whole trial, restarts included, and `recovery_index` narrows
    which incarnation may fire. So "the re-issue after the restart" is occurrence 2 in incarnation
    1 — and that pair is precisely how a fault is aimed at a runtime that re-executes, since a
    memoizing one never reaches a second occurrence at all."""
    doc = {
        **SPEC,
        "faults": [
            {
                **SPEC["faults"][0],
                "trigger": {
                    "boundary": "after:tool_effect",
                    "landmark": "tool:create_issue",
                    "occurrence": 2,
                    "recovery_index": 1,
                },
            }
        ],
    }
    first = _injector(tmp_path, doc, recovery_index=0)
    first.at("tool:create_issue", "after:tool_effect")
    assert killed == [], "the first observation, in the wrong incarnation"

    second = _injector(tmp_path, doc, recovery_index=1)  # rebuilds its state from the directory
    second.at("tool:create_issue", "after:tool_effect")
    assert killed == ["kill"], "the second one, addressed by construction"


def test_a_freeze_is_a_freeze_and_not_an_exit(tmp_path, killed) -> None:
    doc = {**SPEC, "faults": [{**SPEC["faults"][0], "type": "pause_past_ttl"}]}
    inj = _injector(tmp_path, doc)
    inj.at("tool:create_issue", "after:tool_effect")
    assert killed == ["freeze"], "the process stays alive; that is the entire point of the cell"
    assert inj.trial.faults()[0].type == "pause_past_ttl", "and the row is what asks to be frozen"


def test_tokens_are_counted_by_one_function_for_every_arm() -> None:
    """Each arm sends its own prompt; the counting must not be its own too.

    `extra_tokens` is meant to show how much a runtime re-sends after a recovery. That is a
    property of the framework's prompt, so the payload is the framework's — but if Keel were
    counted by its provider's `count_tokens` and LangGraph by nothing at all, the column would be a
    statement about instrumentation rather than about either runtime (§14.3).
    """
    from crashproof.faults.injectors.shim import ToolShim

    assert ToolShim.count_tokens(None) is None
    # Same content, different key order: the dump is canonical, so the count is the same.
    assert ToolShim.count_tokens({"a": 1, "b": 2}) == ToolShim.count_tokens({"b": 2, "a": 1})
    # A bigger prompt costs more, which is the only monotonicity the column relies on.
    assert ToolShim.count_tokens({"messages": ["x" * 400]}) > ToolShim.count_tokens({"messages": []})


def test_a_provider_outage_fails_its_consecutive_calls_across_a_restart(tmp_path, killed) -> None:
    """§11.5 `provider_outage`: one fault row, then `consecutive` model calls fail in a row. The
    count lives in the trial directory, so a worker restarted mid-outage is still inside it."""
    from crashproof.faults.injectors.base import FaultResponse

    doc = {
        "name": "outage", "workload": "tool_chain_1_effect", "mode": "shim", "max_recoveries": 3,
        "faults": [{"id": "o1", "type": "provider_outage", "params": {"consecutive": 3},
                    "trigger": {"boundary": "before:model_call", "landmark": "model:start"}}],
    }
    first = _injector(tmp_path, doc)
    for _ in range(2):
        with pytest.raises(FaultResponse):
            first.at("model:start", "before:model_call")
    restarted = _injector(tmp_path, doc, recovery_index=1)
    with pytest.raises(FaultResponse):
        restarted.at("model:start", "before:model_call")
    restarted.at("model:start", "before:model_call")  # the provider is back
    assert [r.type for r in restarted.trial.faults()] == ["provider_outage"], "one row, three failures"
    assert killed == []


# --- a streamed model call (§11.2, §11.5 `model_stream_truncate`) --------------------------------
def _stream_spec(fault_type: str, chunk: int = 3, mode: str = "shim") -> dict:
    return {
        "name": "stream", "workload": "tool_chain_1_effect", "mode": mode, "max_recoveries": 3,
        "faults": [{"id": "s1", "type": fault_type,
                    "trigger": {"boundary": f"during:model_stream(chunk={chunk})", "landmark": "model:*"}}],
    }


def test_model_stream_truncate_is_a_shim_fault_at_a_numbered_chunk_and_never_a_proxy_one() -> None:
    from crashproof.faults.spec import CrashproofSpecError

    assert from_doc(_stream_spec("model_stream_truncate")).faults[0].trigger.boundary == "during:model_stream(chunk=3)"
    with pytest.raises(CrashproofSpecError, match="model traffic does not cross the proxy"):
        from_doc(_stream_spec("model_stream_truncate", mode="proxy"))
    with pytest.raises(CrashproofSpecError, match="model traffic does not cross the proxy"):
        from_doc(_stream_spec("kill", mode="proxy"))
    with pytest.raises(CrashproofSpecError):  # truncation is a stream's fault, not a call's
        from_doc({**_stream_spec("model_stream_truncate"), "faults": [
            {"id": "s1", "type": "model_stream_truncate",
             "trigger": {"boundary": "before:model_call", "landmark": "model:*"}}]})


async def _drain(tmp_path, doc: dict, pieces: int = 5) -> tuple[list, list]:
    from crashproof.faults.injectors.shim import ToolShim
    from crashproof.world.client import WorldClient

    shim = ToolShim(TrialDir(tmp_path / "t-7"), expand(from_doc(doc), 7), trial_id="t-7",
                    world=WorldClient("http://127.0.0.1:9"))
    got = [item async for item in shim.model_stream(
        "start", lambda: "RESPONSE", lambda r: [f"p{i}" for i in range(1, pieces + 1)], prompt={"m": 1})]
    return got, [o.boundary for o in shim.trial.observations()]


async def test_a_truncated_stream_delivers_k_pieces_and_no_response(tmp_path, killed) -> None:
    got, seen = await _drain(tmp_path, _stream_spec("model_stream_truncate"))
    assert got == ["p1", "p2", "p3"], "k pieces written, then the stream is cut — no final response"
    assert seen == ["before:model_call", *(f"during:model_stream(chunk={k})" for k in (1, 2, 3))]
    assert killed == []


async def test_an_unfaulted_stream_ends_with_the_whole_response(tmp_path, killed) -> None:
    got, seen = await _drain(tmp_path, _stream_spec("kill", chunk=9))
    assert got == ["p1", "p2", "p3", "p4", "p5", "RESPONSE"]
    assert seen[0] == "before:model_call" and seen[-1] == "after:model_return" and len(seen) == 7


async def test_a_kill_mid_stream_lands_after_the_kth_piece_was_taken(tmp_path, killed) -> None:
    got, _ = await _drain(tmp_path, _stream_spec("kill", chunk=2))
    assert killed == ["kill"] and got[:2] == ["p1", "p2"], "the runtime had taken piece 2 when it died"
