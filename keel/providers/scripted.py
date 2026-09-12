"""The scripted provider: decisions are a **pure function of request content** (Appendix A §8).

No per-trial counters — that is the whole point. If the provider counted calls, a restart would
re-ask the same question and get a different answer, and every "the runtime memoized correctly"
result would be an artefact of the fake model instead of a property of the runtime.

The MVP fingerprint is the ordered list of tool results already in the request. That is content,
it is stable across restarts, and it is enough to drive `tool_chain_1_effect`.

# ponytail: fingerprint = the tool-result chain only, and day 5 did not widen it. The benchmark's
# `model_reask_alternate` lives in the harness's own provider (`crashproof/adapters/keel.py`),
# which is what every arm shares — putting it here would have made the fault a property of Keel's
# provider rather than of the workload, and a fault only one arm can feel is not a comparison.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from pydantic import BaseModel, Field

from keel.core.hashing import canonical_json
from keel.providers.protocol import (
    Message,
    ModelChunk,
    ModelRequest,
    ModelResponse,
    ToolCall,
    Usage,
)


class Decision(BaseModel):
    """One scripted model turn: either call a tool, or answer."""

    text: str = ""
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)

    def stop_reason(self) -> str:
        return "tool_use" if self.tool else "end_turn"


def _tool_results(messages: Sequence[Message]) -> list[Any]:
    return [m.content for m in messages if m.role == "tool_result"]


class ScriptedProvider:
    name = "scripted"

    def __init__(self, decisions: Sequence[Decision | dict[str, Any]], *, model: str = "scripted-1") -> None:
        self._script = [d if isinstance(d, Decision) else Decision(**d) for d in decisions]
        self._model = model

    def _fingerprint(self, req: ModelRequest) -> str:
        return canonical_json(_tool_results(req.messages))

    def _decide(self, req: ModelRequest) -> tuple[int, Decision]:
        turn = len(_tool_results(req.messages))
        if turn >= len(self._script):
            return turn, Decision(text="(script exhausted)")
        return turn, self._script[turn]

    async def complete(self, req: ModelRequest) -> ModelResponse:
        turn, decision = self._decide(req)
        prompt_tokens = await self.count_tokens(req)
        out = len(canonical_json(decision.model_dump())) // 4
        calls = []
        if decision.tool:
            # deterministic from the fingerprint, never from a counter
            calls = [ToolCall(id=f"tu_{turn}", name=decision.tool, args=decision.args)]
        return ModelResponse(
            text=decision.text,
            tool_calls=calls,
            stop_reason=decision.stop_reason(),
            usage=Usage(input_tokens=prompt_tokens, output_tokens=out),
            message=Message(role="assistant", content=decision.text or decision.model_dump()),
            provider_meta={"provider": self.name, "model": self._model, "model_version": "1"},
        )

    async def stream(self, req: ModelRequest) -> AsyncIterator[ModelChunk]:  # pragma: no cover - v1
        resp = await self.complete(req)
        yield ModelChunk(text=resp.text, usage_cum=resp.usage)

    async def count_tokens(self, req: ModelRequest) -> int:
        """Exact by definition for this provider: the reservation and the settle use one formula."""
        return len(canonical_json(req.model_dump(mode="json"))) // 4
