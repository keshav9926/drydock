"""The supervisor: the only thing in a trial that is allowed to know a crash happened (§11.9).

It owns the SUT's pid, the schedule cursor, the restart loop and the two bounds that end a trial
besides a terminal state — `max_recoveries` (L2) and `timeout` (L1).

The rule it exists to enforce is one line long and everything else follows from it: **restart the
worker with identical argv and env, and never pass it a run or thread id.** A runtime that finds
its own work is `self`; one whose server re-drives it is `engine`; one that has to be told is
`harness` — and that column is a headline finding, so the supervisor must never accidentally hand
a `self` runtime the help that would make it look like an `engine` one.

It learns that a fault fired by tailing `faults.jsonl`. That file is the only channel from an
in-SUT injector back to the harness, which is why a parked worker's row is written and fsynced
*before* it stops: the row is what asks to be frozen, and later thawed.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from crashproof.faults import process
from crashproof.faults.log import Cursor, FaultFired, TrialDir
from crashproof.faults.schedule import Schedule

POLL_S = 0.05
DEFAULT_PAUSE_MS = 3000.0


@dataclass(slots=True)
class Incarnation:
    recovery_index: int
    pid: int
    started_at: float
    exit_code: int | None = None
    ended_at: float | None = None
    #: The harness ended it at the end of the trial. That kill is the supervisor tidying up, never
    #: the fault a row recorded, so it can never make a `kill` row read as executed.
    stopped_by_harness: bool = False


@dataclass(slots=True)
class SupervisorResult:
    incarnations: list[Incarnation] = field(default_factory=list)
    restarts: int = 0
    timed_out: bool = False
    exhausted_recoveries: bool = False
    terminal: bool = False
    t_restarts: list[float] = field(default_factory=list)
    thawed: list[dict[str, Any]] = field(default_factory=list)
    #: `approval_delay` faults whose second, unkeyed approve was actually sent (§11.4 C).
    duplicates: list[str] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def wall_ms(self) -> float:
        return (self.ended_at - self.started_at) * 1000


class Supervisor:
    def __init__(
        self,
        trial: TrialDir,
        schedule: Schedule,
        *,
        trial_id: str,
        argv: list[str],
        env: dict[str, str],
        is_terminal: Any,
        worker_count: int = 1,
        secondary_env: dict[str, str] | None = None,
        status: Any = None,
        on_waiting: Any = None,
        pinned_pause_ms: float | None = None,
        detection_timeout_s: float | None = None,
    ) -> None:
        self.trial = trial
        self.schedule = schedule
        self.trial_id = trial_id
        self.argv = argv
        self.env = env
        self.is_terminal = is_terminal
        self.worker_count = worker_count
        self.secondary_env = secondary_env or {}
        #: The harness as the human (W5). `status()` is how it notices the run is parked;
        #: `on_waiting()` is the grant. Both optional: a workload that gates nothing never parks.
        self.status = status
        self.on_waiting = on_waiting
        self.pinned_pause_ms = pinned_pause_ms
        self.detection_timeout_s = detection_timeout_s
        self.result = SupervisorResult()
        self._sut: subprocess.Popen | None = None
        self._others: list[subprocess.Popen] = []
        self._seen_faults: set[str] = set()
        self._logs: list[Any] = []
        self._waiting_since: float | None = None
        self._granted = False
        self._duplicate_at: float | None = None
        self._waiting_faults = [e for e in schedule.entries if e.boundary == "supervisor"]

    # --- the loop ------------------------------------------------------------
    async def run(self, submit: Any) -> SupervisorResult:
        self.result.started_at = time.time()
        deadline = self.result.started_at + self.schedule.timeout
        self._spawn(0)
        self._spawn_others()
        await submit()

        try:
            while time.time() < deadline:
                await self._freeze_and_thaw()

                # Once the run is terminal nothing is restarted: the loop only lingers to send a
                # duplicate approve, and a worker that exits on completion is not a crash.
                if self._sut is not None and self._sut.poll() is not None and not self.result.terminal:
                    self._close_incarnation()
                    if self.result.restarts >= self.schedule.max_recoveries:
                        self.result.exhausted_recoveries = True  # L2 FAIL
                        break
                    self.result.restarts += 1
                    self.result.t_restarts.append(time.time())
                    self._spawn(self.result.restarts)

                if await self.is_terminal():
                    self.result.terminal = True
                    if self._duplicate_at is None:
                        break
                await self._play_the_human()
                await asyncio.sleep(POLL_S)
            else:
                self.result.timed_out = True  # L1 FAIL
        finally:
            self._stop_all()
            self.result.ended_at = time.time()
        return self.result

    # --- the human (W5) --------------------------------------------------------
    async def _play_the_human(self) -> None:
        """When the run is parked on an approval, the harness is the person it is waiting for.

        Three supervisor-executed faults decide what that person does, and they are executed here
        rather than by a shim because they happen *outside* the runtime — a kill while parked lands
        in a process that is, for Keel, not even holding the run (§13.7 H7):

            kill_while_waiting   end the process while parked, then grant to whoever comes back
            approval_expiry      never grant; the workload's `expires_in` decides the run's fate
            approval_delay       grant after `delay_ms`

        With none of them scheduled the grant is immediate. It is made once per trial: a human
        clicks once, and whether a runtime needs the click twice is the runtime's finding. The one
        exception is the one §11.4's spec C asks for — `approval_delay` with `duplicate: true` clicks
        again, unkeyed, `duplicate_gap_ms` after the first, whatever the run has done since: a
        runtime that turns the second click into a second grant is the weakness the cell exists to
        catch, and a trial that ended before the click was sent would not have tested it.
        """
        if self.status is None or self.on_waiting is None:
            return
        if self._granted:
            await self._click_again_if_due()
            return
        if await self.status() != "WAITING":
            return
        now = time.time()
        if self._waiting_since is None:
            self._waiting_since = now
            # Only the first time the park is observed: a `kill_while_waiting` fires once, on the
            # incarnation that parked, and the successor that comes back is the one that is granted.
            for entry in self._waiting_faults:
                if entry.type == "kill_while_waiting" and entry.fault_id not in self._seen_faults:
                    self._fire_from_outside(entry)
                    if self._sut is not None and self._sut.poll() is None:
                        process.kill(self._sut.pid)
                    return
        expiry = [e for e in self._waiting_faults if e.type == "approval_expiry"]
        if expiry:
            # The human never answers, and that is a fault that *fired* the moment the park was
            # observed: without its row the trial has no fault rows and is voided as "the schedule
            # never fired", which is the opposite of what happened.
            for entry in expiry:
                if entry.fault_id not in self._seen_faults:
                    self._fire_from_outside(entry)
            return
        delay = max(
            (float(e.params.get("delay_ms", 0.0)) for e in self._waiting_faults if e.type == "approval_delay"),
            default=0.0,
        )
        if (now - self._waiting_since) * 1000.0 < delay:
            return
        for entry in self._waiting_faults:
            if entry.type == "approval_delay" and entry.fault_id not in self._seen_faults:
                self._fire_from_outside(entry)
        self._granted = True
        gaps = [
            float(e.params.get("duplicate_gap_ms", 500.0))
            for e in self._waiting_faults
            if e.type == "approval_delay" and e.params.get("duplicate")
        ]
        if gaps:
            self._duplicate_at = time.time() + max(gaps) / 1000.0
        await self.on_waiting()
        await self._click_again_if_due()

    async def _click_again_if_due(self) -> None:
        """The second click of §11.4 C: the same approve, unkeyed — the adapter sends what it sent
        the first time, and nothing marks it as a retry."""
        if self._duplicate_at is None or time.time() < self._duplicate_at or self.on_waiting is None:
            return
        self._duplicate_at = None
        await self.on_waiting()
        self.result.duplicates += [
            e.fault_id for e in self._waiting_faults if e.type == "approval_delay" and e.params.get("duplicate")
        ]

    def _fire_from_outside(self, entry: Any) -> None:
        """A supervisor fault leaves the same row a shim fault would, in the same file, so the
        verifier and the placement view read one log. `sut_pid` is the incarnation the fault landed
        on; `executed` is stamped later by `executed_flags`, like every other kill."""
        row = FaultFired(
            fault_id=entry.fault_id,
            trial_id=self.trial_id,
            recovery_index=self.result.restarts,
            type=entry.type,
            boundary=entry.boundary,
            landmark=entry.landmark,
            occurrence=entry.occurrence,
            params=dict(entry.params),
            trigger_observed_at=time.time(),
            sut_pid=self._sut.pid if self._sut is not None else 0,
        )
        self.trial.append_fault(row)
        self._seen_faults.add(entry.fault_id)

    # --- processes -----------------------------------------------------------
    def _spawn(self, recovery_index: int) -> None:
        """Identical argv, identical env, every time. The cursor is written first, so a worker
        reads its own incarnation number rather than being handed one on a command line that has
        to stay byte-identical."""
        self.trial.write_cursor(
            Cursor(trial_id=self.trial_id, recovery_index=recovery_index, started_at=time.time())
        )
        proc = subprocess.Popen(
            self.argv, env={**os.environ, **self.env}, **self._output(f"sut-{recovery_index}")
        )
        self.trial.write_cursor(
            Cursor(
                trial_id=self.trial_id,
                recovery_index=recovery_index,
                sut_pid=proc.pid,
                started_at=time.time(),
            )
        )
        self._sut = proc
        self.result.incarnations.append(
            Incarnation(recovery_index=recovery_index, pid=proc.pid, started_at=time.time())
        )

    def _spawn_others(self) -> None:
        """A frozen process cannot reap itself. Where the cell freezes one, a second observer runs
        beside it — carrying no shim, so it can never fire the fault aimed at its predecessor."""
        for _ in range(self.worker_count - 1):
            self._others.append(
                subprocess.Popen(
                    self.argv,
                    env={**os.environ, **self.env, **self.secondary_env},
                    **self._output(f"successor-{len(self._others)}"),
                )
            )

    def _output(self, name: str) -> dict[str, Any]:
        """A SUT's own output goes to a file in its trial directory. Discarding it means a worker
        that dies on startup leaves no trace at all, and the trial reports a timeout with no
        explanation — which is exactly the shape of a harness bug hiding as a finding."""
        log = (self.trial.path / "sut" / f"{name}.log").open("w", encoding="utf8", errors="replace")
        self._logs.append(log)
        return {"stdout": log, "stderr": subprocess.STDOUT}

    def _close_incarnation(self) -> None:
        if self._sut is None:
            return
        current = self.result.incarnations[-1]
        current.exit_code = self._sut.returncode
        current.ended_at = time.time()

    def _stop_all(self) -> None:
        for log in self._logs:
            log.close()
        alive = self._sut is not None and self._sut.poll() is None
        for proc in ([self._sut] if self._sut else []) + self._others:
            if proc.poll() is None:
                process.resume(proc.pid)  # a frozen process cannot be killed until it is thawed
                process.kill(proc.pid)
        if self._sut is not None and self._sut.poll() is not None:
            self._close_incarnation()
            self.result.incarnations[-1].stopped_by_harness = alive

    # --- freezing ------------------------------------------------------------
    async def _freeze_and_thaw(self) -> None:
        """The fault log is the channel. A `pause_past_ttl` row means the worker has parked at the
        boundary with nothing sent, and is waiting to be stopped.

        The supervisor does the stopping because a process cannot reliably stop *itself* on both
        platforms: POSIX self-`SIGSTOP` lifts on `SIGCONT`, but Windows self-suspension leaves a
        state a later resume does not clear. Freezing from outside is one code path that works
        on both, and the worker is parked at the same instant either way.
        """
        for row in self._new_faults():
            if row.type != "pause_past_ttl":
                continue
            pause_ms = self.pause_ms_for(row.params)
            # The firing process's own pid, not `Popen.pid`: a launcher shim makes those different,
            # and a freeze aimed at the launcher stops nothing at all.
            pid = row.sut_pid or (self._sut.pid if self._sut else 0)
            if not pid:
                continue
            process.suspend(pid)
            await asyncio.sleep(pause_ms / 1000.0)  # past the lease, past the attempt deadline
            process.resume(pid)
            self.trial.thaw_marker(row.fault_id).write_text("1", encoding="utf8")
            self.result.thawed.append(
                {"fault_id": row.fault_id, "pid": pid, "pause_ms": pause_ms, "at": time.time()}
            )

    def pause_ms_for(self, params: dict[str, Any]) -> float:
        """The spec's own `pause_ms`, then the arm's pin, then §13.4's draw over the arm's pinned
        detection timeout, then the default for an arm with no detection timeout at all."""
        if "pause_ms" in params:
            return float(params["pause_ms"])
        if self.pinned_pause_ms is not None:
            return self.pinned_pause_ms
        if self.detection_timeout_s is not None and "pause_factor" in params:
            return float(params["pause_factor"]) * self.detection_timeout_s * 1000.0
        return DEFAULT_PAUSE_MS

    def _new_faults(self) -> list[FaultFired]:
        rows = [r for r in self.trial.faults() if r.fault_id not in self._seen_faults]
        self._seen_faults.update(r.fault_id for r in rows)
        return rows

    # --- collection ----------------------------------------------------------
    def executed_flags(self) -> dict[str, bool]:
        """A `kill` row whose process is still alive means the fault was recorded and did not
        happen — the trial is invalid rather than scored. Stamped on the supervisor's own copy in
        `result.json`, never written back into `faults.jsonl` (§11.7).

        "Ended" is read as the restart loop saw it. A kill fired from outside the SUT — the proxy's,
        or `kill_while_waiting` — can miss (a wrong pid, a `taskkill` that lands after the process
        left on its own), and the supervisor's own kill at the end of the trial would otherwise
        close that incarnation and stamp the miss as a kill. So an incarnation the harness stopped
        does not count, and neither does one that exited cleanly: a process that returned 0 was not
        killed."""
        flags: dict[str, bool] = {}
        by_incarnation = {inc.recovery_index: inc for inc in self.result.incarnations}
        for row in self.trial.faults():
            if row.type in ("kill", "kill_while_waiting"):
                inc = by_incarnation.get(row.recovery_index)
                flags[row.fault_id] = bool(
                    inc and inc.exit_code not in (None, 0) and not inc.stopped_by_harness
                )
            elif row.type == "pause_past_ttl":
                flags[row.fault_id] = any(t["fault_id"] == row.fault_id for t in self.result.thawed)
            elif row.type == "approval_delay" and row.params.get("duplicate"):
                flags[row.fault_id] = row.fault_id in self.result.duplicates
            else:
                flags[row.fault_id] = True
        return flags
