"""The timeline page (§26.2): a journal folded into BEFORE CRASH / AFTER RESTART, in the browser.

The fold is JavaScript, so the test runs it: the page's own script under `node` (GitHub's runners
and this machine both have it; without it these skip), against the recorded journals in
`tests/journals` and the demo's golden trials, checked against `keel.state.fold`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from crashproof.demo import EMPTY, timeline_page
from keel.replay.fixtures import load_all
from keel.state.fold import fold as keel_fold
from tests.unit.test_demo import load

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "keel" / "api" / "static" / "timeline.html"
JOURNALS = {f.name: f for f in load_all(ROOT / "tests" / "journals")}


def _timeline(doc: object) -> dict:
    """The page's own script, run under node against `doc`: what the page would show."""
    if shutil.which("node") is None:
        pytest.skip("node is not installed; the timeline page's fold is JavaScript")
    script = re.search(r"<script>\n(.*?)</script>", PAGE.read_text(encoding="utf8"), re.S)[1]
    driver = "\nprocess.stdout.write(JSON.stringify(timeline(JSON.parse(require('fs').readFileSync(0, 'utf8')))));"
    done = subprocess.run(["node", "-e", script + driver], input=json.dumps(doc), capture_output=True,
                          text=True, encoding="utf8", check=True)
    return json.loads(done.stdout)


def _lines(column: dict) -> list[str]:
    return [" ".join(r["cells"]) for r in column["rows"]]


def test_the_page_splits_a_recorded_crash_where_the_orphaned_recovery_starts() -> None:
    doc = json.loads((ROOT / "tests" / "journals" / "recovered_tool_chain.jsonl").read_text(encoding="utf8"))
    view = _timeline(doc)
    assert view["before"]["title"].startswith("BEFORE CRASH · state @ seq 14 · epoch 1")
    assert "#3 TOOL create_issue [EXTERNAL] RUNNING attempt 1 " in _lines(view["before"])
    assert view["before"]["cut"] == ["✂ last append seq 14 · #3 started, no outcome"]
    after = _lines(view["after"])
    assert view["after"]["title"] == "AFTER RESTART · epoch 2 · cause=ORPHANED"
    assert after[0] == "15 - RECOVERY_STARTED cause=ORPHANED from_seq=14 "
    assert after[1].startswith("▸ #0 #1 #2 memo 3 steps returned from the journal")
    assert "17 #3 STEP_RESOLVED RESOLVED_COMPLETED via probe recovered" in after
    assert "18 - RECOVERY_COMPLETED live_from_step=4 replayed_steps=4 " in after
    assert "19 #4 STEP_INTENDED MODEL decide live" in after


@pytest.mark.parametrize("name", sorted(JOURNALS))
def test_the_page_marks_origin_as_keel_events_does(name: str) -> None:
    """The page's fold is display-only, and it must still agree with the real one on `origin`."""
    fixture = JOURNALS[name]
    doc = json.loads((ROOT / "tests" / "journals" / f"{name}.jsonl").read_text(encoding="utf8"))
    state = keel_fold(fixture.events)
    for row in _timeline(doc)["after"]["rows"]:
        if row["cells"][0].isdigit() and row["cells"][1] != "-":
            step = int(row["cells"][1][1:])
            assert row["origin"] == state.origin(step, state.latest_epoch), row["cells"]
    if name == "clean_tool_chain":
        assert _timeline(doc)["before"] is None, "nothing crashed, so there is no BEFORE column"


def test_the_demo_embeds_the_trial_and_its_verdicts_into_keels_page() -> None:
    page = timeline_page(*load("keel"))
    assert EMPTY not in page and page.count('<script id="journal"') == 1
    data = re.search(r'<script id="journal" type="application/json">(.*?)</script>', page, re.S)[1]
    assert "<" not in data, "nothing in the journal can close its script element"
    view = _timeline(json.loads(data))
    assert view["verdict"]["world"].startswith("World  issues.create#1  receipts=1  applied=1")
    assert [s["text"] for s in view["verdict"]["strip"]][:2] == ["S1✓", "S2✓"]
    assert view["before"]["cut"][0] == "✂ kill @ after:tool_effect · landmark tool:create_issue · trial t-7"
    assert "RECOVERY_STARTED" in _lines(view["after"])[0]


def test_a_runtime_with_no_journal_gets_a_page_that_says_so() -> None:
    page = timeline_page(*load("langgraph"))
    view = _timeline(json.loads(re.search(r'type="application/json">(.*?)</script>', page, re.S)[1]))
    assert view["note"].startswith("No journal exposed") and view["after"] is None
    assert "receipts=2  applied=2" in view["verdict"]["world"]
