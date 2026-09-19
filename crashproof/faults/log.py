"""The trial directory: firing state that outlives the process it belongs to (§11.7).

A worker that has just been restarted must not fire a fault it already fired, and a worker cannot
remember anything — it was killed. So firing state lives in files the supervisor owns and both
incarnations can read.

Five files, no locks across processes:

    supervisor  → cursor.json, program_variant           (single writer)
    firing site → faults.jsonl, observations.jsonl       (appends; more than one process may write)
    World       → world/receipts.jsonl                   (single writer)

An append is one write the OS places at end-of-file (`_durably_append`), so the logs can have
several writers — the proxy and the SUT's observe-only shim do — without interleaving.

The write order inside the firing site is the whole reliability argument. Observe and fsync first,
so the occurrence counter survives the kill that is about to happen; append the fault row and fsync
*before* executing the fault, so "each entry fires at most once per trial" holds across a kill. A
process that dies between the row and the fault leaves a row for a fault that did not happen — the
supervisor stamps that trial invalid rather than scoring it, which is the honest disposal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

CURSOR = "cursor.json"
FAULTS = "faults.jsonl"
OBSERVATIONS = "observations.jsonl"
SCHEDULE = "schedule.json"
SPEC = "spec.yaml"
RESULT = "result.json"


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    landmark: str
    boundary: str
    occurrence: int
    recovery_index: int
    ts: float
    #: Prompt size at `before:model_call`, charged when the request is sent rather than when it
    #: returns — an attempt that never came back was still billed (§16.4), and counting it at the
    #: return would make every crashed attempt free.
    tokens: int | None = None


class FaultFired(BaseModel):
    """One firing. `executed` is deliberately not here: the firing site cannot know whether the
    fault it is about to execute actually happened, so the supervisor stamps that on its own copy
    in `result.json` and never writes back into this file."""

    model_config = ConfigDict(frozen=True)

    fault_id: str
    trial_id: str
    recovery_index: int
    type: str
    boundary: str
    landmark: str
    occurrence: int
    params: dict[str, Any] = {}
    trigger_observed_at: float = 0.0
    trigger_observed_mono_ns: int = 0
    #: The firing process's *own* pid. The supervisor cannot infer it: a venv launcher shim (Windows
    #: Store Python is one) makes `Popen.pid` the launcher, with the real interpreter a grandchild.
    #: Killing a tree hides that; freezing one does not, and a freeze aimed at a launcher freezes
    #: nothing. So the only process that knows for certain says so, in the row it was going to
    #: write anyway.
    sut_pid: int = 0
    sut_ref: dict[str, Any] = {}


class Cursor(BaseModel):
    """Written by the supervisor BEFORE every spawn, so a worker reads its own incarnation number
    rather than being told one on a command line that must stay identical."""

    model_config = ConfigDict(frozen=True)

    trial_id: str
    recovery_index: int = 0
    sut_pid: int | None = None
    started_at: float = 0.0


class TrialDir:
    """The one channel between the supervisor and an in-SUT injector, and the only thing that
    changes content across restarts."""

    ENV = "CRASHPROOF_TRIAL_DIR"

    def __init__(self, path: Path | str, *, fresh: bool = False) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "world").mkdir(exist_ok=True)
        (self.path / "sut").mkdir(exist_ok=True)
        if fresh:
            self._clear()

    def _clear(self) -> None:
        """Empty the firing state, rather than removing the directory that holds it.

        A trial directory IS the firing state: reusing a dirty one means every schedule entry is
        already spent, the fault never fires, and the trial reports a clean recovery it never
        performed — a false PASS, the one result this harness must never produce. But `rmtree` is
        the wrong tool for saying so on Windows, where a single handle still open somewhere makes
        the whole call fail and takes the trial with it. Emptying the named files is what `fresh`
        actually means, and it cannot fail for a reason that has nothing to do with the trial.

        The SUT never asks for this: it is joining a trial, not starting one.
        """
        for name in (CURSOR, FAULTS, OBSERVATIONS, SCHEDULE, RESULT):
            _truncate(self.path / name)
        _truncate(self.receipts_path)
        for stale in self.path.glob("thawed-*"):
            _truncate(stale)
        _truncate(self.alternate_marker())
        _truncate(self.outage_marker())
        for leftover in (self.path / "sut").glob("*"):
            _truncate(leftover)

    # --- paths ---------------------------------------------------------------
    @property
    def cursor_path(self) -> Path:
        return self.path / CURSOR

    @property
    def faults_path(self) -> Path:
        return self.path / FAULTS

    @property
    def observations_path(self) -> Path:
        return self.path / OBSERVATIONS

    @property
    def schedule_path(self) -> Path:
        return self.path / SCHEDULE

    @property
    def receipts_path(self) -> Path:
        return self.path / "world" / "receipts.jsonl"

    def thaw_marker(self, fault_id: str) -> Path:
        """Written by the supervisor after it resumes a frozen worker, and polled by the worker.
        A frozen process cannot poll, so the first successful read is necessarily after the thaw."""
        return self.path / f"thawed-{fault_id}"

    def pid_path(self, recovery_index: int, role: str = "worker") -> Path:
        """Where a SUT process names its own pid. `pid-<n>` belongs to the worker under test and
        to nobody else: the proxy aims kills and freezes by it, so a second process that wrote the
        same file — the successor in a zombie cell, started from the same cursor — would turn a
        freeze of the holder into a freeze of the idle observer beside it."""
        name = f"pid-{recovery_index}" if role == "worker" else f"pid-{role}-{recovery_index}"
        return self.path / "sut" / name

    def announce_pid(self, recovery_index: int, role: str = "worker") -> None:
        self.pid_path(recovery_index, role).write_text(str(os.getpid()), encoding="utf8")

    def outage_marker(self) -> Path:
        """`provider_outage`: how many more model calls fail (§11.5). Trial-owned for the same reason
        the fault log is — a worker killed or restarted mid-outage must not end the outage early."""
        return self.path / "provider_outage"

    def outage_remaining(self) -> int:
        marker = self.outage_marker()
        try:
            return int(marker.read_text(encoding="utf8").strip() or 0) if marker.exists() else 0
        except ValueError:
            return 0

    def set_outage_remaining(self, n: int) -> None:
        _durably_write(self.outage_marker(), str(max(0, n)))

    def alternate_marker(self) -> Path:
        """`model_reask_alternate`: the trial-owned flag the scripted provider consults (§13.3).

        Trial-owned rather than worker-owned, and a file rather than an environment variable,
        because the successor is a *different process* that must see the arming its predecessor's
        fault performed — the same reason the fault log is a file. The provider stays a pure
        function of (request content, flag): no per-fingerprint ask counter, no per-trial counter.
        """
        return self.path / "alternate-armed"

    @property
    def alternate_armed(self) -> bool:
        """Non-empty, not merely present. `_clear` can only *empty* a file Windows still holds
        open, so existence alone would leave a reused trial directory permanently armed — the
        same class of bug as the reused schedule that made every entry read as already spent."""
        marker = self.alternate_marker()
        return marker.exists() and marker.stat().st_size > 0

    @classmethod
    def from_env(cls) -> "TrialDir":
        path = os.environ.get(cls.ENV)
        if not path:
            raise RuntimeError(f"{cls.ENV} is not set; a SUT is always started with a trial dir")
        return cls(path)

    # --- supervisor side -----------------------------------------------------
    def write_cursor(self, cursor: Cursor) -> None:
        _durably_write(self.cursor_path, cursor.model_dump_json(indent=2))

    def read_cursor(self) -> Cursor:
        return Cursor.model_validate_json(self.cursor_path.read_text(encoding="utf8"))

    # --- firing site side ----------------------------------------------------
    def append_observation(self, obs: Observation) -> None:
        _durably_append(self.observations_path, obs.model_dump_json())

    def append_fault(self, row: FaultFired) -> None:
        _durably_append(self.faults_path, row.model_dump_json())

    def observations(self) -> list[Observation]:
        return [Observation.model_validate(d) for d in _read_jsonl(self.observations_path)]

    def faults(self) -> list[FaultFired]:
        return [FaultFired.model_validate(d) for d in _read_jsonl(self.faults_path)]

    def fired_ids(self) -> set[str]:
        """Entries already spent. Rebuilt at process start, because the process that spent them
        is gone."""
        return {row.fault_id for row in self.faults()}

    def occurrence_counts(self) -> dict[tuple[str, str], int]:
        """The trial-wide counter, replayed from disk. This is what lets `occurrence: 2` mean
        "after the restart" — the semantics the cross-restart triggers are built on."""
        counts: dict[tuple[str, str], int] = {}
        for obs in self.observations():
            key = (obs.landmark, obs.boundary)
            counts[key] = counts.get(key, 0) + 1
        return counts


def _truncate(path: Path) -> None:
    """Remove a file, or empty it if something still holds it open. Either satisfies the caller:
    what `fresh` needs is that nothing is read back, not that the inode is gone."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        try:
            path.write_text("", encoding="utf8")
        except OSError:
            pass


