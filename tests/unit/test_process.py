"""Killing and freezing from outside, on this platform (§11.2).

One regression: a process the proxy has just killed can still be opened for a few milliseconds —
`poll()` says alive — and refuses to be suspended or resumed with STATUS_PROCESS_IS_TERMINATING.
The supervisor resumes every live-looking process before killing it at trial end (a frozen process
cannot be killed until it is thawed), and that race took a whole bench run down at trial 154 of
1080. Gone-in-every-sense-that-matters is not an error, on either platform.
"""

from __future__ import annotations

import subprocess
import sys

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
