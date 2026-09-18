"""The matrix page as one self-contained HTML file (§26.4, `crashproof report --fmt html`).

It is the Markdown page, converted — not a second renderer over the same cells. §15.11 rule 10 says
the two are derived from the same rows; converting the one page makes them the same *text*, so the
numbers, the N/A marks, the counterexamples, the MDD tables, the FAQ and the provenance block cannot
drift apart, and a page that re-renders byte-identically in Markdown does so in HTML too.

The converter knows exactly the subset `markdown.py` writes — `#`-headings, paragraphs, pipe tables,
`code`, **bold**, *italic*, `<br>` inside a cell — and escapes everything else as text. Table rows
are split on `" | "`, the separator `markdown.py` joins with, so a pin like `worker_count=1|2` stays
one cell (GitHub's renderer splits it). No script, no external stylesheet, no font: the file is the
page.
"""

from __future__ import annotations

import html
import re
from typing import Any

from crashproof.report import markdown
from crashproof.report.matrix import CellSummary

_HEADING = re.compile(r"(#{1,3}) (.*)")
_SEPARATOR = re.compile(r"\|(\s*:?-+:?\s*\|)+")
_VERDICT = re.compile(r"\b([A-Z]\d+)([✓✗·])")
_VERDICT_CLASS = {"✓": ("pass", "PASS"), "✗": ("fail", "FAIL"), "·": ("na", "N/A")}


def render(
    cells: dict[str, CellSummary],
    *,
    workload: str,
    title: str = "matrix v0",
    sources: list[tuple[str, list[dict[str, Any]]]] = (),
) -> str:
    """The same arguments as `markdown.render`, and the same page."""
    return page(markdown.render(cells, workload=workload, title=title, sources=sources), title=title)


def page(md: str, *, title: str) -> str:
    head, tail = TEMPLATE.split("{body}")
    return head.replace("{title}", html.escape(title)) + "\n".join(_blocks(md.split("\n"))) + tail


def _blocks(lines: list[str]) -> list[str]:
    out: list[str] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|"):
            flush()
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            out.append(_table(lines[i:j]))
            i = j
            continue
        if heading := _HEADING.fullmatch(line):
            flush()
            n = len(heading[1])
            out.append(f"<h{n}>{_inline(heading[2])}</h{n}>")
        elif line.strip():
            para.append(line)
        else:
            flush()
        i += 1
    flush()
    return out


def _cells(row: str) -> list[str]:
    return row.rstrip()[2:-2].split(" | ")


def _table(rows: list[str]) -> str:
    head, *body = [_cells(r) for r in rows if not _SEPARATOR.fullmatch(r.strip())]
    heads = [head]
    # The grid prints each column's recovery mechanism and claims as a first row with an empty stub:
    # it belongs to the column header, and a screen reader should announce it as one.
    if body and body[0][0] == "":
        heads.append(body.pop(0))
    thead = "".join(
        "<tr>" + "".join(f'<th scope="col">{_inline(c)}</th>' for c in r) + "</tr>" for r in heads
    )
    tbody = "\n".join(
        f'<tr><th scope="row">{_inline(r[0])}</th>' + "".join(f"<td>{_inline(c)}</td>" for c in r[1:]) + "</tr>"
        for r in body
    )
    return f'<div class="scroll"><table>\n<thead>{thead}</thead>\n<tbody>\n{tbody}\n</tbody>\n</table></div>'


def _inline(text: str) -> str:
    """Escape first, then mark up: nothing from a row — a cell id, a counterexample's detail — can
    reach the page as markup. `<br>` is the one tag `markdown.py` writes and the one put back."""
    parts = re.split(r"(`[^`]+`)", html.escape(text, quote=False).replace("&lt;br&gt;", "<br>"))
    for k, part in enumerate(parts):
        if k % 2:
            parts[k] = f"<code>{part[1:-1]}</code>"
            continue
        part = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", part)
        part = re.sub(r"(?<![\w*])\*([^\s*][^*]*?)\*(?![\w*])", r"<em>\1</em>", part)
        parts[k] = _VERDICT.sub(_verdict, part)
    return "".join(parts)


def _verdict(m: re.Match[str]) -> str:
    cls, word = _VERDICT_CLASS[m[2]]
    return f'<span class="{cls}" title="{m[1]} {word}">{m[0]}</span>'


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · crashproof</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #fbfbf9; --fg: #1d1f21; --muted: #5b6168; --rule: #d9dad6; --head: #f0f0ec;
  --code: #eeeeea; --pass: #1f7a3a; --fail: #b3261e; --na: #80868b; --link: #1a5fb4;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161819; --fg: #e4e4e0; --muted: #a3a8ad; --rule: #34383b; --head: #202325;
    --code: #26292b; --pass: #6fcf87; --fail: #ff8a80; --na: #8d9398; --link: #8ab4f8;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 1400px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0 0 .5rem; }
h2 { font-size: 1.2rem; margin: 2.2rem 0 .6rem; padding-top: .8rem; border-top: 1px solid var(--rule); }
h3 { font-size: 1.05rem; margin: 1.6rem 0 .5rem; }
p { max-width: 78ch; }
code {
  font: .88em/1.4 ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  background: var(--code); padding: .05em .3em; border-radius: 3px;
}
a { color: var(--link); }
.scroll { overflow-x: auto; margin: .8rem 0 1.2rem; border: 1px solid var(--rule); border-radius: 6px; }
table { border-collapse: collapse; font-size: .85rem; font-variant-numeric: tabular-nums; }
th, td { padding: .45rem .6rem; border-bottom: 1px solid var(--rule); text-align: left; vertical-align: top; }
thead th { background: var(--head); font-weight: 600; }
thead tr + tr th { font-weight: 400; color: var(--muted); font-size: .8rem; }
tbody th[scope="row"] { position: sticky; left: 0; background: var(--bg); font-weight: 400; white-space: nowrap; }
tbody tr:last-child > * { border-bottom: 0; }
td { min-width: 14ch; }
.pass, .fail, .na { white-space: nowrap; }
.pass { color: var(--pass); }
.fail { color: var(--fail); font-weight: 700; }
.na { color: var(--na); }
footer { max-width: 1400px; margin: 0 auto; padding: 16px; color: var(--muted); font-size: .8rem; border-top: 1px solid var(--rule); }
</style>
</head>
<body>
<main>
{body}
</main>
<footer>
Rendered by <code>crashproof report --fmt html</code> from the same fold as the Markdown page, and pure
over the rows it names under Provenance: re-rendering them is byte-identical. The rows themselves are the
<code>results.jsonl</code> beside the page, not embedded in it.
</footer>
</body>
</html>
"""
