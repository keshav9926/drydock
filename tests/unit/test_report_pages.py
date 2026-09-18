"""What every published page says about where it came from, and that it says the same thing twice.

A page is a pure function of its rows: re-rendering them is byte-identical, which is what lets CI
check a committed page against the committed rows. And a page names the rows — the directory, how
many, the commits they ran at — because §29.3 asks whether a page's commits match its rows'.
"""

from __future__ import annotations

import re

from crashproof.report.markdown import render
from crashproof.report.matrix import fold
from tests.unit.test_agreement import KILL, _row


def _rows(n: int, **extra) -> list[dict]:
    return [{**_row(KILL, 7 + s, "shim"), "ended_at": 1_789_000_000.0 + s, **extra} for s in range(n)]


def test_a_page_is_a_pure_function_of_its_rows_and_names_them() -> None:
    rows = _rows(3, keel_commit="a83c322")
    page = render(fold(rows), workload="w", title="t", sources=[("bench/results/t", rows)])
    assert page == render(fold(rows), workload="w", title="t", sources=[("bench/results/t", rows)])
    assert "Generated" not in page
    assert "Rows through 2026-09-10T00:26:42+00:00 (the last trial's end)." in page
    assert "| `bench/results/t` | 3 | `a83c322` ×3 |" in page
    assert "dirty" not in page.split("## Provenance")[1].split("| config |")[0]


def test_rows_from_a_dirty_tree_are_flagged() -> None:
    rows = _rows(2, keel_commit="a83c322-dirty") + _rows(1, keel_commit="a83c322")
    page = render(fold(rows), workload="w", title="t", sources=[("r", rows)])
    assert "`a83c322-dirty` ×2 **dirty**" in page and "**2 row(s) ran from a dirty tree**" in page


def test_faq_3_claims_a_confirmation_tier_only_where_one_ran() -> None:
    screening = render(fold(_rows(31)), workload="w", title="t")
    assert "This page is the screening tier only" in screening, "n > 30 on screening seeds is not a confirmation"
    assert "Confirmation is automatic" not in screening
    confirmed_rows = [{**r, "seed": 100_000 + i} for i, r in enumerate(_rows(3))]
    confirmed = render(fold(_rows(30) + confirmed_rows), workload="w", title="t")
    assert "Confirmation is automatic where it matters" in confirmed
    assert "adapter_commit" not in screening, "no row carries one; keel_commit pins the adapters"


def test_a_confirmed_cell_prints_at_the_confirmation_n_with_screening_in_the_appendix() -> None:
    screening = _rows(30)
    screening[4] = {**screening[4], "verdicts": {**screening[4]["verdicts"], "S1": "FAIL"},
                    "counterexamples": [{"invariant": "S1", "detail": "twice"}]}
    confirmation = [{**r, "seed": 100_000 + i} for i, r in enumerate(_rows(300))]
    [cell] = fold(screening + confirmation).values()
    assert (cell.tier, cell.n, cell.screening.n) == ("confirmation", 300, 30)
    assert cell.verdicts["S1"] == "FAIL", "a FAIL at screening is never averaged away by more trials"
    assert [c["seed"] for c in cell.counterexamples] == [11]
    page = render(fold(screening + confirmation), workload="w", title="t")
    grid, appendix = page.split("## Appendix — the screening tier of the confirmed cells (§15.3)")
    assert "L1 300/300" in grid and "L1 30/30" in appendix.split("## Counterexamples")[0]


def test_the_commit_a_row_records_is_a_short_sha_marked_dirty_when_the_tree_is() -> None:
    from crashproof.runner.trial import current_commit

    assert re.fullmatch(r"[0-9a-f]{7,40}(-dirty)?", current_commit())
