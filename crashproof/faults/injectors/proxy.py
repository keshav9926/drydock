"""The proxy injector: the same observe → match → record sequence, one process further out (§11.2).

Two things differ from the shim, and both follow from where it runs.

It lives in the *harness* process for the life of the trial, across every restart of the SUT. So
the incarnation a firing is recorded against is read from the cursor at that moment rather than
fixed at construction, and a `kill` is aimed at the SUT's pid rather than at `os._exit` — the pid
the SUT wrote for itself, because on Windows `Popen.pid` can be a launcher shim and a freeze aimed
at a launcher freezes nothing.

And it fires on the event loop that also hosts the World, so nothing here may block: a delay is
`asyncio.sleep`, a freeze is a wait for the thaw marker, and `apply` returns an *action* for the
proxy's handler to perform on the socket rather than touching a socket itself. The order of the
first three steps is the shim's and is not restated here; `arm` is that order under the lock.
"""

from __future__ import annotations

import asyncio
import time

from crashproof.faults import process
from crashproof.faults.injectors.base import DEFAULT_DELAY_MS, Injector
from crashproof.faults.log import FaultFired, Observation, TrialDir
from crashproof.faults.schedule import Entry, Schedule

#: How long a frozen request waits for the thaw before being forwarded anyway. The supervisor
#: resumes the SUT after `pause_ms` and writes the marker; a marker that never comes means the
#: supervisor is gone, and a request parked for ever would hide that as a timeout.
THAW_WAIT_S = 60.0


class ProxyInjector(Injector):
    def __init__(self, trial: TrialDir, schedule: Schedule, *, trial_id: str) -> None:
        super().__init__(trial, schedule, trial_id=trial_id, recovery_index=0)

    # --- who the fault lands on ------------------------------------------------
    def _current(self) -> tuple[int, int]:
        """`(recovery_index, sut_pid)` as of now, from the trial directory: the supervisor writes
        the cursor before every spawn, and the SUT writes its own pid once it is up."""
        cursor = self.trial.read_cursor()
        pid_file = self.trial.path / "sut" / f"pid-{cursor.recovery_index}"
        pid = cursor.sut_pid or 0
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf8").strip() or pid)
            except ValueError:
                pass
        return cursor.recovery_index, pid

    def _record(self, entry: Entry) -> None:
        recovery_index, pid = self._current()
        self.trial.append_fault(
            FaultFired(
                fault_id=entry.fault_id,
                trial_id=self.trial_id,
                recovery_index=recovery_index,
                type=entry.type,
                boundary=entry.boundary,
                landmark=entry.landmark,
                occurrence=entry.occurrence,
                params=entry.params,
                trigger_observed_at=time.time(),
                trigger_observed_mono_ns=time.monotonic_ns(),
                sut_pid=pid,
            )
        )

    # --- the sequence ----------------------------------------------------------
    def arm(self, landmark: str, boundary: str) -> Entry | None:
        """Observe, match, record — under the lock, in that order — and hand back what fired.
        The action itself is `apply`, awaited by the handler, because it may take time."""
        recovery_index, _ = self._current()
        self.recovery_index = recovery_index
        self.matcher.recovery_index = recovery_index
        with self.matcher.lock:
            occurrence = self.matcher.bump(landmark, boundary)
            self.trial.append_observation(
                Observation(
                    landmark=landmark,
                    boundary=boundary,
                    occurrence=occurrence,
                    recovery_index=recovery_index,
                    ts=time.time(),
                )
            )
            entry = self.matcher.match(landmark, boundary)
            if entry is None:
                return None
            self.matcher.spend(entry)
            self._record(entry)
        return entry

    async def apply(self, entry: Entry) -> str:
        """What the network does to this request. One of:

            continue   forward / answer normally (after a delay or a freeze)
            killed     the SUT is dead; write nothing
            500        answer 5xx
            timeout    forward, then never answer
            dropped    close the socket with nothing written
            malformed  answer 200 with a body that is not JSON
        """
        if entry.delay_ms:
            await asyncio.sleep(entry.delay_ms / 1000.0)
        kind = entry.type
        if kind == "kill":
            _, pid = self._current()
            process.kill(pid)
            return "killed"
        if kind == "pause_past_ttl":
            # The row is what asks the supervisor to freeze the SUT; the marker is how it says the
            # thaw happened. Nothing is forwarded in between — the same "nothing sent while
            # frozen" the shim's self-SIGSTOP gives, realised from outside.
            marker = self.trial.thaw_marker(entry.fault_id)
            deadline = time.monotonic() + THAW_WAIT_S
            while time.monotonic() < deadline and not marker.exists():
                await asyncio.sleep(0.01)
            return "continue"
        if kind == "tool_delay":
            await asyncio.sleep(float(entry.params.get("delay_ms", DEFAULT_DELAY_MS)) / 1000.0)
            return "continue"
        if kind == "tool_500":
            return "500"
        if kind == "tool_timeout":
            return "timeout"
        if kind == "tool_dropped_response":
            return "dropped"
        if kind == "tool_malformed":
            return "malformed"
        raise NotImplementedError(f"fault type {kind!r} is not a proxy fault")  # refused at load
