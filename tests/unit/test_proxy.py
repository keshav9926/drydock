"""The proxy: the shim's three instants, one process further out (§11.2, §27.7).

A stand-in for the SUT — the one World client, pointed at the proxy — makes tool calls, and each
test asks the two questions a proxy cell asks: what did the World actually do, and what did the
SUT get told. The answers are the §11.5 rows for the network faults: applied-and-unanswered,
applied-and-500, applied-and-garbage, applied-and-never-answered, and killed-before-forwarding.

The kills are real: a sleeping interpreter stands in for the SUT process, and the proxy aims at
the pid the trial directory names, exactly as it would in a trial.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

import pytest

from crashproof.faults.injectors.proxy import ProxyInjector
from crashproof.faults.log import Cursor, TrialDir
from crashproof.faults.schedule import expand
from crashproof.faults.spec import CrashproofSpecError, from_doc
from crashproof.proxy import Proxy
from crashproof.workloads.spec import load_named
from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.client import WorldClient, WorldError
from crashproof.world.server import WorldServer

WORKLOAD = load_named("tool_chain_1_effect")
TOOL_NAMES = {t.endpoint: t.name for t in WORKLOAD.tools_for("EXTERNAL")}
ISSUE = {"title": "CI flake: test_retry", "body": "see search hits"}


def _spec(fault_type: str | None, boundary: str = "after:tool_effect", **params: Any) -> Any:
    faults = [] if fault_type is None else [
        {"id": "f1", "type": fault_type, "params": params,
         "trigger": {"boundary": boundary, "landmark": "tool:create_issue"}}
    ]
    return from_doc({"name": "p", "workload": "tool_chain_1_effect", "mode": "proxy",
                     "max_recoveries": 3, "faults": faults})


@dataclass
class Rig:
    world: Any
    server: WorldServer
    proxy: Proxy
    trial: TrialDir
    client: WorldClient

    async def call(self, endpoint: str = "issues.create", **args: Any) -> Any:
        """The SUT's call, on a thread: the World and the proxy live on this loop."""
        return await asyncio.to_thread(self.client.call, endpoint, args or ISSUE)

    def applied(self) -> dict[str, int]:
        return self.world.applied_counts()

    def observed(self) -> list[tuple[str, str]]:
        return [(o.landmark, o.boundary) for o in self.trial.observations()]


@pytest.fixture
async def make(tmp_path):
    rigs: list[Rig] = []

    async def build(spec: Any, *, sut_pid: int = 0, client_timeout: float = 5.0) -> Rig:
        trial = TrialDir(tmp_path / f"t-{len(rigs)}", fresh=True)
        schedule = expand(spec, 7, WORKLOAD)
        schedule.write(trial.schedule_path)
        trial.write_cursor(Cursor(trial_id="t-7", recovery_index=0, sut_pid=sut_pid))
        world = build_world()
        server = WorldServer(world, port=0)
        await server.start()
        proxy = Proxy(server.base_url, ProxyInjector(trial, schedule, trial_id="t-7"), tool_names=TOOL_NAMES)
        await proxy.start()
        rig = Rig(world, server, proxy, trial, WorldClient(proxy.base_url, timeout=client_timeout))
        rigs.append(rig)
        return rig

    try:
        yield build
    finally:
        for rig in rigs:
            await rig.proxy.stop()
            await rig.server.stop()


