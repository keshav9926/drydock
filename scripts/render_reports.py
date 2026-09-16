"""Re-render every published page in bench/reports/ from the committed rows in bench/results/.

Every page is a pure function of its rows, so the output is byte-identical to what is committed
unless the rows or the renderer changed. CI runs this and then `git diff --exit-code -- bench/reports`:
a change to crashproof/report or crashproof/stats that silently changes a published page fails there,
on the commit that made it, rather than going stale behind a green build.

    uv run python scripts/render_reports.py      # from the repository root

This is the one list of which rows back which page; each entry is the exact command that renders it.
"""

from __future__ import annotations

import subprocess
import sys

RESULTS = ("matrix_v0", "tier1a", "tier1p", "reask_alternate", "w5", "w5_pre")
COMPARED = {"matrix_v0": "compare_keel_vs_langgraph_sync.md", "tier1a": "compare_tier1a_keel_vs_langgraph_sync.md",
            "tier1p": "compare_tier1p_keel_vs_langgraph_sync.md", "w5": "compare_w5_keel_vs_langgraph_sync.md",
            "w5_pre": "compare_w5_pre_keel_vs_langgraph_sync.md"}

PAGES: list[list[str]] = [
    *(["report", f"bench/results/{name}", "--out", f"bench/reports/{name}.md"] for name in RESULTS),
    *(
        ["compare", f"bench/results/{name}", "--a", "keel.*", "--b", "langgraph.sync.*", "--out", f"bench/reports/{page}"]
        for name, page in COMPARED.items()
    ),
    ["agree", "--shim", "bench/results/matrix_v0", "--shim", "bench/results/tier1a",
     "--proxy", "bench/results/tier1p", "--out", "bench/reports/agreement_tier1p.md"],
]


def main() -> None:
    for argv in PAGES:
        subprocess.run([sys.executable, "-m", "crashproof.cli.main", *argv], check=True)


if __name__ == "__main__":
    main()
