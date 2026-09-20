"""A World for the K11(a) audit, optionally mis-ordered on purpose (§30, §28.2).

Run with no environment it is the ordinary World: `crashproof world`, nothing patched. With
`K11_MUTATE_GAP_MS` set it is the implementation K11(a) exists to catch — the receipt is written
`gap` milliseconds *after* the response has gone back to the caller, so a kill in between leaves a
client that was answered for a request the log does not have.

The mutant is the audit's calibration, not a product path: an audit that cannot fail on a broken
World says nothing about a correct one. Nothing in `crashproof/` is changed to make it possible;
the reordering lives here, in the test instrument.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

from crashproof.world import services


def _mutate(gap_s: float) -> None:
    """Answer first, log `gap_s` later — the ordering §28.2 forbids."""
    original_log = services.World._durably_log

    def deferred_log(self: Any, receipt: Any) -> None:
        self.receipts.append(receipt)  # in memory now; on disk later, if the process lives
        fh = getattr(self, "_fh", None)
        if fh is None:
            return

        def write() -> None:
            try:
                fh.write(receipt.as_json() + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            except (OSError, ValueError):
                pass

        threading.Timer(gap_s, write).start()

    services.World._durably_log = deferred_log  # type: ignore[method-assign]
    assert original_log is not services.World._durably_log


def main() -> int:
    gap_ms = os.environ.get("K11_MUTATE_GAP_MS")
    if gap_ms is not None:
        _mutate(float(gap_ms) / 1000.0)
    from crashproof.cli.main import app

    return int(app(sys.argv[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
