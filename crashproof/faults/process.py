"""Killing and freezing a process, on both platforms the harness runs on.

A freeze must be a real freeze. The zombie cell exists to observe a worker that is *alive*, still
holding a committed STARTED, and still able to complete an outgoing request after its lease has
expired — so a `time.sleep` that leaves the heartbeat task running would measure nothing (that is
the stalled-handler variant the specification stages at V2, §27.7). What is needed is a whole
process, all threads, stopped.

POSIX has `SIGSTOP`, and a process may raise it on itself — which is what the specification
prescribes for `shim` mode, because it puts the freeze exactly at the boundary.

**Windows cannot do that.** `NtSuspendProcess` on the current process leaves a suspend state that a
later `NtResumeProcess` from the supervisor does not lift; the process stays frozen for good.
Verified directly: external suspend + external resume works, self-suspend + external resume does
not. So on Windows the freeze is aimed from outside, and the firing thread simply *parks* at the
boundary until the supervisor — which has already read the fault row — stops the whole process.
Nothing has been sent when the freeze lands either way, which is what the cell is about.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

WINDOWS = sys.platform == "win32"
KILL_CODE = 137  # 128 + SIGKILL, the exit status a SIGKILLed process reports on POSIX

#: An upper bound on the park, in case the supervisor never arrives. Not the normal exit: the
#: worker leaves as soon as the thaw marker appears. Well past the longest drawn pause (§13.4:
#: 4 x the arm's detection timeout — Restate's 7 s makes 28 s) plus the supervisor's detection.
PARK_S = 120.0


def die_now() -> None:
    """SIGKILL-equivalent, from inside. No atexit handlers, no `finally`, no lease release —
    a runtime that survives only because it was allowed to tidy up is not what is being tested."""
    os._exit(KILL_CODE)


def kill(pid: int) -> None:
    """From outside, for a process that will not die on its own."""
    if WINDOWS:
        import subprocess

        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True, check=False)
    else:
        _signal(pid, signal.SIGKILL)


def freeze_self(thaw_marker: "Path | None" = None) -> None:
    """Stop here, at the boundary, with nothing sent: park until the supervisor's thaw marker exists.

    The supervisor does the stopping, on both platforms: it reads the fault row, freezes this
    process from outside, waits out the pause, resumes it and only then writes the marker. So this
    thread just polls — and polling is what makes it exact, because a frozen process cannot poll, so
    the first successful read is necessarily after the thaw.

    **No self-`SIGSTOP`, on POSIX either.** It used to stop itself too, and that raced the supervisor:
    when the supervisor read the fault row and froze the process between the row's write and this
    thread's own `kill(getpid(), SIGSTOP)`, the self-stop ran *after* the supervisor's resume, and
    nothing ever resumed the process again. Four of sixty Restate `pause_past_ttl` trials sat stopped
    until the trial timed out — scored as Restate failing to recover (week 2, WSL).
    """
    deadline = time.monotonic() + PARK_S
    while time.monotonic() < deadline:
        if thaw_marker is not None and thaw_marker.exists():
            return
        time.sleep(0.01)


def suspend(pid: int) -> None:
    """Freeze another process, every thread of it."""
    if WINDOWS:
        _with_handle(pid, "NtSuspendProcess")
    else:
        _signal(pid, signal.SIGSTOP)


def resume(pid: int) -> None:
    if WINDOWS:
        _with_handle(pid, "NtResumeProcess")
    else:
        _signal(pid, signal.SIGCONT)


def terminate(pid: int) -> None:
    """A polite stop: SIGTERM where there is one, and the drain path Keel installs answers it."""
    if WINDOWS:
        kill(pid)  # Windows has no SIGTERM for another process; the drain cells are day 4 (POSIX)
    else:
        _signal(pid, signal.SIGTERM)


# --- Windows plumbing --------------------------------------------------------
_PROCESS_SUSPEND_RESUME = 0x0800
#: STATUS_PROCESS_IS_TERMINATING. A process the proxy has just `taskkill`ed can still be opened for
#: a few milliseconds — `poll()` says alive — and refuses to be suspended or resumed. That is the
#: outcome we wanted, not an error: the same rule `_ignore_gone` applies on POSIX.
_STATUS_PROCESS_IS_TERMINATING = 0xC000010A


def _with_handle(pid: int, fn: str) -> None:
    """Handles are pointer-sized; leaving ctypes to guess `c_int` truncates them on 64-bit."""
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    getattr(ntdll, fn).argtypes = [ctypes.c_void_p]

    handle = kernel32.OpenProcess(_PROCESS_SUSPEND_RESUME, 0, pid)
    if not handle:
        return  # the process is already gone, which is not an error here
    try:
        status = getattr(ntdll, fn)(handle) & 0xFFFFFFFF
        if status == _STATUS_PROCESS_IS_TERMINATING:
            return  # gone in every sense that matters
        if status != 0:
            raise OSError(f"{fn}({pid}) failed with NTSTATUS 0x{status:08x}")
    finally:
        kernel32.CloseHandle(handle)


def _signal(pid: int, sig: int) -> None:
    """POSIX `kill(0, …)` signals the caller's whole process group and `kill(-1, …)` every process
    the user owns; on Windows the same pids open nothing. A pid that names no one process is refused
    here, where every outside signal passes, so no caller can take down the supervisor with it."""
    if pid <= 0:
        return
    _ignore_gone(lambda: os.kill(pid, sig))


def _ignore_gone(action) -> None:
    """A process that has already exited is not an error here — it is the outcome we wanted."""
    try:
        action()
    except (ProcessLookupError, OSError):
        pass
