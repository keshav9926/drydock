"""Reserve-then-settle, and the admission check that makes S9 true (§8.6, §16.4).

A model attempt is at-least-once against the provider's bill and effectively-once as a decision.
Those are different facts and the budget has to respect both, so the rule is:

    at STARTED   charge `count_tokens(prompt) + max_tokens`   — the most this attempt could cost
    at COMPLETED swap the reservation for the reported usage  — what it did cost
    no outcome   the reservation stays charged, for good      — it was possibly billed

The third line is the one that matters. A crashed, timed-out or fenced model attempt may well have
been served and billed; the runtime cannot know, so it assumes it was. That is why the journaled
charge is an *upper bound* on what the provider billed under every fault in the taxonomy, and why
Keel can claim S9 while runtimes that count only completed calls report `budget_overshoot`.

Admission runs in the same transaction as the STARTED it guards. Refusing before the barrier means
no attempt and therefore no bill — a pre-dispatch refusal, `attempt_no = 0`, `retryable = False`.

`max_usd` is the same rule in dollars, priced from the table the run pinned at RUN_CREATED
(`providers/pricing.py`). An unpriced binding is admitted and makes the run's figure a floor, not a
bound — so from then on `max_usd` is not admitted against at all, and `keel show` says so.

# ponytail: `max_wall_clock` needs a deadline the waiting kinds respect (§16.4); it arrives with them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from keel.core.errors import KeelError
from keel.state.fold import usd_of


class BudgetExceeded(KeelError):
    """A pre-dispatch refusal. No attempt was started, so nothing was spent to discover it."""

    def __init__(self, dimension: str, charged: int, reservation: int, limit: int) -> None:
        super().__init__(
            f"budget {dimension}: {charged} charged + {reservation} reserved exceeds {limit}"
        )
        self.dimension = dimension
        self.charged = charged
        self.reservation = reservation
        self.limit = limit


@dataclass(frozen=True, slots=True)
class Reservation:
    """What one attempt is charged before it runs."""

    tokens: int = 0
    model_call: bool = False
    tool_call: bool = False
    #: A MODEL attempt's rate from the pinned table and the reservation priced at it; None: unpriced.
    price: tuple[float, float] | None = None
    usd: float | None = None


def reserve_model(prompt_tokens: int, max_tokens: int, price: tuple[float, float] | None = None) -> Reservation:
    """The most this attempt could cost: everything already in the prompt, plus everything the
    provider is allowed to generate. `count_tokens` is exact for the scripted provider and for
    Anthropic; anything else must over-count rather than under-count, or the bound is not one."""
    usd = usd_of({"input_tokens": prompt_tokens, "output_tokens": max_tokens}, price) if price else None
    return Reservation(tokens=prompt_tokens + max_tokens, model_call=True, price=price, usd=usd)


def reserve_tool() -> Reservation:
    """Tools carry no token reservation — their cost is the effect, which is not measured in
    tokens — but they do count against `max_tool_calls`."""
    return Reservation(tool_call=True)


def admit(budget: Any, charged: Any, reservation: Reservation) -> None:
    """Raise `BudgetExceeded` if this attempt would take the run past a declared limit.

    Called inside the STARTED transaction, so a refusal leaves no attempt behind.
    """
    if budget is None:
        return
    limits = budget if isinstance(budget, dict) else budget.model_dump()

    max_tokens = limits.get("max_tokens")
    if max_tokens is not None and reservation.tokens:
        if charged.tokens_charged + reservation.tokens > max_tokens:
            raise BudgetExceeded("max_tokens", charged.tokens_charged, reservation.tokens, max_tokens)

    max_calls = limits.get("max_model_calls")
    if max_calls is not None and reservation.model_call:
        # STARTED attempts, not outcomes: an attempt that crashed still asked the provider.
        if charged.model_calls + 1 > max_calls:
            raise BudgetExceeded("max_model_calls", charged.model_calls, 1, max_calls)

    max_usd = limits.get("max_usd")
    if max_usd is not None and reservation.usd is not None and charged.usd_priced:
        if charged.usd_charged + reservation.usd > max_usd:
            raise BudgetExceeded("max_usd", round(charged.usd_charged, 6), round(reservation.usd, 6), max_usd)

    max_tool_calls = limits.get("max_tool_calls")
    if max_tool_calls is not None and reservation.tool_call:
        if charged.tool_calls + 1 > max_tool_calls:
            raise BudgetExceeded("max_tool_calls", charged.tool_calls, 1, max_tool_calls)
