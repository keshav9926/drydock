"""The matrix page in HTML (§26.4): the Markdown page converted, so these check the conversion —
it is deterministic, it drops no cell, and nothing from a row reaches the page as markup.
"""

from __future__ import annotations

import re

from crashproof.report import html, markdown
from crashproof.report.matrix import fold
from tests.unit.test_report_pages import _rows


def _pages(rows: list[dict]) -> tuple[str, str]:
    args = dict(workload="w", title="t", sources=[("bench/results/t", rows)])
    return markdown.render(fold(rows), **args), html.render(fold(rows), **args)


def test_the_html_page_is_a_pure_function_of_its_rows() -> None:
    rows = _rows(3, keel_commit="a83c322")
    assert html.render(fold(rows), workload="w", title="t") == html.render(fold(rows), workload="w", title="t")
    _, page = _pages(rows)
    assert "Rows through 2026-09-10T00:26:42+00:00" in page, "the page's only date is read from the rows"
    assert "<script" not in page and "http" not in page, "no script, no external resource"


def test_every_table_row_and_heading_of_the_markdown_page_is_on_the_html_page() -> None:
    rows = _rows(3, keel_commit="a83c322")
    rows[1] = {**rows[1], "verdicts": {**rows[1]["verdicts"], "S1": "FAIL"},
               "counterexamples": [{"invariant": "S1", "detail": "applied twice"}]}
    md, page = _pages(rows)
    table_rows = [line for line in md.split("\n") if line.startswith("|") and not line.startswith("|---")]
    assert page.count("<tr>") == len(table_rows)
    headings = re.findall(r"^#{1,3} (.*)$", md, re.M)
    assert re.findall(r"<h[123]>(.*?)</h[123]>", page) == [html._inline(h) for h in headings]
    for cell_id in fold(rows):
        assert f"<code>{cell_id}</code>" in page, "every cell the Markdown page names"
    assert '<span class="fail" title="S1 FAIL">S1✗</span>' in page
    assert "Minimum detectable difference" in page and "You only ran this thirty times" in page


def test_nothing_from_a_row_reaches_the_page_as_markup() -> None:
    rows = _rows(1)
    rows[0] = {**rows[0], "cell_id": "keel.default.EXTERNAL.<b>x</b>", "verdicts": {**rows[0]["verdicts"], "S1": "FAIL"},
               "counterexamples": [{"invariant": "S1", "detail": "<script>alert(1)</script> & more"}]}
    _, page = _pages(rows)
    assert "<script>" not in page and "<b>x</b>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in page
    assert "<code>keel.default.EXTERNAL.&lt;b&gt;x&lt;/b&gt;</code>" in page


def test_a_table_cell_is_split_where_markdown_py_joined_it() -> None:
    """`worker_count=1|2` is one pin, printed as one cell."""
    assert html._cells("| `keel.default` | lease_ttl_s=2, worker_count=1|2 |") == [
        "`keel.default`", "lease_ttl_s=2, worker_count=1|2"]
    assert html._cells("|  | recovery=self |") == ["", "recovery=self"]
