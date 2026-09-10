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


@dataclass(slots=True)
class SupervisorResult:
    incarnations: list[Incarnation] = field(default_factory=list)
    restarts: int = 0
    timed_out: bool = False
    exhausted_recoveries: bool = False
    terminal: bool = False
    t_restarts: list[float] = field(default_factory=list)
    thawed: list[dict[str, Any]] = field(default_factory=list)
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
    ) -> None:
        self.trial = trial
        self.schedule = schedule
        self.trial_id = trial_id
        self.argv = argv
        self.env = env
        self.is_terminal = is_terminal
        self.worker_count = worker_count
        self.secondary_env = secondary_env or {}
        self.result = SupervisorResult()
        self._sut: subprocess.Popen | None = None
        self._others: list[subprocess.Popen] = []
        self._seen_faults: set[str] = set()

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

                if self._sut is not None and self._sut.poll() is not None:
                    self._close_incarnation()
                    if self.result.restarts >= self.schedule.max_recoveries:
                        self.result.exhausted_recoveries = True  # L2 FAIL
                        break
                    self.result.restarts += 1
                    self.result.t_restarts.append(time.time())
                    self._spawn(self.result.restarts)

                if await self.is_terminal():
                    self.result.terminal = True
                    break
                await asyncio.sleep(POLL_S)
            else:
                self.result.timed_out = True  # L1 FAIL
        finally:
            self._stop_all()
            self.result.ended_at = time.time()
        return self.result

    # --- processes -----------------------------------------------------------
    def _spawn(self, recovery_index: int) -> None:
        """Identical argv, identical env, every time. The cursor is written first, so a worker
        reads its own incarnation number rather than being handed one on a command line that has
        to stay byte-identical."""
        self.trial.write_cursor(
            Cursor(trial_id=self.trial_id, recovery_index=recovery_index, started_at=time.time())
        )
        proc = subprocess.Popen(
            self.argv,
            env={**os.environ, **self.env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )

    def _close_incarnation(self) -> None:
        if self._sut is None:
            return
        current = self.result.incarnations[-1]
        current.exit_code = self._sut.returncode
        current.ended_at = time.time()

    def _stop_all(self) -> None:
        for proc in ([self._sut] if self._sut else []) + self._others:
            if proc.poll() is None:
                process.resume(proc.pid)  # a frozen process cannot be killed until it is thawed
                process.kill(proc.pid)
        if self._sut is not None and self._sut.poll() is not None:
            self._close_incarnation()

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
            pause_ms = float(row.params.get("pause_ms", DEFAULT_PAUSE_MS))
            pid = self._sut.pid if self._sut else None
            if pid is None:
                continue
            process.suspend(pid)
            await asyncio.sleep(pause_ms / 1000.0)  # past the lease, past the attempt deadline
            process.resume(pid)
            self.trial.thaw_marker(row.fault_id).write_text("1", encoding="utf8")
            self.result.thawed.append(
                {"fault_id": row.fault_id, "pid": pid, "pause_ms": pause_ms, "at": time.time()}
            )

    def _new_faults(self) -> list[FaultFired]:
        rows = [r for r in self.trial.faults() if r.fault_id not in self._seen_faults]
        self._seen_faults.update(r.fault_id for r in rows)
        return rows

    # --- collection ----------------------------------------------------------
    def executed_flags(self) -> dict[str, bool]:
        """A `kill` row whose process is still alive means the fault was recorded and did not
        happen — the trial is invalid rather than scored. Stamped on the supervisor's own copy in
        `result.json`, never written back into `faults.jsonl` (§11.7)."""
        flags: dict[str, bool] = {}
        by_incarnation = {inc.recovery_index: inc for inc in self.result.incarnations}
        for row in self.trial.faults():
            if row.type == "kill":
                inc = by_incarnation.get(row.recovery_index)
                flags[row.fault_id] = bool(inc and inc.exit_code is not None)
            elif row.type == "pause_past_ttl":
                flags[row.fault_id] = any(t["fault_id"] == row.fault_id for t in self.result.thawed)
            else:
                flags[row.fault_id] = True
        return flags
