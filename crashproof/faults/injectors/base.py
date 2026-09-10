"""What every injector does with a matched entry, and in what order (§11.7).

The order is the whole reliability argument, so it lives in one place rather than in each injector:

    1. observe — append the observation, fsync, and only then count it
    2. match   — against live entries; no match, return
    3. record  — append the fault row, fsync
    4. execute — os._exit, freeze, raise

Step 3 before step 4 is what makes "each entry fires at most once per trial" true across a kill. If
the process dies inside step 4 the row is already durable; if it dies between 3 and 4 the fault is
recorded as fired and did not happen — the supervisor stamps that trial invalid rather than scoring
it, which is the honest disposal of a fault whose effect nobody can observe.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from crashproof.faults import process
from crashproof.faults.log import FaultFired, Observation, TrialDir
from crashproof.faults.schedule import Entry, Schedule
from crashproof.faults.triggers import Matcher


class Injector:
    """The shared observe→match→record→execute sequence. A subclass adds boundaries, not order."""

    def __init__(
        self,
        trial: TrialDir,
        schedule: Schedule,
        *,
        trial_id: str,
        recovery_index: int = 0,
        sut_ref: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.trial = trial
        self.trial_id = trial_id
        self.recovery_index = recovery_index
        self.sut_ref = sut_ref
        # Firing state is trial-owned: a restarted worker rebuilds it from the directory, because
        # the process that accumulated it was killed.
        self.matcher = Matcher(
            schedule,
            recovery_index=recovery_index,
            fired=trial.fired_ids(),
            counts=trial.occurrence_counts(),
        )

    @classmethod
    def from_env(cls, **kwargs: Any) -> "Injector":
        trial = TrialDir.from_env()
        cursor = trial.read_cursor()
        return cls(
            trial,
            Schedule.read(trial.schedule_path),
            trial_id=cursor.trial_id,
            recovery_index=cursor.recovery_index,
            **kwargs,
        )

    # --- the sequence --------------------------------------------------------
    def at(self, landmark: str, boundary: str) -> None:
        """One boundary. Returns normally when nothing fires; may not return at all when it does."""
        with self.matcher.lock:
            occurrence = self.matcher.bump(landmark, boundary)
            self.trial.append_observation(
                Observation(
                    landmark=landmark,
                    boundary=boundary,
                    occurrence=occurrence,
                    recovery_index=self.recovery_index,
                    ts=time.time(),
                )
            )
            entry = self.matcher.match(landmark, boundary)
            if entry is None:
                return
            self.matcher.spend(entry)
            self._record(entry)
        self._execute(entry)

    def _record(self, entry: Entry) -> None:
        self.trial.append_fault(
            FaultFired(
                fault_id=entry.fault_id,
                trial_id=self.trial_id,
                recovery_index=self.recovery_index,
                type=entry.type,
                boundary=entry.boundary,
                landmark=entry.landmark,
                occurrence=entry.occurrence,
                params=entry.params,
                trigger_observed_at=time.time(),
                trigger_observed_mono_ns=time.monotonic_ns(),
                sut_ref=self.sut_ref() if self.sut_ref else {},
            )
        )

    def _execute(self, entry: Entry) -> None:
        if entry.delay_ms:
            # The one time-shaped input, and it is applied *after* a history-defined observation.
            time.sleep(entry.delay_ms / 1000.0)
        if entry.type == "kill":
            process.die_now()
        elif entry.type == "pause_past_ttl":
            # Stop here with nothing sent, and stay stopped past the lease. The fault row is
            # already durable, and it is what tells the supervisor to freeze and later thaw us.
            process.freeze_self(self.trial.thaw_marker(entry.fault_id))
        else:  # pragma: no cover - refused at spec load (§11.3)
            raise NotImplementedError(f"fault type {entry.type!r} is not built")
