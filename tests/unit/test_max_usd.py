"""`max_usd` (§16.4): reserve-then-settle in dollars, priced from the table the run pinned at
RUN_CREATED, with an unpriced binding surfaced as a gap rather than guessed."""

from __future__ import annotations

from typing import Any

import pytest

from keel import Budget, Keel, program
from keel.core.clock import FakeClock
from keel.core.errors import ContractInvalid
from keel.journal.memory import MemoryJournal
from keel.providers import pricing
from keel.providers.scripted import Decision, ScriptedProvider
from keel.runtime import delegation
from keel.runtime.budget import BudgetExceeded, admit, reserve_model
from keel.state.fold import Charged, fold, usd_of

RATE = pricing.rate(pricing.current_ref("scripted"), "scripted", None)


@program(name="usd_two_calls", version="1.0")
async def two_calls(ctx: Any, args: dict[str, Any]) -> str:
    await ctx.model([{"role": "user", "content": "first"}], name="first", max_tokens=1000)
    return (await ctx.model([{"role": "user", "content": "second"}], name="second", max_tokens=1000)).text


def _keel() -> Keel:
    clock = FakeClock()
    return Keel(journal=MemoryJournal(clock=clock), provider=ScriptedProvider([Decision(text="ok")] * 2),
                programs=[two_calls], clock=clock)


def test_the_fold_reserves_settles_and_floors_in_dollars() -> None:
    c = Charged()
    held = usd_of({"input_tokens": 100, "output_tokens": 1000}, RATE)
    c.start(0, 1, 1100, "MODEL", held, RATE)
    assert c.usd_charged == pytest.approx(held)
    c.chunk(0, 1, {"input_tokens": 100, "output_tokens": 10})
    assert c.usd_charged == pytest.approx(held), "a chunk below the reservation raises nothing"
    c.settle(0, 1, {"input_tokens": 100, "output_tokens": 40})
    assert c.usd_charged == pytest.approx(usd_of({"input_tokens": 100, "output_tokens": 40}, RATE))
    c.start(1, 1, 1100, "MODEL", held, RATE)  # never settles: a crash
    assert c.usd_charged == pytest.approx(usd_of({"input_tokens": 100, "output_tokens": 40}, RATE) + held)
    assert c.usd_priced


def test_an_unpriced_attempt_makes_the_figure_a_floor_and_admission_stops() -> None:
    c = Charged()
    c.start(0, 1, 1100, "MODEL", None, None)
    assert not c.usd_priced
    admit({"max_usd": 0.0}, c, reserve_model(10**6, 10**6, RATE))  # not admitted against any more


def test_admission_refuses_the_attempt_that_would_cross_max_usd() -> None:
    c = Charged(usd_charged=0.01)
    with pytest.raises(BudgetExceeded) as exc:
        admit({"max_usd": 0.02}, c, reserve_model(1000, 1000, RATE))  # 0.018 more
    assert exc.value.dimension == "max_usd"
    admit({"max_usd": 0.03}, c, reserve_model(1000, 1000, RATE))


async def test_a_run_pins_its_table_and_is_charged_in_dollars(monkeypatch: pytest.MonkeyPatch) -> None:
    k = _keel()
    handle = await k.start(two_calls, {}, budget=Budget(max_usd=1.0))
    created = (await k.events(handle.run_id))[0]
    assert created.body.model_config_["pricing_ref"] == "scripted-2026-09"
    # A price change after RUN_CREATED re-values nothing: the run reads the table it pinned.
    monkeypatch.setitem(pricing.TABLES, "scripted-2099-01", {("scripted", "*"): (300.0, 1500.0)})
    monkeypatch.setitem(pricing.CURRENT, "scripted", "scripted-2099-01")
    await k.worker(worker_id="inline").run_until_idle(run_id=handle.run_id, timeout=30)
    events = await k.events(handle.run_id)
    assert fold(events).phase == "COMPLETED"
    started = [e.body for e in events if e.type == "STEP_ATTEMPT_STARTED"]
    assert [tuple(b.price) for b in started] == [RATE, RATE]
    settled = sum(usd_of(e.body.usage, RATE) for e in events if e.type == "STEP_COMPLETED" and e.body.usage)
    state = fold(events)
    assert state.charged.usd_charged == pytest.approx(settled) and settled > 0


async def test_max_usd_refuses_before_the_barrier_and_the_run_fails() -> None:
    k = _keel()
    result = await k.run(two_calls, {}, budget=Budget(max_usd=0.0001))
    events = await k.events(result.run_id)
    assert result.phase == "FAILED"
    [refusal] = [e for e in events if e.type == "STEP_FAILED"]
    assert refusal.attempt_no == 0 and "max_usd" in refusal.body.error
    assert not [e for e in events if e.type == "STEP_ATTEMPT_STARTED"], "no attempt, so no bill"


async def test_an_unpriced_binding_runs_and_says_so() -> None:
    k = _keel()
    result = await k.run(two_calls, {}, budget=Budget(max_usd=0.0001),
                         model_config={"provider": "scripted", "pricing_ref": "no-such-table"})
    assert result.phase == "COMPLETED", "max_usd cannot be enforced against a figure that is not a bound"
    view = await k.get(result.run_id)
    assert view.charged["usd_priced"] is False and view.pricing_ref == "no-such-table"


def test_delegation_slices_are_admitted_in_dollars_too() -> None:
    contract = delegation.Delegation(program="child", args={}, budget_slice={"max_usd": 0.5}, result_schema={})
    delegation.validate([contract, contract], parent_tools=None, parent_remaining_tokens=None,
                        parent_remaining_usd=1.0)
    with pytest.raises(ContractInvalid, match="max_usd"):
        delegation.validate([contract, contract, contract], parent_tools=None, parent_remaining_tokens=None,
                            parent_remaining_usd=1.0)


def test_a_child_settles_its_dollars_into_the_parent_ledger() -> None:
    c = Charged()
    c.reserve_child("kid", {"max_usd": 0.5})
    assert c.usd_charged == pytest.approx(0.5)
    c.settle_child("kid", {"tokens_charged": 0, "usd_charged": 0.125, "usd_priced": True})
    assert c.usd_charged == pytest.approx(0.125) and c.usd_priced
    c.reserve_child("kid2", {"max_usd": 0.5})
    c.settle_child("kid2", {"tokens_charged": 0, "usd_charged": 0.0, "usd_priced": False})
    assert not c.usd_priced, "an unpriced child makes the parent's figure a floor too"