def _durably_write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())


def _durably_append(path: Path, line: str) -> None:
    """Append and fsync, before anything irreversible happens next — as one write at the end of
    the file as the OS sees it. The logs have more than one writing process (the proxy and the
    SUT's shim both observe; so do Keel's non-worker roles), and Windows' `open(..., "a")` is a
    seek to the end and then a write, which another process can land between: three writers of
    1500 lines each lost 522 and tore 221, and one torn line took a bench run down."""
    fd = _open_append(path)
    try:
        os.write(fd, (line + "\n").encode("utf8"))
        os.fsync(fd)
    finally:
        os.close(fd)


if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _CreateFileW = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    _CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _CreateFileW.restype = wintypes.HANDLE
    _FILE_APPEND_DATA, _SHARE_ALL, _OPEN_ALWAYS, _NORMAL = 0x0004, 0x7, 4, 0x80

    def _open_append(path: Path) -> int:
        # Append access without write access: every write goes to end-of-file, placed by the
        # file system in the same step (WriteFile's docs: the same as offset 0xFFFFFFFF).
        handle = _CreateFileW(str(path), _FILE_APPEND_DATA, _SHARE_ALL, None, _OPEN_ALWAYS, _NORMAL, None)
        if handle is None or handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return msvcrt.open_osfhandle(handle, 0)  # binary, and no CRT seek before each write

else:

    def _open_append(path: Path) -> int:
        return os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)  # one write(), one append


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
