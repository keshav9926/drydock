"""The reference program and its tools — the Keel form of `tool_chain_1_effect` (§14.1).

    search [PURE] → create_issue [EXTERNAL | IDEMPOTENT] → answer

`create_issue` is registered twice, under one name, because the two registrations are the two
published bands of matrix v0 and the program must not be able to tell them apart:

    EXTERNAL    → `issues.create` (dedup: false)               no key sent      F0
    IDEMPOTENT  → `issues.upsert` (dedup: true, natural: true) Idempotency-Key  F1

The receiver is the World (`crashproof world`), reached over plain HTTP from an environment
variable. Keel never imports the harness — the World is an external service to this program exactly
as a real issue tracker would be, which is also what lets day 3's adapter hand the same endpoints to
LangGraph and get a comparable trial.

Run it with:  keel worker --app keel.agents.demo:app
"""

from __future__ import annotations

import asyncio
import json
import os
from http.client import HTTPConnection
from typing import Any
from urllib.parse import urlsplit

from keel.client import Keel, program
from keel.core.protocols import EffectClass, Idempotency, ProbeResult
from keel.effects.registry import ToolCtx, tool
from keel.providers.scripted import Decision, ScriptedProvider

WORLD_URL = os.environ.get("KEEL_WORLD_URL", "http://127.0.0.1:8600")
VARIANT = os.environ.get("KEEL_DEMO_VARIANT", "EXTERNAL")

CREATE_ENDPOINT = "issues.create"
UPSERT_ENDPOINT = "issues.upsert"


def _post(path: str, body: dict[str, Any], *, key: str | None = None, timeout: float = 10.0) -> Any:
    """One blocking POST. Blocking on purpose: a freeze that an event loop can cancel is a timeout,
    not a zombie, and the day-3 cell needs the request to leave the process (§11.2)."""
    parts = urlsplit(WORLD_URL)
    conn = HTTPConnection(parts.hostname or "127.0.0.1", parts.port or 80, timeout=timeout)
    try:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        conn.request("POST", path, body=json.dumps(body).encode(), headers=headers)
        resp = conn.getresponse()
        return json.loads(resp.read() or b"null")
    finally:
        conn.close()


async def _call(endpoint: str, args: dict[str, Any], *, key: str | None = None) -> Any:
    path = "/" + endpoint.replace(".", "/", 1)
    return await asyncio.to_thread(_post, path, args, key=key)


@tool(effect=EffectClass.PURE, timeout=1.0)
async def search(args: dict[str, Any], tctx: ToolCtx) -> dict[str, Any]:
    """Read-only: re-executable, and its recorded result is reused on replay."""
    return await _call("kv.search", {"q": args.get("q", "")})


@tool(
    effect=EffectClass.EXTERNAL,
    resolution="probe",
    timeout=1.0,
    idempotency=Idempotency.NONE,
    name="create_issue",
)
async def create_issue_external(args: dict[str, Any], tctx: ToolCtx) -> dict[str, Any]:
    """Non-idempotent create against a receiver that honours nothing. No key is sent — that is what
    `key_source = none` means, and synthesising one here would be the adapter cheating (§13.6)."""
    return await _call(CREATE_ENDPOINT, args)


@create_issue_external.probe_hook
async def _probe_create_issue(effect_key: str, args: dict[str, Any], tctx: Any) -> ProbeResult:
    """Ask the receiver, do not guess. Point-in-time by construction: a zombie request the World
    applies after this returns is a duplicate the probe could not have seen (§8.4)."""
    answer = await asyncio.to_thread(
        _post,
        "/oracle/probe",
        {"endpoint": CREATE_ENDPOINT, "effect_key": effect_key, "args": dict(args)},
    )
    if answer["verdict"] == "COMMITTED":
        return ProbeResult(
            "COMMITTED",
            evidence=answer["evidence"],
            result=answer["result"],
            external_ref=answer.get("external_ref"),
        )
    return ProbeResult(answer["verdict"], evidence=answer["evidence"])


@tool(
    effect=EffectClass.IDEMPOTENT,
    timeout=1.0,
    idempotency=Idempotency.KEY,
    name="create_issue",
)
async def create_issue_idempotent(args: dict[str, Any], tctx: ToolCtx) -> dict[str, Any]:
    """The same create against a receiver that deduplicates. The key is `effect_key`, which is
    stable across attempts and recoveries by derivation, so a re-run after a crash is applied once
    — the only thing a fence cannot buy, because a fence cannot reach a third party (§8.4)."""
    return await _call(UPSERT_ENDPOINT, args, key=tctx.effect_key)


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
            # The tool's name travels with its result because the decision script is keyed on the
            # ordered (tool, occurrence) pairs already answered — never on a counter, and never on
            # the content of a result (§13.2). Both exclusions are what keep a runtime that
            # duplicates an effect scored on the duplicate rather than on a broken script.
            {"role": "tool_result", "content": {"tool": call.name, "result": result}},
        ]
    return {"answer": "step limit reached"}


SCRIPT = [
    Decision(text="searching", tool="search", args={"q": "flaky test in ci"}),
    Decision(
        text="filing",
        tool="create_issue",
        args={"title": "CI flake: test_retry", "body": "see search hits"},
    ),
    Decision(text="filed the issue"),
]


def create_issue_tool(variant: str = VARIANT):
    """The band under test. One name, two registrations, and the program cannot tell which."""
    if variant not in ("EXTERNAL", "IDEMPOTENT"):
        raise ValueError(f"unknown variant {variant!r}: EXTERNAL | IDEMPOTENT")
    return create_issue_external if variant == "EXTERNAL" else create_issue_idempotent


def build(dsn: str | None = None, *, variant: str = VARIANT) -> Keel:
    return Keel(
        dsn or os.environ.get("KEEL_DSN", "postgresql://keel:keel@localhost:5432/keel"),
        provider=ScriptedProvider(SCRIPT),
        tools=[search, create_issue_tool(variant)],
        programs=[tool_chain],
    )


app = build()
