"""Retry policy: how many times, and how long to wait (§7.3, §8.7).

The MVP ran one attempt on purpose — an unmeasured retry policy is a guess, and a runtime that
retries by default hides the difference between "recovered" and "did it twice". Now there is a
matrix to measure against, so the policy arrives with the faults that exercise it.

Two rules keep it from becoming a duplicate machine:

**Only a retryable failure is retried.** An EXTERNAL timeout is `STEP_AMBIGUOUS`, never `FAILED`,
because the request left the process and retrying is precisely how systems duplicate effects (§8.5).
A definite refusal from the receiver — it said no — is `retryable=False` and ends the step.

**No backoff holds a lease it cannot renew.** A delay shorter than `PARK_BACKOFF_AFTER_S` is served
in-process with the heartbeat still running (§4.3); a longer one — the policy's own curve, or a
provider whose circuit breaker is open — parks: `RUN_WAITING{retry_backoff}` releases the lease and
sets `wake_at` (`runtime/steps.py`). So the curve is the policy's, capped by `max_backoff_s`, and
never by the lease; before the park existed it was clamped to half the TTL.

MODEL steps have their own policy (§8, "PURE-with-cost"): an outage is waited out rather than
turned into a failure after three quick tries.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_S = 0.1
DEFAULT_FACTOR = 2.0


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential backoff with full jitter, bounded attempts.

    Full jitter — a uniform draw over the whole interval rather than the interval's edge — because
    the alternative synchronises every retrying worker onto the same instant, and a benchmark that
    measures a thundering herd it manufactured is measuring itself.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_s: float = DEFAULT_BASE_S
    factor: float = DEFAULT_FACTOR
    max_backoff_s: float | None = None
    #: The receiver's key window (§9.7, `charge_card`: 1 h). No IDEMPOTENT re-send — a retry or a
    #: recovery re-run — starts this long after the step's first STARTED, by the store's clock: outside
    #: the window a receiver may no longer dedup the key, so the step goes to a human instead (§9.1).
    max_elapsed_s: float | None = None

    def may_retry(self, attempt_no: int) -> bool:
        return attempt_no < self.max_attempts

    def backoff_s(self, attempt_no: int, *, rng: random.Random | None = None) -> float:
        """The delay before attempt `attempt_no + 1`: a full-jitter draw over the exponential window,
        capped by `max_backoff_s`. Whether it is slept or parked is the engine's call."""
        window = self.base_s * (self.factor ** max(0, attempt_no - 1))
        if self.max_backoff_s is not None:
            window = min(window, self.max_backoff_s)
        draw = rng.random() if rng is not None else random.random()
        return max(0.0, window * draw)


#: One attempt. Kept as the default so nothing retries unless a caller asks, which is what let the
#: matrix measure recovery rather than a retry policy's opinion of it.
NO_RETRY = RetryPolicy(max_attempts=1)

#: §8's defaults (section-local decisions): tools (PURE, and IDEMPOTENT with the same key) 3 attempts,
#: base 1 s, x2, cap 30 s; MODEL steps 5 attempts, base 2 s, cap 60 s, below the circuit breaker.
TOOL_RETRY = RetryPolicy(max_attempts=3, base_s=1.0, max_backoff_s=30.0)
MODEL_RETRY = RetryPolicy(max_attempts=5, base_s=2.0, max_backoff_s=60.0)
