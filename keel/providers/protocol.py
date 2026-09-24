"""ModelProvider and its request/response models (§23.4).

Provider, model id and sampling defaults are `runs.model_config`, resolved when a MODEL step
executes LIVE — `ctx.model` carries no provider argument, because model identity is a *binding*,
not a program input (§1). Nothing above `runtime` knows which provider answered.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: str
    content: Any


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_tokens: int = 0
    output_tokens: int = 0
    #: Prompt tokens served from the provider's cache — billed apart from `input_tokens`, so counted
    #: apart (STEP_COMPLETED v2, §6.5). A provider with no cache reports 0.
    cache_read_tokens: int = 0


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    messages: list[Message]
    system: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    max_tokens: int = 1024
    sampling: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = Usage()
    message: Message | None = None
    provider_meta: dict[str, Any] = Field(default_factory=dict)


class ModelChunk(BaseModel):
    """One piece of a streamed answer. The last one carries the whole `response`; a stream that ends
    without it was cut, and what came before is never the answer (§10.7)."""

    model_config = ConfigDict(frozen=True)
    text: str = ""
    usage_cum: Usage = Usage()
    response: ModelResponse | None = None


class ModelProvider(Protocol):
    name: str

    async def complete(self, req: ModelRequest) -> ModelResponse: ...

    def stream(self, req: ModelRequest) -> AsyncIterator[ModelChunk]: ...

    async def count_tokens(self, req: ModelRequest) -> int:
        """Exact, or a heuristic that never under-counts — the budget reservation depends on it."""
        ...
