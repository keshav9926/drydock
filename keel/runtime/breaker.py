"""The circuit breaker: a per-provider policy below the journal (§8, §9.1, §27.5).

A provider outage must not become a retry storm across every run on the worker, each attempt billed.
So a worker keeps one breaker per provider. `n_open` consecutive failures open it; while it is open,
a failed MODEL attempt's next attempt is pushed out to the end of the cooldown instead of the retry
curve's next point, and the run parks for that wait at zero compute (`RUN_WAITING{retry_backoff}`,
§11.5 `provider_outage`). After the cooldown one attempt is let through: success closes the breaker,
failure opens it again.

It lives in the worker process and journals nothing. The journal sees what the breaker caused — a
STEP_FAILED carrying the `next_attempt_at` it chose, a RUN_WAITING — and never the breaker's state,
which is a property of this process's view of a provider, not of any run (§22.2: a cross-node breaker
cache is the one condition under which Redis would return, and it has not).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

DEFAULT_N_OPEN = 5
DEFAULT_COOLDOWN_S = 30.0


@dataclass(slots=True)
class CircuitBreaker:
    n_open: int = DEFAULT_N_OPEN
    cooldown_s: float = DEFAULT_COOLDOWN_S
    _failures: dict[str, int] = field(default_factory=dict)
    _opened_at: dict[str, datetime] = field(default_factory=dict)

    def blocked_until(self, provider: str, now: datetime) -> datetime | None:
        """When an attempt against `provider` may next start, or None if it may start now. Past the
        cooldown the breaker is half-open: one attempt goes through and its outcome decides."""
        opened = self._opened_at.get(provider)
        if opened is None:
            return None
        until = opened + timedelta(seconds=self.cooldown_s)
        return until if now < until else None

    def failure(self, provider: str, now: datetime) -> None:
        n = self._failures.get(provider, 0) + 1
        self._failures[provider] = n
        if n >= self.n_open:
            self._opened_at[provider] = now  # opens, or re-opens from half-open

    def success(self, provider: str) -> None:
        self._failures.pop(provider, None)
        self._opened_at.pop(provider, None)

    def is_open(self, provider: str, now: datetime) -> bool:
        return self.blocked_until(provider, now) is not None


if __name__ == "__main__":  # the one runnable check
    t0 = datetime(2026, 1, 1)
    b = CircuitBreaker(n_open=2, cooldown_s=10)
    b.failure("p", t0)
    assert b.blocked_until("p", t0) is None, "one failure is not an outage"
    b.failure("p", t0)
    assert b.blocked_until("p", t0) == t0 + timedelta(seconds=10), "n_open failures open it"
    assert b.blocked_until("p", t0 + timedelta(seconds=11)) is None, "half-open after the cooldown"
    b.failure("p", t0 + timedelta(seconds=11))
    assert b.is_open("p", t0 + timedelta(seconds=12)), "a half-open failure re-opens it"
    b.success("p")
    assert not b.is_open("p", t0 + timedelta(seconds=12)) and b.blocked_until("q", t0) is None
    print("breaker ok")
