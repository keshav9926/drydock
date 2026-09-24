"""The compensate hook (§9.5, §27.5): manual only, never automatic, and a fresh TOOL step of its own
with its own key — from the program (`ctx.compensate`) and from an operator (`Keel.compensate`,
`keel signal RUN --compensate STEP`), whose undo is a compensation run rather than a step injected into
a journal its program would then fail to replay."""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import pytest

from keel import Keel, program
from keel.core.clock import FakeClock
from keel.core.errors import ContractInvalid, UnknownTool
from keel.core.protocols import EffectClass, Idempotency
from keel.effects.registry import tool
from keel.journal.memory import MemoryJournal
from keel.replay.verify import verify
from keel.state.fold import fold

UNDONE: list[tuple[Any, ...]] = []


@tool(effect=EffectClass.EXTERNAL, timeout=1.0, name="book")
async def book(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    return {"booking": f"B-{args['seat']}"}


@book.compensate_hook
async def _cancel_booking(effect_key: str, args: dict[str, Any], result: Any, tctx: Any) -> dict[str, Any]:
    UNDONE.append((effect_key, args, result, tctx.effect_key))
    return {"cancelled": result["booking"]}


@tool(effect=EffectClass.EXTERNAL, timeout=1.0, name="email")
async def email(args: dict[str, Any], tctx: Any) -> str:
    return "sent"  # no inverse: no hook


@program(name="compensating", version="1.0")
async def compensating(ctx: Any, args: dict[str, Any]) -> Any:
    booked = await ctx.tool("book", seat=args["seat"])
    if args.get("undo") is not None:
        return {"booked": booked, "undone": await ctx.compensate(args["undo"])}
    return {"booked": booked}


def _keel(clock: FakeClock) -> Keel:
    return Keel(journal=MemoryJournal(clock=clock), tools=[book, email], programs=[compensating], clock=clock)


async def _work(k: Keel) -> None:
    for i in range(10):
        lease = await k.journal.claim(f"w{i}", timedelta(seconds=2.0))
        if lease is None:
            return
        with contextlib.suppress(BaseException):
            await k.worker(worker_id=f"w{i}", lease_ttl=2.0).execute(lease)
    raise AssertionError("still runnable")


@pytest.fixture(autouse=True)
def _fresh() -> None:
    UNDONE.clear()


async def test_the_program_undoes_an_effect_as_a_step_of_its_own() -> None:
    k = _keel(FakeClock())
    handle = await k.start(compensating, {"seat": "12A", "undo": 0})
    await _work(k)
    events = await k.events(handle.run_id)
    state = fold(events)
    assert state.phase == "COMPLETED"
    assert state.result == {"booked": {"booking": "B-12A"}, "undone": {"cancelled": "B-12A"}}
    booked, undo = state.steps[0], state.steps[1]
    assert (undo.kind, undo.name, undo.effect_class) == ("TOOL", "book.compensate", "EXTERNAL")
    assert undo.effect_key != booked.effect_key, "its own key"
    [(of_key, args, result, own_key)] = UNDONE
    assert (of_key, args, result, own_key) == (booked.effect_key, {"seat": "12A"}, {"booking": "B-12A"}, undo.effect_key)
    assert (await verify(k.journal, handle.run_id, compensating, tools=k.tools)).ok
    assert len(UNDONE) == 1, "a replay reads the journal; the hook runs once"


async def test_nothing_is_ever_compensated_by_itself() -> None:
    k = _keel(FakeClock())
    handle = await k.start(compensating, {"seat": "3C"})
    await _work(k)
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED" and not UNDONE


async def test_an_effect_that_did_not_commit_cannot_be_compensated() -> None:
    k = _keel(FakeClock())
    with pytest.raises(ContractInvalid, match="not a committed TOOL effect"):
        from keel.state.fold import committed_effect

        committed_effect([], 0)
    handle = await k.start(compensating, {"seat": "1A", "undo": 7})
    await _work(k)
    state = fold(await k.events(handle.run_id))
    assert state.phase == "FAILED" and "nothing to compensate" in state.error


async def test_an_operator_compensates_a_finished_run_with_a_compensation_run() -> None:
    k = _keel(FakeClock())
    original = await k.start(compensating, {"seat": "9F"})
    await _work(k)
    before = await k.events(original.run_id)

    handle = await k.compensate(original.run_id, 0)
    await _work(k)
    undo = fold(await k.events(handle.run_id))
    assert undo.phase == "COMPLETED" and undo.result == {"cancelled": "B-9F"}
    assert undo.program == "keel.compensate"
    [(of_key, args, _, own_key)] = UNDONE
    assert of_key == fold(before).steps[0].effect_key and args == {"seat": "9F"} and own_key != of_key
    assert await k.events(original.run_id) == before, "the original run's journal is untouched"


async def test_an_operator_cannot_compensate_what_has_no_hook() -> None:
    @program(name="emailer", version="1.0")
    async def emailer(ctx: Any, args: dict[str, Any]) -> Any:
        return await ctx.tool("email", to="x")

    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), tools=[book, email], programs=[emailer], clock=clock)
    handle = await k.start(emailer, {})
    await _work(k)
    with pytest.raises(UnknownTool):
        await k.compensate(handle.run_id, 0)


def test_a_compensation_declares_its_own_class() -> None:
    @tool(effect=EffectClass.EXTERNAL, timeout=1.0, name="upsert_doc")
    async def upsert(args: dict[str, Any], tctx: Any) -> None: ...

    @upsert.compensate_hook(effect=EffectClass.IDEMPOTENT, idempotency=Idempotency.KEY)
    async def _delete(effect_key: str, args: Any, result: Any) -> None: ...

    k = Keel(tools=[upsert])
    spec = k.tools.get("upsert_doc.compensate")
    assert (spec.effect_class, spec.timeout) == (EffectClass.IDEMPOTENT, 1.0)
    assert "upsert_doc.compensate" not in k.tools.manifest(), "derived, not declared"
    with pytest.raises(Exception, match="IDEMPOTENT needs"):
        upsert.compensate_hook(effect=EffectClass.IDEMPOTENT)


async def test_the_cli_starts_the_compensation_run(monkeypatch: Any, capsys: Any) -> None:
    from typer.testing import CliRunner

    from keel.cli import main as cli

    k = _keel(FakeClock())
    handle = await k.start(compensating, {"seat": "2B"})
    await _work(k)
    queued: list[Any] = []
    monkeypatch.setattr(cli, "_load_app", lambda *_: k)
    monkeypatch.setattr(cli, "_run", queued.append)
    assert CliRunner().invoke(cli.app, ["signal", str(handle.run_id), "--compensate", "0"]).exit_code == 0
    await queued.pop()
    assert "compensation of step 0" in capsys.readouterr().out
    await _work(k)
    assert UNDONE and UNDONE[0][1] == {"seat": "2B"}