@pytest.fixture
def sut():
    """A process the proxy can kill: it sleeps, and nothing else."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


# --- the vocabulary ---------------------------------------------------------------
def test_a_proxy_spec_speaks_the_tool_boundaries_and_refuses_the_model_ones() -> None:
    assert _spec("kill", "after:tool_effect").mode == "proxy"
    assert _spec("tool_dropped_response").faults[0].type == "tool_dropped_response"
    with pytest.raises(CrashproofSpecError, match="model traffic does not cross the proxy"):
        from_doc({"name": "p", "workload": "tool_chain_1_effect", "mode": "proxy", "faults": [
            {"id": "m", "type": "model_500",
             "trigger": {"boundary": "before:model_call", "landmark": "model:*"}}]})
    with pytest.raises(CrashproofSpecError, match="not built in 'proxy' mode"):
        _spec("journal_unavailable", "after:tool_effect")
    with pytest.raises(CrashproofSpecError, match="only meaningful at"):
        _spec("tool_dropped_response", "before:tool_call")


# --- the wire ---------------------------------------------------------------------
async def test_with_no_fault_the_proxy_is_invisible_and_counts(make) -> None:
    rig = await make(_spec(None))
    result = await rig.call()
    assert result["id"], "the World's own answer, passed through"
    assert rig.applied() == {"issues.create#1": 1}
    assert rig.observed() == [
        ("tool:create_issue", "before:tool_call"),
        ("tool:create_issue", "after:tool_effect"),
        ("tool:create_issue", "after:tool_return"),
    ]
    assert rig.trial.faults() == []
    # The oracle and the control surface pass through untouched, and are never a landmark.
    probe = await asyncio.to_thread(rig.client.probe, "issues.create", ISSUE)
    assert probe["verdict"] == "COMMITTED"
    assert (await asyncio.to_thread(rig.client.applied)) == {"issues.create#1": 1}
    assert len(rig.trial.observations()) == 3


async def test_a_dropped_response_is_applied_and_unanswered(make) -> None:
    """§11.5: the World applied and responded; the socket closes with nothing written. From the
    SUT's side it is a timeout with a faster clock — a transport error, nothing known."""
    rig = await make(_spec("tool_dropped_response"))
    with pytest.raises(OSError):
        await rig.call()
    assert rig.applied() == {"issues.create#1": 1}
    [row] = rig.trial.faults()
    assert (row.type, row.boundary, row.landmark) == ("tool_dropped_response", "after:tool_effect", "tool:create_issue")
    assert rig.observed()[-1] == ("tool:create_issue", "after:tool_effect"), "no return boundary: nothing returned"


async def test_a_500_after_the_effect_is_applied_then_denied(make) -> None:
    rig = await make(_spec("tool_500"))
    with pytest.raises(WorldError) as exc:
        await rig.call()
    assert exc.value.status == 500
    assert rig.applied() == {"issues.create#1": 1}, "applied, then failed to answer — the classic case"


async def test_a_malformed_answer_is_garbage_the_client_cannot_parse(make) -> None:
    rig = await make(_spec("tool_malformed"))
    with pytest.raises(ValueError):
        await rig.call()
    assert rig.applied() == {"issues.create#1": 1}


async def test_a_timeout_forwards_and_never_answers(make) -> None:
    """Armed at `before:tool_call`, exactly as the shim's version is: the request is really
    forwarded and really applied, and the SUT's own bound is what ends the attempt."""
    rig = await make(_spec("tool_timeout", "before:tool_call"), client_timeout=0.3)
    with pytest.raises(OSError):
        await rig.call()
    assert rig.applied() == {"issues.create#1": 1}
    [row] = rig.trial.faults()
    assert row.boundary == "before:tool_call"
    # And the SUT giving up is what frees the handler: a second call goes through at once.
    assert (await rig.call(title="again", body="b"))["id"]


async def test_a_delay_is_only_latency(make) -> None:
    rig = await make(_spec("tool_delay", delay_ms=150))
    assert (await rig.call())["id"]
    assert rig.applied() == {"issues.create#1": 1}
    [row] = rig.trial.faults()
    assert row.params == {"delay_ms": 150}


# --- the kills ------------------------------------------------------------------
async def test_a_kill_before_the_call_forwards_nothing(make, sut) -> None:
    rig = await make(_spec("kill", "before:tool_call"), sut_pid=sut.pid)
    with pytest.raises(OSError):
        await rig.call()
    assert rig.applied() == {}, "the request died with its sender; the World never saw it"
    assert sut.wait(timeout=10) is not None
    [row] = rig.trial.faults()
    assert row.sut_pid == sut.pid and row.boundary == "before:tool_call"


async def test_a_kill_after_the_effect_leaves_the_world_ahead_of_the_sut(make, sut) -> None:
    """The window the whole design is about: applied, receipted, and nobody was told."""
    rig = await make(_spec("kill", "after:tool_effect"), sut_pid=sut.pid)
    with pytest.raises(OSError):
        await rig.call()
    assert rig.applied() == {"issues.create#1": 1}
    assert sut.wait(timeout=10) is not None


