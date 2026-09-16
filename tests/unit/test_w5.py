"""W5 `approval_gated_deploy`: the human in the loop, as a cell (§29.1, §13.7 H7).

Three pieces make a gated workload runnable against every arm, and each is pinned here:

    the vocabulary   `approval:` and `before_approval:` on a script node are runtime-neutral
                     statements about *when a human is asked* — and W5-pre is a separate workload,
                     not a variant, because a variant may never change the script
    the cell         `approval_delay`, `approval_expiry`, `kill_while_waiting` are supervisor
                     faults aimed at the `approval:*` landmark, and `approval_expiry` changes what
                     "correct" looks like — nothing deployed — on the spec, so it is hashed
    the human        the supervisor grants exactly once, honours the delay, never grants under
                     expiry but still records that a fault fired, and kills while parked

The last one is the part that was wrong twice on the first real run: an expiry cell was voided
because "the human never answered" wrote no fault row, and S3 read a run that correctly refused to
deploy as a phantom completion. Both are tests below now rather than surprises.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import pytest

from crashproof.faults.log import TrialDir
from crashproof.faults.schedule import expand
from crashproof.faults.spec import CrashproofSpecError, from_doc
from crashproof.faults.supervisor import Supervisor
from crashproof.runner.bench import Matrix
from crashproof.workloads.spec import load_named


# --- the vocabulary ---------------------------------------------------------------
def test_a_gated_node_is_a_landmark_and_the_variants_never_touch_the_script() -> None:
    w = load_named("approval_gated_deploy")
    gate = w.node_for(((("search", 1),)))
    assert gate is not None and gate.gated
    assert "approval:search1" in w.landmarks()
    assert w.expected_occurrences("approval:*") == 1
    assert w.gated_tools() == ("deploy_service",)
    assert w.input["expires_in"] == 5, "the deadline is the trial's, and it travels in the input"
    assert set(w.variants) == {"GATED"}, "one band; the tier-2 form is its own workload"


def test_the_tier_2_form_is_a_separate_workload_with_one_extra_call() -> None:
    """A variant overrides tools and the expected World state and never the script. The two forms
    differ in exactly the script — one ungated `notify` before the question — so the tier-2 form
    is `approval_gated_deploy_pre`, with its own spec hash and its own row."""
    head, pre = load_named("approval_gated_deploy"), load_named("approval_gated_deploy_pre")
    assert head.spec_hash != pre.spec_hash
    gate = pre.node_for(((("search", 1),)))
    assert [c["name"] for c in gate.all_tool_calls()] == ["notify", "deploy_service"]
    assert pre.expected_occurrences("tool:notify") == 1 and head.expected_occurrences("tool:notify") == 0
    assert pre.variant("GATED").required_effects == ("notify.send#1", "deploy.service#1")


# --- the cell ---------------------------------------------------------------------
def test_supervisor_faults_are_aimed_at_the_wait_and_carry_their_parameters() -> None:
    m = Matrix.load("bench/specs/w5.yaml")
    cells = {c.trigger: c for c in m.cells() if c.adapter == "keel"}
    w = load_named(m.workload)

    delay = expand(cells["approval_delay@supervisor"].spec, 7, w).entries
    assert [(e.boundary, e.landmark, e.params) for e in delay] == [
        ("supervisor", "approval:*", {"delay_ms": 500.0, "duplicate": True, "duplicate_gap_ms": 0})
    ]
    kill = expand(cells["kill@after:tool_effect"].spec, 7, w).entries
    assert kill[0].landmark == "tool:deploy_service", "the matrix's own landmark for the day-3 window"


def test_expiry_changes_what_correct_looks_like_and_the_spec_hash_says_so() -> None:
    """A human who never answers is a fault, and under it the gated effect must *not* happen. That
    is stated on the spec — so a cell that expects nothing deployed is a different cell from one
    that expects a deploy, and the hash says so."""
    m = Matrix.load("bench/specs/w5.yaml")
    cells = {c.trigger: c for c in m.cells() if c.adapter == "keel"}
    expiry, delay = cells["approval_expiry@supervisor"].spec, cells["approval_delay@supervisor"].spec
    assert expiry.expected_effects == ()
    assert expiry.expected_world_state == {"deploy.service#1": 0}, "the forbidden label, stated"
    assert delay.expected_effects is None, "every other cell defers to the workload's variant"
    assert expiry.spec_hash != delay.spec_hash


def test_the_supervisor_boundary_is_legal_in_shim_mode_and_a_misaimed_human_fault_is_not() -> None:
    ok = from_doc({
        "name": "w5", "workload": "approval_gated_deploy", "mode": "shim",
        "faults": [{"id": "f1", "type": "approval_delay",
                    "trigger": {"boundary": "supervisor", "landmark": "approval:*", "occurrence": 1}}],
    })
    assert ok.faults[0].trigger.boundary == "supervisor"
    with pytest.raises(CrashproofSpecError):
        from_doc({
            "name": "bad", "workload": "approval_gated_deploy", "mode": "shim",
            "faults": [{"id": "f1", "type": "approval_delay",
                        "trigger": {"boundary": "before:tool_call", "landmark": "tool:deploy_service",
                                    "occurrence": 1}}],
        })


# --- the human --------------------------------------------------------------------
class _Sut:
    """A process the supervisor can own and kill: it sleeps, and nothing else."""

    argv = [sys.executable, "-c", "import time; time.sleep(60)"]


def _supervisor(
    tmp_path, trigger: str, status: list[str], granted: list[float], *, duplicate: bool = False
) -> Supervisor:
    m = Matrix.load("bench/specs/w5.yaml")
    if not duplicate:
        m.approval_duplicate_gap_ms = None
    cell = next(c for c in m.cells() if c.adapter == "keel" and c.trigger == trigger)
    schedule = expand(cell.spec, 7, load_named(m.workload))
    trial = TrialDir(tmp_path / "t-7", fresh=True)
    schedule.write(trial.schedule_path)

    async def on_waiting() -> None:
        granted.append(time.time())

    async def status_fn() -> str:
        return status[0]

    return Supervisor(
        trial, schedule, trial_id="t-7", argv=_Sut.argv, env={},
        is_terminal=lambda: asyncio.sleep(0, result=False),
        status=status_fn, on_waiting=on_waiting,
    )


async def _drive(sup: Supervisor, ticks: int, gap: float = 0.0) -> None:
    for _ in range(ticks):
        await sup._play_the_human()
        if gap:
            await asyncio.sleep(gap)


async def test_the_human_grants_exactly_once(tmp_path) -> None:
    status, granted = ["WAITING"], []
    sup = _supervisor(tmp_path, "approval_delay@supervisor", status, granted)
    sup.result.started_at = time.time()
    sup._spawn(0)
    try:
        await _drive(sup, 8, gap=0.1)  # 0.8 s across the 500 ms delay
    finally:
        sup._stop_all()
    assert len(granted) == 1, "a human clicks once; needing it twice is the runtime's finding"
    rows = sup.trial.faults()
    assert [r.type for r in rows] == ["approval_delay"], "the delay fired, and is on record"


async def test_the_duplicate_click_is_sent_once_even_after_the_run_is_over(tmp_path) -> None:
    """§11.4 C: the same approve again, unkeyed. It is sent whatever the run did in the gap — a
    trial that ended first would not have offered the runtime the chance to grant twice — and the
    fault reads as executed only once the second click actually went out."""
    status, granted = ["WAITING"], []
    sup = _supervisor(tmp_path, "approval_delay@supervisor", status, granted, duplicate=True)
    sup._spawn(0)
    try:
        await _drive(sup, 8, gap=0.1)
        assert len(granted) == 2, "the click, and the duplicate"
        status[0] = "COMPLETED"
        await _drive(sup, 5, gap=0.05)
    finally:
        sup._stop_all()
    [row] = sup.trial.faults()
    assert row.params["duplicate"] is True and len(granted) == 2
    assert sup.executed_flags() == {row.fault_id: True}


async def test_the_human_waits_out_the_delay_before_granting(tmp_path) -> None:
    status, granted = ["WAITING"], []
    sup = _supervisor(tmp_path, "approval_delay@supervisor", status, granted)
    sup._spawn(0)
    try:
        t0 = time.time()
        await _drive(sup, 3, gap=0.05)  # 150 ms: well inside the 500 ms delay
        assert granted == [], "not yet"
        await _drive(sup, 6, gap=0.1)
        assert len(granted) == 1 and granted[0] - t0 >= 0.45
    finally:
        sup._stop_all()


async def test_under_expiry_the_human_never_answers_but_the_fault_is_on_record(tmp_path) -> None:
    """The bug the first real run found: with no fault row the trial is voided as "the schedule
    never fired", which is the opposite of what happened. A human who never answers is a fault
    that fired the moment the park was observed."""
    status, granted = ["WAITING"], []
    sup = _supervisor(tmp_path, "approval_expiry@supervisor", status, granted)
    sup._spawn(0)
    try:
        await _drive(sup, 5, gap=0.05)
    finally:
        sup._stop_all()
    assert granted == []
    assert [r.type for r in sup.trial.faults()] == ["approval_expiry"]
    assert sup.executed_flags() == {sup.trial.faults()[0].fault_id: True}


async def test_kill_while_waiting_ends_the_process_and_grants_to_whoever_comes_back(tmp_path) -> None:
    status, granted = ["WAITING"], []
    sup = _supervisor(tmp_path, "kill_while_waiting@supervisor", status, granted)
    sup._spawn(0)
    try:
        await sup._play_the_human()  # first observation of the park: the kill
        for _ in range(50):
            if sup._sut.poll() is not None:
                break
            await asyncio.sleep(0.05)
        assert sup._sut.poll() is not None, "the process holding the wait is gone"
        assert granted == [], "nobody has been granted yet; there is nobody to grant"
        sup._close_incarnation()
        sup.result.restarts += 1
        sup._spawn(1)  # the successor
        await sup._play_the_human()
        assert len(granted) == 1, "the grant goes to whoever came back"
    finally:
        sup._stop_all()
    [row] = sup.trial.faults()
    assert row.type == "kill_while_waiting" and row.recovery_index == 0
    assert sup.executed_flags()[row.fault_id] is True, "recorded *and* happened: not a void trial"


async def test_the_keel_arm_names_the_approval_it_decides_and_the_duplicate_names_it_again(
    tmp_path, monkeypatch
) -> None:
    """Keel's drain reads `payload.approval_id`: a named decision for an approval already decided is
    `SIGNAL_IGNORED{approval_terminal}`. So the human's click names the open approval, and §11.4 C's
    second click is the same row again, unkeyed — never a click on nothing in particular."""
    import contextlib
    from datetime import timedelta

    from crashproof.adapters.base import SutHandle
    from crashproof.adapters.keel import KeelAdapter
    from crashproof.workloads.tool_chain_1_effect import build_world
    from crashproof.world.server import WorldServer
    from keel import Keel
    from keel.agents import demo
    from keel.core.clock import FakeClock
    from keel.journal.memory import MemoryJournal
    from keel.providers.scripted import ScriptedProvider
    from keel.state.fold import fold

    server = WorldServer(build_world(), port=0)
    await server.start()
    monkeypatch.setattr(demo, "WORLD_URL", server.base_url)
    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), provider=ScriptedProvider(demo.SCRIPT),
             tools=[demo.search, demo.create_issue_tool("EXTERNAL")],
             programs=[demo.gated_tool_chain], clock=clock)
    try:
        run = await k.start(demo.gated_tool_chain, {"title": "gate me"})
        lease = await k.journal.claim("w1", timedelta(seconds=2.0))
        with contextlib.suppress(BaseException):
            await k.worker(worker_id="w1", lease_ttl=2.0).execute(lease)
        adapter = KeelAdapter(load_named("approval_gated_deploy"), "GATED")
        adapter._app = k
        handle = SutHandle(trial_dir=tmp_path, dependency=None, world_url=server.base_url, run_ref=str(run.run_id))
        assert await adapter.approve(handle) and await adapter.approve(handle)
        [approval_id] = fold(await k.events(run.run_id)).approvals
        rows = await k.journal.pending_signals(run.run_id)
    finally:
        await server.stop()
    assert [(r.type, r.payload, r.client_key) for r in rows] == [
        ("approve", {"by": "harness", "approval_id": str(approval_id)}, None)
    ] * 2


async def test_a_workload_that_never_parks_never_asks_the_human(tmp_path) -> None:
    status, granted = ["RUNNING"], []
    sup = _supervisor(tmp_path, "approval_delay@supervisor", status, granted)
    await _drive(sup, 5)
    assert granted == [] and sup.trial.faults() == []
