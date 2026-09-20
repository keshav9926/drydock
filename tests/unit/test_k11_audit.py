"""K11(a)'s audit, pinned where §30 says it belongs: in CI (§30, §28.2).

Not the 300-seed run — one trial of each band, which is what CI can afford and what keeps the
instrument honest. The band that matters here is `mutant`: `scripts/_k11_world.py` defers the
receipt past the answer, which is exactly the implementation K11(a) exists to catch, and an audit
that does not convict it cannot be read as clearing the real one.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.k11_oracle_audit import run  # noqa: E402


@pytest.mark.parametrize(("band", "expected"), [("mutant", "VIOLATION"), ("held", "in window")])
def test_the_audit_convicts_a_world_that_logs_after_it_answers(band: str, expected: str, tmp_path) -> None:
    [row] = run(seeds=1, bands=(band,), calibration_seeds=1, quiet=True)
    assert row["outcome"] == expected, row