async def test_a_kill_after_the_return_lands_after_the_bytes(make, sut) -> None:
    rig = await make(_spec("kill", "after:tool_return"), sut_pid=sut.pid)
    assert (await rig.call())["id"], "the SUT had the answer in hand"
    assert sut.wait(timeout=10) is not None
    assert rig.observed()[-1] == ("tool:create_issue", "after:tool_return")


async def test_the_pid_the_sut_wrote_outranks_the_cursor(make, sut) -> None:
    """`Popen.pid` can be a launcher shim; the SUT's own word is what the proxy aims by."""
    rig = await make(_spec("kill", "after:tool_effect"), sut_pid=0)
    (rig.trial.path / "sut" / "pid-0").write_text(str(sut.pid), encoding="utf8")
    with pytest.raises(OSError):
        await rig.call()
    assert sut.wait(timeout=10) is not None


# --- the freeze -----------------------------------------------------------------
async def test_the_freeze_forwards_nothing_until_the_thaw(make) -> None:
    """`pause_past_ttl` from outside: the row asks the supervisor to stop the SUT, the request
    waits at the proxy, and the thaw marker is what lets it through — nothing is sent while the
    process is frozen, which is what the shim's self-SIGSTOP gives from inside."""
    rig = await make(_spec("pause_past_ttl", "before:tool_call"), client_timeout=10.0)
    call = asyncio.ensure_future(rig.call())
    await asyncio.sleep(0.3)
    [row] = rig.trial.faults()
    assert row.type == "pause_past_ttl" and not call.done()
    assert rig.applied() == {}, "frozen: nothing forwarded"

    rig.trial.thaw_marker(row.fault_id).write_text("1", encoding="utf8")
    assert (await asyncio.wait_for(call, 5))["id"]
    assert rig.applied() == {"issues.create#1": 1}


# --- the incarnation --------------------------------------------------------------
async def test_the_incarnation_is_read_at_firing_time(make) -> None:
    """The proxy outlives every restart of the SUT, so it cannot remember which incarnation it is
    talking to — it reads the cursor the supervisor wrote before the last spawn."""
    rig = await make(_spec("tool_500"))
    rig.trial.write_cursor(Cursor(trial_id="t-7", recovery_index=2, sut_pid=0))
    with pytest.raises(WorldError):
        await rig.call()
    [row] = rig.trial.faults()
    assert row.recovery_index == 2
    assert {o.recovery_index for o in rig.trial.observations()} == {2}


async def test_a_freeze_parked_at_a_stopping_proxy_is_dropped_not_forwarded(make) -> None:
    """The thaw marker never comes when the trial ends first. Stopping the proxy must release the
    parked request at once and drop it: forwarded after collection, it is an effect nobody counted."""
    rig = await make(_spec("pause_past_ttl", "before:tool_call"), client_timeout=10.0)
    call = asyncio.ensure_future(rig.call())
    await asyncio.sleep(0.3)
    assert [r.type for r in rig.trial.faults()] == ["pause_past_ttl"]
    started = asyncio.get_running_loop().time()
    await rig.proxy.stop()
    assert asyncio.get_running_loop().time() - started < 2.0, "the stop did not wait out THAW_WAIT_S"
    with pytest.raises(OSError):
        await asyncio.wait_for(call, 5)
    assert rig.applied() == {}, "dropped at the proxy, never applied"


# --- who the proxy aims at ---------------------------------------------------------
_ANNOUNCE = (
    "import os; from crashproof.faults.log import TrialDir; t = TrialDir.from_env(); "
    "t.announce_pid(t.read_cursor().recovery_index, os.environ.get('CRASHPROOF_KEEL_ROLE', 'worker')); "
    "print(os.getpid(), flush=True)"
)


