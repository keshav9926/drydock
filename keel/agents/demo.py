"""The day-1 reference program and its two tools — the Keel form of `tool_chain_1_effect`.

`search` is PURE, `create_issue` is EXTERNAL. The receiver here is a JSONL file, which is a
stand-in for day 2's World: it records every receipt with the effect key it was presented, so a
duplicate is visible from outside the runtime rather than on the runtime's own word.

Run it with:  keel worker --app keel.agents.demo:app
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from keel.client import Keel, program
from keel.core.protocols import EffectClass, Idempotency, ProbeResult
from keel.effects.registry import ToolCtx, tool
from keel.providers.scripted import Decision, ScriptedProvider

SINK = Path(os.environ.get("KEEL_DEMO_SINK", "keel-demo-sink.jsonl"))


def _receipts() -> list[dict[str, Any]]:
    if not SINK.exists():
        return []
    return [json.loads(line) for line in SINK.read_text(encoding="utf8").splitlines() if line.strip()]


@tool(effect=EffectClass.PURE, timeout=2.0)
async def search(args: dict[str, Any], tctx: ToolCtx) -> dict[str, Any]:
    """Read-only: re-executable, and its recorded result is reused on replay."""
    q = args.get("q", "")
    return {"hits": [f"{q} #1", f"{q} #2", f"{q} #3"]}


@tool(
    effect=EffectClass.EXTERNAL,
    resolution="probe",
    timeout=1.0,
    idempotency=Idempotency.NONE,
)
async def create_issue(args: dict[str, Any], tctx: ToolCtx) -> dict[str, Any]:
    """Non-idempotent create. The receipt is written (and flushed) BEFORE the response is computed,
    so a kill aimed at `after:tool_effect` really does land after the effect (§28.2's K11(a))."""
    receipt = {
        "effect_key": tctx.effect_key,
        "title": args.get("title"),
        "body": args.get("body"),
        "ts": datetime.now(UTC).isoformat(),
    }
    with SINK.open("a", encoding="utf8") as fh:
        fh.write(json.dumps(receipt) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    # The ack delay is read from the environment, never from the args: args feed the effect key,
    # and widening a demo's crash window must not change the identity of the effect (§3).
    delay = float(os.environ.get("KEEL_DEMO_DELAY_MS", "500")) / 1000
    if delay:
        await asyncio.sleep(delay)
    number = len(_receipts())
    return {"issue": number, "external_ref": f"issue#{number}"}


@create_issue.probe_hook
async def _probe_create_issue(effect_key: str, args: dict[str, Any], tctx: Any) -> ProbeResult:
    """Point-in-time: it answers 'has the receiver applied this key as of now'. A zombie request
    applied after the probe is a duplicate the probe could not see (§8.4)."""
    for i, r in enumerate(_receipts(), start=1):
        if r.get("effect_key") == effect_key:
            return ProbeResult(
                "COMMITTED",
                evidence=f"receipt for {effect_key} at {r['ts']}",
                result={"issue": i, "external_ref": f"issue#{i}"},
                external_ref=f"issue#{i}",
            )
    return ProbeResult("ABSENT", evidence=f"no receipt for {effect_key}")


@program(name="tool_chain", version="1.0")
async def tool_chain(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    task = args.get("task", "file an issue")
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    for _ in range(6):
        resp = await ctx.model(messages, name="decide")
        if not resp.tool_calls:
            return {"answer": resp.text}
        call = resp.tool_calls[0]
        result = await ctx.tool(call.name, **call.args)
        messages = [
            *messages,
            {"role": "assistant", "content": resp.text or call.name},
            {"role": "tool_result", "content": result},
        ]
    return {"answer": "step limit reached"}


SCRIPT = [
    Decision(text="searching", tool="search", args={"q": "lease test flaky"}),
    Decision(
        text="filing",
        tool="create_issue",
        args={"title": "flaky lease test", "body": "see search hits"},
    ),
    Decision(text="filed the issue"),
]


def build(dsn: str | None = None) -> Keel:
    return Keel(
        dsn or os.environ.get("KEEL_DSN", "postgresql://keel:keel@localhost:5432/keel"),
        provider=ScriptedProvider(SCRIPT),
        tools=[search, create_issue],
        programs=[tool_chain],
    )


app = build()
