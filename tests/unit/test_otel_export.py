"""The OTel export (§19.7): a projection of the journal into spans, and those spans as OTLP/JSON.

Deterministic ids, so a re-export is byte-identical; a crash is a second epoch span that splits the
trace, never a second copy of the work memoized before it; MODEL attempts carry the GenAI names a
Langfuse *generation* is made of; and `keel otel --tree` hangs a child under its DELEGATE attempt.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from keel import Keel, program
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import Decision, ScriptedProvider
from keel.runtime.delegation import Delegation
from keel.state.spans import otlp, span_id, spans
from tests.property.journals import build, run_to_completion


def _flat(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for r in doc["resourceSpans"] for scope in r["scopeSpans"] for s in scope["spans"]]


def _attr(span: dict[str, Any], key: str) -> Any:
    for a in span["attributes"]:
        if a["key"] == key:
            (value,) = a["value"].values()
            return value
    return None


@pytest.mark.parametrize("crash", [False, True])
async def test_a_run_is_one_trace_its_epochs_split_it_and_nothing_is_counted_twice(crash: bool) -> None:
    rig = build(effect_class="EXTERNAL", dedup=True, tool_calls=2, crash_after_effect=crash)
    events = await rig.keel.events(await run_to_completion(rig))
    doc = otlp(spans(events))
    flat = _flat(doc)

    assert json.dumps(otlp(spans(events)), sort_keys=True) == json.dumps(doc, sort_keys=True), "re-export is identical"
    assert {s["traceId"] for s in flat} == {events[0].env.trace_id.hex} and all(len(s["spanId"]) == 16 for s in flat)
    ids = {s["spanId"] for s in flat}
    [root] = [s for s in flat if "parentSpanId" not in s]
    assert root["name"].startswith("run "), "one root: the run"
    assert all(s.get("parentSpanId", next(iter(ids))) in ids for s in flat), "every parent is exported too"
    assert all(int(s["startTimeUnixNano"]) <= int(s["endTimeUnixNano"]) for s in flat)

    started = [e for e in events if e.type == "STEP_ATTEMPT_STARTED"]
    attempts = [s for s in flat if _attr(s, "keel.attempt_no") is not None]
    assert len(attempts) == len(started), "one span per paid attempt; a memoized step emits none"
    epochs = [s for s in flat if s["name"].startswith("epoch ")]
    assert len(epochs) == (2 if crash else 1), "a crash is a second epoch span"
    models = [s for s in attempts if _attr(s, "keel.kind") == "MODEL"]
    assert models and all(_attr(s, "gen_ai.usage.input_tokens") for s in models), "a generation per model call"
    if crash:
        [crashed] = [s for s in attempts if s["status"]["code"] == 2]
        assert _attr(crashed, "keel.outcome") in ("STEP_AMBIGUOUS", "STEP_FAILED")
        assert crashed["parentSpanId"] == epochs[0]["spanId"], "the lost attempt stays in the epoch that lost it"


@program(name="otel_child", version="1.0")
async def child(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    return {"answer": (await ctx.model([{"role": "user", "content": "c"}], name="c")).text}


@program(name="otel_parent", version="1.0")
async def parent(ctx: Any, args: dict[str, Any]) -> Any:
    return (await ctx.delegate(Delegation(program="otel_child"))).status


async def test_the_cli_exports_a_tree_and_posts_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from keel.cli import main as cli

    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), provider=ScriptedProvider([Decision(text="x")] * 3),
             programs=[parent, child], clock=clock)
    handle = await k.start(parent, {})
    await k.worker(worker_id="w", lease_ttl=2.0).run_until_idle(timeout=10)
    [row] = await k.journal.delegations(handle.run_id)

    queued: list[Any] = []
    monkeypatch.setattr(cli, "_load_app", lambda *_: k)
    monkeypatch.setattr(cli, "_run", queued.append)
    out = tmp_path / "spans.json"
    assert CliRunner().invoke(cli.app, ["otel", str(handle.run_id), "--tree", "--out", str(out)]).exit_code == 0
    await queued.pop()
    flat = _flat(json.loads(out.read_text(encoding="utf8")))
    assert len({s["traceId"] for s in flat}) == 1, "the tree is one trace"
    [child_run] = [s for s in flat if s["name"] == "run otel_child"]
    assert child_run["parentSpanId"] == span_id(handle.run_id, row.parent_step_index, 1), "under its DELEGATE"

    received: dict[str, Any] = {}

    class Collector(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
            received["auth"] = self.headers.get("Authorization")
            received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            return None

    server = http.server.HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.handle_request, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/traces"
    args = ["otel", str(handle.run_id), "--endpoint", url, "--header", "Authorization=Basic a2VlbA=="]
    assert CliRunner().invoke(cli.app, args).exit_code == 0
    await queued.pop()
    server.server_close()
    assert received["auth"] == "Basic a2VlbA==" and _flat(received["body"])
