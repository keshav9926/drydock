"""The context projection: what the model has been shown, as the journal records it (§16.2).

The fold, in seq order, of: the initial messages in `RUN_CREATED.args["messages"]` (if the run was
given any), each MODEL step's completed result (the assistant turn), each TOOL step's completed or
resolved-completed result (a `tool_result` turn naming its tool), reset to `[summary]` by a COMPACT
step's result. A request blob is never folded — it already contains the prior fold, and folding it
would count every message twice. A continuation boundary resets it too, to the summary its
`compact_seq` names (§10.8), which is what makes it rebuildable from the boundary alone.

One `apply` for the fold and for `ctx.context` (which reads it at the replay cursor), so the context
a program sends and the context the journal projects cannot drift apart.
"""

from __future__ import annotations

from typing import Any


def initial(args: Any) -> list[dict[str, Any]]:
    messages = args.get("messages") if isinstance(args, dict) else None
    return [dict(m) for m in messages] if isinstance(messages, list) else []


def summary(result: Any) -> dict[str, Any]:
    """A COMPACT outcome as the one message it leaves behind."""
    return {"role": "summary", "content": (result or {}).get("text", "") if isinstance(result, dict) else str(result)}


def apply(context: list[dict[str, Any]], kind: str, name: str, result: Any) -> list[dict[str, Any]]:
    """The context after one step's outcome is handed back. Kinds that show the model nothing —
    PLAN, SLEEP, NOW, APPROVAL, DELEGATE — leave it as it was."""
    if kind == "MODEL":
        message = result.get("message") if isinstance(result, dict) else None
        return [*context, dict(message or {"role": "assistant", "content": (result or {}).get("text", "")})]
    if kind == "TOOL":
        return [*context, {"role": "tool_result", "content": {"tool": name, "result": result}}]
    if kind == "COMPACT":
        return [summary(result)]
    return context
