"""Human resolution: the way out of a RESOLVED_UNKNOWN suspension that is not `keel cancel`
(§6.2, §7.3, §10.3, §25.2).

Both sources of RESOLVED_UNKNOWN are here — an EXTERNAL `escalate` and an IDEMPOTENT
`key_window_expired` — because they are one path by design, and a test of one would let the other
drift. Each is driven the way an operator drives it: the run SUSPENDED, one `Keel.resolve_step` row in the
inbox, and a worker that picks it up with nothing else asked of anyone. No `keel resume`: §7.2.1
makes a resolve imply resume, and that is the first thing asserted.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import pytest

from keel import EffectClass, Keel, program, tool
from keel.core.clock import FakeClock
from keel.core.errors import StepFailed, UnknownOutcome
from keel.core.protocols import ProbeResult
from keel.journal.memory import MemoryJournal
from keel.replay.verify import verify
from keel.state.fold import fold

TTL = 2.0
CALLS: list[str] = []


@tool(effect=EffectClass.EXTERNAL, timeout=1.0, name="send_mail")
async def send_mail(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    CALLS.append("send_mail")
    raise UnknownOutcome("the relay hung up after DATA")


@tool(effect=EffectClass.IDEMPOTENT, timeout=1.0, name="put_doc")
async def put_doc(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    CALLS.append("put_doc")
    raise UnknownOutcome("502 with no body")


@tool(effect=EffectClass.EXTERNAL, timeout=1.0, resolution="probe", name="page_oncall")
async def page_oncall(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    CALLS.append("page_oncall")
    raise UnknownOutcome("the pager gateway timed out")


@page_oncall.probe_hook
async def _probe_page(effect_key: str, args: dict[str, Any], tctx: Any) -> ProbeResult:
    """Attempt 1 never reached the gateway; attempt 2 did, and only its answer was lost."""
    if tctx.attempt_no == 1:
        return ProbeResult("ABSENT", evidence="no page under this key")
    return ProbeResult("COMMITTED", evidence="paged", result={"paged": True})


@program(name="mailer", version="1.0")
async def mailer(ctx: Any, args: dict[str, Any]) -> Any:
    sent = await ctx.tool(args["tool"], to="ops")
    when = await ctx.now()
    return {"sent": sent, "at": when.isoformat()}


@program(name="careful_mailer", version="1.0")
async def careful_mailer(ctx: Any, args: dict[str, Any]) -> Any:
    try:
        await ctx.tool("send_mail", to="ops")
    except StepFailed as exc:
        return {"gave_up": exc.error}
    return {"gave_up": None}


@pytest.fixture(autouse=True)
def _calls() -> None:
    CALLS.clear()


def _keel(clock: FakeClock) -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        tools=[send_mail, put_doc, page_oncall],
        programs=[mailer, careful_mailer],
        clock=clock,
    )


async def _work(k: Keel, worker_id: str) -> str | None:
    lease = await k.journal.claim(worker_id, timedelta(seconds=TTL))
    if lease is None:
        return None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
    return lease.cause


async def _suspended(k: Keel, prog: Any, tool_name: str) -> Any:
    handle = await k.start(prog, {"tool": tool_name})
    await _work(k, "w1")
    state = fold(await k.events(handle.run_id))
    assert state.phase == "SUSPENDED"
    assert state.steps[0].state == "RESOLVED_UNKNOWN"
    return handle.run_id


def _recovery_causes(events: list[Any]) -> list[str]:
    return [e.body.cause for e in events if e.type == "RECOVERY_STARTED"]


@pytest.mark.parametrize(
    ("tool_name", "reason"), [("send_mail", "resolved_unknown"), ("put_doc", "key_window_expired")]
)
async def test_completed_lifts_the_suspension_and_hands_the_program_the_result(tool_name: str, reason: str) -> None:
    clock = FakeClock()
    k = _keel(clock)
    run_id = await _suspended(k, mailer, tool_name)
    assert fold(await k.events(run_id)).suspended_reason == reason

    assert await k.resolve_step(run_id, 0, "completed", evidence="found it in the relay log", result={"id": 7}, by="keshav")
    cause = await _work(k, "w2")

    events = await k.events(run_id)
    state = fold(events)
    assert cause == "WAKE" and _recovery_causes(events)[-1] == "RESUME", "a resolve implies resume (§7.2.1)"
    assert state.phase == "COMPLETED"
    assert state.result["sent"] == {"id": 7}, "the program is handed the human's result"
    assert CALLS == [tool_name], "nothing is re-sent: the human said it landed"

    [human] = [e.body for e in events if e.type == "STEP_RESOLVED" and e.body.method == "human"]
    assert human.resolution == "RESOLVED_COMPLETED" and human.step_index == 0
    assert human.evidence["evidence"] == "found it in the relay log" and human.evidence["by"] == "keshav"
    [row] = await k.journal.effects(run_id)
    assert (row.status, row.resolution) == ("RESOLVED_COMMITTED", "human")

    # C1: the resolved step is a memo like any other, so VERIFY reproduces the run.
    result = await verify(k.journal, run_id, mailer, tools=k.tools)
    assert result.ok and result.projection_hash is not None, result.as_dict()


async def test_completed_without_a_result_hands_back_the_declared_sentinel() -> None:
    k = _keel(FakeClock())
    run_id = await _suspended(k, mailer, "put_doc")
    assert await k.resolve_step(run_id, 0, "completed")
    await _work(k, "w2")

    state = fold(await k.events(run_id))
    sent = state.result["sent"]
    assert sent["__keel_resolved__"] == "COMMITTED"
    assert sent["effect_key"] == state.steps[0].effect_key
    assert sent["evidence"] == "resolved completed by a human"


async def test_failed_settles_the_step_and_the_program_sees_a_failure() -> None:
    k = _keel(FakeClock())
    run_id = await _suspended(k, mailer, "send_mail")
    assert await k.resolve_step(run_id, 0, "failed", evidence="bounced; nothing delivered")
    await _work(k, "w2")

    state = fold(await k.events(run_id))
    assert (state.phase, state.error) == ("FAILED", "bounced; nothing delivered")
    assert state.steps[0].state == "RESOLVED_FAILED"
    assert CALLS == ["send_mail"], "failed is a decision about the step, not a retry of the effect"
    [row] = await k.journal.effects(run_id)
    assert (row.status, row.resolution) == ("RESOLVED_ABSENT", "human")
    assert (await verify(k.journal, run_id, mailer, tools=k.tools)).ok


async def test_a_program_may_catch_the_failure_and_carry_on() -> None:
    k = _keel(FakeClock())
    run_id = await _suspended(k, careful_mailer, "send_mail")
    assert await k.resolve_step(run_id, 0, "failed", evidence="bounced")
    await _work(k, "w2")

    state = fold(await k.events(run_id))
    assert state.phase == "COMPLETED" and state.result == {"gave_up": "bounced"}
    assert (await verify(k.journal, run_id, careful_mailer, tools=k.tools)).ok


async def test_cancelled_is_the_run_cancel_and_closes_the_step() -> None:
    k = _keel(FakeClock())
    run_id = await _suspended(k, mailer, "send_mail")
    assert await k.resolve_step(run_id, 0, "cancelled", evidence="not worth chasing")
    await _work(k, "w2")

    events = await k.events(run_id)
    state = fold(events)
    assert state.phase == "CANCELLED"
    [asked] = [e.body for e in events if e.type == "SIGNAL_RECEIVED"]
    assert asked.signal_type == "cancel" and "not worth chasing" in asked.payload["reason"]
    assert state.steps[0].state == "CANCELLED", "§7.3: RESOLVED_UNKNOWN → CANCELLED by STEP_CANCELLED"
    [row] = await k.journal.effects(run_id)
    assert row.status == "RESOLVED_UNKNOWN", "cancelling the run does not say whether the mail went"
    assert (await verify(k.journal, run_id, mailer, tools=k.tools)).ok


async def test_a_resolve_for_the_wrong_step_is_ignored_and_the_run_suspends_again() -> None:
    k = _keel(FakeClock())
    run_id = await _suspended(k, mailer, "send_mail")
    assert await k.resolve_step(run_id, 5, "completed")
    await _work(k, "w2")

    events = await k.events(run_id)
    [ignored] = [e.body for e in events if e.type == "SIGNAL_IGNORED"]
    assert ignored.reason == "unknown_step"
    assert fold(events).phase == "SUSPENDED"
    assert await k.journal.claim("w3", timedelta(seconds=TTL)) is None, "the row is consumed, not re-read"


async def test_a_second_decision_for_one_step_is_ignored() -> None:
    k = _keel(FakeClock())
    run_id = await _suspended(k, careful_mailer, "send_mail")
    assert await k.resolve_step(run_id, 0, "failed", evidence="first")
    assert await k.resolve_step(run_id, 0, "completed", evidence="second")
    await _work(k, "w2")

    events = await k.events(run_id)
    assert [e.body.method for e in events if e.type == "STEP_RESOLVED"] == ["escalate", "human"]
    assert [e.body.reason for e in events if e.type == "SIGNAL_IGNORED"] == ["step_not_unresolved"]
    assert fold(events).result == {"gave_up": "first"}


async def test_the_cli_writes_the_same_row(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from keel.cli import main as cli

    k = _keel(FakeClock())
    run_id = await _suspended(k, mailer, "send_mail")
    queued: list[Any] = []
    monkeypatch.setattr(cli, "_load_app", lambda *_: k)
    monkeypatch.setattr(cli, "_run", queued.append)  # the test's loop runs it, not a second one
    r = CliRunner().invoke(cli.app, ["signal", str(run_id), "--resolve", "0=completed", "--evidence", "seen"])
    assert r.exit_code == 0, r.output
    await queued.pop()
    assert CliRunner().invoke(cli.app, ["signal", str(run_id), "--resolve", "zero=done"]).exit_code == cli.EXIT_USAGE

    [row] = await k.journal.pending_signals(run_id)
    assert (row.type, row.payload["kind"], row.payload["resolve_step"], row.payload["as"], row.payload["evidence"]) == (
        "custom", "resolve_step", 0, "completed", "seen",
    )


async def test_a_reattempt_that_goes_ambiguous_is_probed_in_its_turn() -> None:
    """ABSENT closes attempt 1 and starts attempt 2 under the same key (§7.4); attempt 2's answer is
    lost too, so it is probed in its turn. Keyed per step rather than per attempt, that second probe
    row was a unique violation and the run FAILED — the v1 confirmation tier's `pause_past_ttl`
    trial whose successor's re-attempt timed out under load."""
    k = _keel(FakeClock())
    handle = await k.start(mailer, {"tool": "page_oncall"})
    await _work(k, "w1")

    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED", [e.type for e in events]
    assert state.result["sent"] == {"paged": True}
    assert CALLS == ["page_oncall", "page_oncall"]
    resolved = [(e.body.attempt_no, e.body.resolution, e.body.method) for e in events if e.type == "STEP_RESOLVED"]
    assert resolved == [(1, "RESOLVED_FAILED", "probe"), (2, "RESOLVED_COMPLETED", "probe")]
    [row] = await k.journal.effects(handle.run_id)
    assert (row.status, row.resolution) == ("RESOLVED_COMMITTED", "probe")

    result = await verify(k.journal, handle.run_id, mailer, tools=k.tools)
    assert result.ok and result.projection_hash is not None, result.as_dict()
