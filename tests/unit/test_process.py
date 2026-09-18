"""Killing and freezing from outside, on this platform (§11.2).

One regression: a process the proxy has just killed can still be opened for a few milliseconds —
`poll()` says alive — and refuses to be suspended or resumed with STATUS_PROCESS_IS_TERMINATING.
The supervisor resumes every live-looking process before killing it at trial end (a frozen process
cannot be killed until it is thawed), and that race took a whole bench run down at trial 154 of
1080. Gone-in-every-sense-that-matters is not an error, on either platform.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from crashproof.faults import process


def test_resuming_a_process_that_is_terminating_is_not_an_error() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        process.kill(proc.pid)
        # Immediately, while the OS may still be tearing it down: the exact instant `_stop_all` hit.
        process.resume(proc.pid)
        process.suspend(proc.pid)
        proc.wait(timeout=10)
        process.resume(proc.pid)  # and once it is fully gone, the same answer
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_a_self_freeze_does_not_pass_the_boundary_before_the_thaw(tmp_path, monkeypatch) -> None:
    """The boundary is not passed until the supervisor's thaw marker exists — a Restate smoke's frozen
    attempt once sent its request 17 ms after its fault row, before parking existed."""
    import threading
    import time

    marker = tmp_path / "thaw"
    thawed_at: list[float] = []

    def thaw() -> None:
        thawed_at.append(time.monotonic())  # before the write, so a return after the write finds it
        marker.write_text("1", encoding="utf8")

    threading.Timer(0.3, thaw).start()
    process.freeze_self(marker)
    # Ordered by the thaw itself, not by a duration: a stalled test thread cannot make this pass or fail.
    assert thawed_at and time.monotonic() >= thawed_at[0]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX stop/continue")
def test_a_freeze_the_supervisor_finished_before_the_worker_parked_does_not_stop_it_for_ever(tmp_path) -> None:
    """The race behind week 2's four stuck Restate trials: the supervisor stops and resumes the worker
    before the worker's own freeze call runs. A self-SIGSTOP there would stop it with nobody left to
    resume it; parking on the marker returns as soon as the marker exists."""
    import signal
    import subprocess
    import time

    marker = tmp_path / "thaw"
    ready = tmp_path / "ready"
    script = "; ".join([
        "import pathlib, time, sys",
        "from crashproof.faults import process",
        f"pathlib.Path({str(ready)!r}).write_text('1')",
        "time.sleep(0.5)",  # the supervisor's stop + resume land in here
        f"process.freeze_self(pathlib.Path({str(marker)!r}))",
        "sys.exit(0)",
    ])
    child = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = time.monotonic() + 20
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        os.kill(child.pid, signal.SIGSTOP)
        time.sleep(0.2)
        os.kill(child.pid, signal.SIGCONT)
        marker.write_text("1", encoding="utf8")
        assert child.wait(timeout=10) == 0
    finally:
        if child.poll() is None:
            child.kill()