def test_only_the_worker_under_test_names_itself_as_pid_n(tmp_path) -> None:
    """A zombie cell starts a successor from the same cursor. Writing `pid-0` too, it froze the idle
    observer instead of the holder in 41 of 60 published proxy trials. The successor writes last
    here on purpose — the losing order of that race — and the proxy must still aim at the worker."""
    import types

    from crashproof.faults.supervisor import Supervisor

    trial = TrialDir(tmp_path / "t-7", fresh=True)
    sup = Supervisor(
        trial, types.SimpleNamespace(entries=[]), trial_id="t-7",
        argv=[sys.executable, "-c", _ANNOUNCE], env={TrialDir.ENV: str(trial.path)},
        is_terminal=None, worker_count=2, secondary_env={"CRASHPROOF_KEEL_ROLE": "successor"},
    )
    sup._spawn(0)
    sup._sut.wait(timeout=30)
    sup._spawn_others()
    sup._others[0].wait(timeout=30)
    for log in sup._logs:
        log.close()
    worker = (trial.path / "sut" / "sut-0.log").read_text().split()[0]
    successor = (trial.path / "sut" / "successor-0.log").read_text().split()[0]
    assert worker != successor
    assert trial.pid_path(0).read_text() == worker
    assert trial.pid_path(0, "successor").read_text() == successor
    injector = ProxyInjector(trial, expand(_spec(None), 7, WORKLOAD), trial_id="t-7")
    assert injector._current() == (0, int(worker))


async def test_a_kill_that_never_landed_is_not_executed_because_the_trial_ended(tmp_path) -> None:
    """A kill fired from outside can miss. The supervisor's own kill at the end of the trial must
    not close that incarnation as though the fault had ended it: the trial is void, not scored."""
    import time
    import types

    from crashproof.faults import process
    from crashproof.faults.log import FaultFired
    from crashproof.faults.supervisor import Supervisor

    trial = TrialDir(tmp_path / "t-7", fresh=True)
    fired: list[float] = []

    async def is_terminal() -> bool:
        return bool(fired) and time.time() - fired[0] > 0.5

    sup = Supervisor(
        trial, types.SimpleNamespace(entries=[], timeout=20.0, max_recoveries=3), trial_id="t-7",
        argv=[sys.executable, "-c", "import time; time.sleep(60)"], env={}, is_terminal=is_terminal,
    )

    async def submit() -> None:
        trial.append_fault(FaultFired(fault_id="f1", trial_id="t-7", recovery_index=0, type="kill",
                                      boundary="after:tool_effect", landmark="tool:create_issue",
                                      occurrence=1, sut_pid=0))
        process.kill(0)  # aimed at nobody
        fired.append(time.time())

    result = await sup.run(submit)
    assert result.terminal and result.restarts == 0
    assert sup.executed_flags() == {"f1": False}


def test_a_pause_lasts_a_seeded_draw_over_the_arms_detection_timeout(tmp_path) -> None:
    """§13.4: [2x, 4x] of the arm's pinned detection timeout, one draw per trial, the same factor for
    every arm at a seed. An arm's own pin (Keel: 3 s) and a spec's explicit `pause_ms` both win."""
    import types

    from crashproof.faults.supervisor import DEFAULT_PAUSE_MS, Supervisor

    [entry] = expand(_spec("pause_past_ttl", boundary="before:tool_call"), 7, WORKLOAD).entries
    factor = entry.params["pause_factor"]
    assert 2.0 <= factor <= 4.0
    assert expand(_spec("pause_past_ttl", boundary="before:tool_call"), 7, WORKLOAD).entries[0].params == entry.params
    [pinned] = expand(_spec("pause_past_ttl", boundary="before:tool_call", pause_ms=500), 7, WORKLOAD).entries
    assert "pause_factor" not in pinned.params

    def sup(**pins: Any) -> Supervisor:
        return Supervisor(TrialDir(tmp_path / "t", fresh=True), types.SimpleNamespace(entries=[]),
                          trial_id="t", argv=[], env={}, is_terminal=None, **pins)

    assert sup(detection_timeout_s=2.0).pause_ms_for(entry.params) == factor * 2000.0
    assert sup(pinned_pause_ms=3000.0, detection_timeout_s=2.0).pause_ms_for(entry.params) == 3000.0
    assert sup(detection_timeout_s=2.0).pause_ms_for(pinned.params) == 500.0
    assert sup().pause_ms_for(entry.params) == DEFAULT_PAUSE_MS
