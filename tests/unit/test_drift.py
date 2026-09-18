"""§18.6's drift detectors, and the Policy threshold they feed.

A plan that stops moving while the run keeps working, and a plan item ticked off with nothing done
for it: both are facts about the pair (plan projection, step history), so both are folds — and a
`Policy` reading the journal as of now can put a human in front of the next effect.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from keel import EffectClass, Keel, program, tool
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.runtime.policy import StaticPolicy
from keel.state.drift import drift
from keel.state.fold import fold

TTL = 2.0


@tool(effect=EffectClass.PURE, timeout=1.0, name="peek")
async def peek(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    return {}


@tool(effect=EffectClass.IDEMPOTENT, timeout=1.0, name="save")
async def save(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    return {"saved": args["v"]}


@program(name="planner", version="1.0")
async def planner(ctx: Any, args: dict[str, Any]) -> Any:
    await ctx.plan.init(["write"])                # 0: item 0.0
    await ctx.tool("save", v=1)                   # 1: an effect for "write"
    await ctx.plan.complete("0.0")                # 2
    review = await ctx.plan.add("review")         # 3: item "3"
    await ctx.plan.complete(review)               # 4: ticked off with nothing done since it was made
    for n in range(args["reads"]):                # 5..: the plan stops moving
        await ctx.tool("peek", n=n)
    await ctx.tool("save", v=2)
    return "done"


def _keel(clock: FakeClock, policy: Any = None) -> Keel:
    return Keel(journal=MemoryJournal(clock=clock), tools=[peek, save], programs=[planner], clock=clock,
                policy=policy)


async def _work(k: Keel) -> None:
    lease = await k.journal.claim("w", timedelta(seconds=TTL))
    assert lease is not None
    with contextlib.suppress(BaseException):
        await k.worker(worker_id="w", lease_ttl=TTL).execute(lease)


async def test_the_two_detectors_read_the_fold() -> None:
    k = _keel(FakeClock())
    handle = await k.start(planner, {"reads": 3})
    await _work(k)
    state = fold(await k.events(handle.run_id))
    assert state.phase == "COMPLETED"
    # Steps 5, 6, 7 read and 8 saved, all after the last PLAN step (4).
    assert drift(state) == {"steps_since_plan_update": 4, "items_completed_without_effects": ["3"]}
    assert state.plan_completed_at == {"0.0": 2, "3": 4}
    view = await k.get(handle.run_id)
    assert (view.steps_since_plan_update, view.items_completed_without_effects) == (4, ["3"])


async def test_a_run_with_no_plan_has_nothing_to_drift_from() -> None:
    @program(name="planless", version="1.0")
    async def planless(ctx: Any, args: dict[str, Any]) -> Any:
        await ctx.tool("save", v=0)

    k = _keel(FakeClock())
    k.register(planless)
    handle = await k.start(planless, {})
    await _work(k)
    assert drift(fold(await k.events(handle.run_id))) == {
        "steps_since_plan_update": None, "items_completed_without_effects": [],
    }


async def test_a_stale_plan_puts_a_human_in_front_of_the_next_effect() -> None:
    """`stale_plan_after=2`: reads go through (PURE carries no risk), the effect after them waits."""
    k = _keel(FakeClock(), StaticPolicy(stale_plan_after=2))
    handle = await k.start(planner, {"reads": 3})
    await _work(k)

    state = fold(await k.events(handle.run_id))
    assert state.phase == "WAITING_APPROVAL"
    [approval] = state.approvals.values()
    assert (approval.step_index, approval.payload["tool"]) == (8, "save")
    assert [s.kind for s in state.steps.values()][5:] == ["TOOL", "TOOL", "TOOL", "APPROVAL"]


async def test_keel_show_prints_both(monkeypatch: Any, capsys: Any) -> None:
    from typer.testing import CliRunner

    from keel.cli import main as cli

    k = _keel(FakeClock())
    handle = await k.start(planner, {"reads": 3})
    await _work(k)
    queued: list[Any] = []
    monkeypatch.setattr(cli, "_load_app", lambda *_: k)
    monkeypatch.setattr(cli, "_run", queued.append)
    assert CliRunner().invoke(cli.app, ["show", str(handle.run_id)]).exit_code == 0
    await queued.pop()
    assert "drift: 4 steps since the plan last changed; completed without an effect: 3" in capsys.readouterr().out
