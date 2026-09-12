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

import os
import signal
import threading
import time
from collections.abc import Callable
from typing import Any

from crashproof.faults import process
from crashproof.faults.log import FaultFired, Observation, TrialDir
from crashproof.faults.schedule import Entry, Schedule
from crashproof.faults.triggers import Matcher

DEFAULT_DELAY_MS = 2000.0
#: The two `sigterm_grace_*` types differ only in whether the grace covers the open step, so the
#: grace is a property of the type rather than a parameter every spec has to remember to set. Both
#: are pinned by the harness and printed in `config_pin`: 3 s is longer than any step timeout any
#: arm declares, and 150 ms is shorter than the shortest, so `_ok` lets the drain finish and
#: `_too_short` cuts it off — for every arm, from one spec (§11.5).
DEFAULT_GRACE_MS = 10_000.0
GRACE_MS = {"sigterm_grace_ok": 3_000.0, "sigterm_grace_too_short": 150.0}


class FaultResponse(Exception):
    """What the receiver said instead of answering. A 5xx is an *unknown* outcome — epistemically
    identical to a timeout — so the effect class decides what happens next, not the status code."""

    def __init__(self, kind: str, status: int) -> None:
        super().__init__(f"{kind}: HTTP {status}")
        self.kind = kind
        self.status = status


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
        observe_only: bool = False,
    ) -> None:
        self.trial = trial
        self.trial_id = trial_id
        self.recovery_index = recovery_index
        self.sut_ref = sut_ref
        # A second SUT process — the successor in a zombie cell — must never fire the fault aimed
        # at its predecessor, but it must still be *seen*: model and tool calls are counted at the
        # wire from this log, and a process whose work is invisible makes the economy metrics a
        # statement about which process happened to carry the instrument.
        self.observe_only = observe_only
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
    def at(self, landmark: str, boundary: str, *, tokens: int | None = None) -> None:
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
                    tokens=tokens,
                )
            )
            if self.observe_only:
                return
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
                sut_pid=os.getpid(),
                sut_ref=self.sut_ref() if self.sut_ref else {},
            )
        )

    @property
    def alternate_armed(self) -> bool:
        """Read fresh every ask, never cached: the flag may have been armed by a *predecessor*
        process, and a value read once at startup would miss it."""
        return self.trial.alternate_armed

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
        elif entry.type in ("sigterm_grace_ok", "sigterm_grace_too_short"):
            self._sigterm(entry)
        elif entry.type in ("tool_delay", "model_timeout"):
            # A blocking sleep, deliberately: it runs on the same worker thread as the request, so
            # a runtime whose own timeout should fire still gets the chance to fire it.
            time.sleep(float(entry.params.get("delay_ms", DEFAULT_DELAY_MS)) / 1000.0)
        elif entry.type in ("tool_500", "model_500"):
            raise FaultResponse(entry.type, entry.params.get("status", 500))
        elif entry.type == "tool_timeout":
            pass  # armed at the World by the shim, which knows which endpoint (§11.5)
        elif entry.type == "model_reask_alternate":
            # Arms a trial-owned flag and returns. The provider is what changes its answer, and it
            # stays a pure function of (request content, flag) — no ask counter anywhere, which is
            # what keeps a re-asked fingerprint the *same* question rather than the nth one.
            self.trial.alternate_marker().write_text(entry.fault_id, encoding="utf8")
        else:  # pragma: no cover - refused at spec load (§11.3)
            raise NotImplementedError(f"fault type {entry.type!r} is not built")

    def _sigterm(self, entry: Entry) -> None:
        """Ask politely, then insist. The follow-up kill is armed *inside* the SUT and timed to the
        millisecond, because tailing a file for it would put jitter into precisely the grace the
        cell measures (§11.1)."""
        grace_ms = float(
            entry.params.get("grace_ms", GRACE_MS.get(entry.type, DEFAULT_GRACE_MS))
        )
        threading.Timer(grace_ms / 1000.0, process.die_now).start()
        signal.raise_signal(signal.SIGTERM)
