"""Retry policy: how many times, and how long to wait (§7.3, §8.7).

The MVP ran one attempt on purpose — an unmeasured retry policy is a guess, and a runtime that
retries by default hides the difference between "recovered" and "did it twice". Now there is a
matrix to measure against, so the policy arrives with the faults that exercise it.

Two rules keep it from becoming a duplicate machine:

**Only a retryable failure is retried.** An EXTERNAL timeout is `STEP_AMBIGUOUS`, never `FAILED`,
because the request left the process and retrying is precisely how systems duplicate effects (§8.5).
A definite refusal from the receiver — it said no — is `retryable=False` and ends the step.

**The backoff stays inside the lease.** A delay shorter than the lease TTL is served in-process with
the heartbeat still running (§4.3). Longer delays are supposed to release the lease and set
`wake_at`, which needs `RUN_WAITING` — a v1 event with the signals inbox. So the cap is the lease
instead, and a policy that would exceed it is clamped rather than quietly holding a lease it cannot
renew. That ceiling is real and named, not hidden.
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

    def may_retry(self, attempt_no: int) -> bool:
        return attempt_no < self.max_attempts

    def backoff_s(self, attempt_no: int, *, lease_ttl_s: float, rng: random.Random | None = None) -> float:
        """The delay before attempt `attempt_no + 1`, clamped to stay inside the lease.

        Clamped rather than released-and-rescheduled: holding a lease past its TTL is how a worker
        becomes a zombie, and this module will not manufacture one to honour a backoff curve.
        """
        ceiling = min(
            self.max_backoff_s if self.max_backoff_s is not None else lease_ttl_s / 2,
            lease_ttl_s / 2,
        )
        window = min(self.base_s * (self.factor ** max(0, attempt_no - 1)), ceiling)
        draw = rng.random() if rng is not None else random.random()
        return max(0.0, window * draw)


#: One attempt. Kept as the default so nothing retries unless a caller asks, which is what let the
#: matrix measure recovery rather than a retry policy's opinion of it.
NO_RETRY = RetryPolicy(max_attempts=1)
