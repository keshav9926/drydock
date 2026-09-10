"""Landmark matching: deciding, from history alone, whether this is the moment (§11.3).

A landmark is a logical point every runtime reaches — `tool:create_issue`, `model:n2` — never an
ordinal in one framework's traffic. That is the publication rule made mechanical: the same spec
lands on the same *logical* point in every arm, even when the arms issue different numbers of raw
requests.

The matcher is the only stateful part of an injector, and its state is rebuilt from the trial
directory at process start, because the process that accumulated it was killed.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from crashproof.faults.schedule import Entry, Schedule

WILDCARD = "*"


def landmark_of(kind: str, name: str) -> str:
    """`tool:create_issue`, `model:decide`. One spelling, used by every injector."""
    return f"{kind}:{name}"


def wildcard_of(landmark: str) -> str:
    kind, _, _ = landmark.partition(":")
    return f"{kind}:{WILDCARD}"


class Matcher:
    """Observe → count → match. Single-threaded by lock, because some frameworks run tools on
    worker threads and the observe-match-fire sequence must not interleave."""

    def __init__(
        self,
        schedule: Schedule,
        *,
        recovery_index: int = 0,
        fired: Iterable[str] = (),
        counts: dict[tuple[str, str], int] | None = None,
    ) -> None:
        self.schedule = schedule
        self.recovery_index = recovery_index
        self.fired: set[str] = set(fired)
        self.counts: dict[tuple[str, str], int] = dict(counts or {})
        self.lock = threading.Lock()

    def bump(self, landmark: str, boundary: str) -> int:
        """Count this observation, for the landmark and for its wildcard. Returns the occurrence
        number of the exact landmark, which is what goes in the observation row."""
        for key in ((landmark, boundary), (wildcard_of(landmark), boundary)):
            self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[(landmark, boundary)]

    def match(self, landmark: str, boundary: str) -> Entry | None:
        """The live entry this observation satisfies, if any. `bump` must already have run."""
        for entry in self.schedule.entries:
            if entry.fault_id in self.fired:
                continue  # spent in this trial, by this incarnation or a previous one
            if entry.boundary != boundary:
                continue
            if entry.landmark not in (landmark, wildcard_of(landmark)):
                continue
            if entry.recovery_index is not None and entry.recovery_index != self.recovery_index:
                continue
            if self.counts.get((entry.landmark, boundary), 0) != entry.occurrence:
                continue
            return entry
        return None

    def spend(self, entry: Entry) -> None:
        self.fired.add(entry.fault_id)
