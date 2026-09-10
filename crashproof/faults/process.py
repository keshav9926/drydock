"""Killing and freezing a process, on both platforms the harness runs on.

A freeze must be a real freeze. The zombie cell exists to observe a worker that is *alive*, still
holding a committed STARTED, and still able to complete an outgoing request after its lease has
expired — so a `time.sleep` that leaves the heartbeat task running would measure nothing (that is
the stalled-handler variant the specification stages at V2, §27.7). What is needed is a whole
process, all threads, stopped.

POSIX has `SIGSTOP` for exactly this. Windows has no signal for it; `NtSuspendProcess` is the
equivalent and takes the same two calls. Both are here rather than in the injector, because the
shim freezes itself and the supervisor thaws it, and the two must agree.
"""

from __future__ import annotations

import os
import signal
import sys

WINDOWS = sys.platform == "win32"
KILL_CODE = 137  # 128 + SIGKILL, the exit status a SIGKILLed process reports on POSIX


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
        with _suppress_gone():
            os.kill(pid, signal.SIGKILL)


def suspend_self() -> None:
    """Stop every thread of this process. The supervisor is the only thing that can thaw it, which
    is why the fault row is written and fsynced first — it is the channel that asks."""
    if WINDOWS:
        _nt("NtSuspendProcess", _current_process())
    else:
        os.kill(os.getpid(), signal.SIGSTOP)


def resume(pid: int) -> None:
    if WINDOWS:
        handle = _open_process(pid)
        try:
            _nt("NtResumeProcess", handle)
        finally:
            _close(handle)
    else:
        with _suppress_gone():
            os.kill(pid, signal.SIGCONT)


def terminate(pid: int) -> None:
    """A polite stop: SIGTERM where there is one, and the drain path Keel installs answers it."""
    if WINDOWS:
        kill(pid)  # Windows has no SIGTERM for another process; the drain cells are day 4 (POSIX)
    else:
        with _suppress_gone():
            os.kill(pid, signal.SIGTERM)


# --- Windows plumbing --------------------------------------------------------
_PROCESS_SUSPEND_RESUME = 0x0800


def _nt(fn: str, handle: int) -> None:
    import ctypes

    status = getattr(ctypes.windll.ntdll, fn)(ctypes.c_void_p(handle))
    if status != 0:
        raise OSError(f"{fn} failed with NTSTATUS 0x{status & 0xFFFFFFFF:08x}")


def _current_process() -> int:
    import ctypes

    return ctypes.windll.kernel32.GetCurrentProcess()


def _open_process(pid: int) -> int:
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(_PROCESS_SUSPEND_RESUME, False, pid)
    if not handle:
        raise OSError(f"OpenProcess({pid}) failed: {ctypes.GetLastError()}")
    return handle


def _close(handle: int) -> None:
    import ctypes

    ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))


class _suppress_gone:
    """A process that has already exited is not an error here — it is the outcome we wanted."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, (ProcessLookupError, OSError))
