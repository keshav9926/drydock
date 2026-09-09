"""Ctx — the only door for nondeterminism (§24.2).

Every method here is a Step: the step index is incremented synchronously at entry before any await,
the intent is compared against the journal, and a journaled outcome is returned without awaiting
anything external. Agent code must not read time, randomness or the network outside this object;
that is the documented determinism contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from keel.core.errors import ConcurrentStepError, UnknownTool
from keel.core.hashing import args_hash as _args_hash
from keel.core.hashing import effect_key as _effect_key
from keel.core.hashing import request_hash as _request_hash
from keel.core.protocols import StepIntent, StepKind
from keel.providers.protocol import Message, ModelRequest, ModelResponse
from keel.runtime.steps import StepEngine


class Ctx:
    def __init__(
        self,
        engine: StepEngine,
        *,
        run_id: Any,
        run_root_id: Any,
        args: Any,
        program_version: str,
        tools: Any = None,
    ) -> None:
        self._engine = engine
        self._tools = tools
        self._next_index = 0
        self._in_flight = False
        self.run_id = run_id
        self.run_root_id = run_root_id
        self.args = args
        self.program_version = program_version

    @property
    def step_index(self) -> int:
        """The next index to be issued."""
        return self._next_index

    def _open(self) -> int:
        if self._in_flight:
            raise ConcurrentStepError(
                "a step is already in flight; steps are strictly sequential per run. "
                "Parallelism is ctx.delegate_many to child runs, never concurrent ctx.* calls."
            )
        self._in_flight = True
        index = self._next_index
        self._next_index += 1
        return index

    async def _run(self, intent: StepIntent) -> Any:
        try:
            return await self._engine.execute(intent)
        finally:
            self._in_flight = False

    # --- steps ---------------------------------------------------------------
    async def model(
        self,
        messages: Sequence[Message | dict[str, Any]],
        tools: Sequence[dict[str, Any]] = (),
        *,
        name: str,
        max_tokens: int = 1024,
        **sampling: Any,
    ) -> ModelResponse:
        """MODEL step; identity = (MODEL, name). No provider/model argument — that is
        runs.model_config, resolved when the step executes LIVE (§1)."""
        index = self._open()
        req = ModelRequest(
            messages=[m if isinstance(m, Message) else Message(**m) for m in messages],
            tools=list(tools),
            max_tokens=max_tokens,
            sampling=dict(sampling),
        )
        payload = req.model_dump(mode="json")
        intent = StepIntent(
            step_index=index,
            kind=StepKind.MODEL,
            name=name,
            args=payload,
            args_hash=_args_hash(payload),
            request_hash=_request_hash(payload),
            program_version=self.program_version,
        )
        return ModelResponse.model_validate(await self._run(intent))

    async def tool(self, name: str, /, **args: Any) -> Any:
        """TOOL step; identity = (TOOL, name, canonical-args hash)."""
        index = self._open()
        try:
            tool = self._tools.get(name) if self._tools else None
            if tool is None:
                raise UnknownTool(name)
            intent = StepIntent(
                step_index=index,
                kind=StepKind.TOOL,
                name=name,
                args=args,
                args_hash=_args_hash(args),
                effect_key=_effect_key(self.run_root_id, index, name, args),
                effect_class=tool.effect_class,
                modifiers=tuple(tool.modifiers),
                program_version=self.program_version,
            )
        except BaseException:
            self._in_flight = False
            raise
        return await self._run(intent)

    async def now(self) -> datetime:
        """NOW step; recorded once, replayed forever."""
        index = self._open()
        intent = StepIntent(
            step_index=index,
            kind=StepKind.NOW,
            name="now",
            args_hash=_args_hash(None),
            program_version=self.program_version,
        )
        return datetime.fromisoformat(await self._run(intent))

    async def random(self) -> float:
        """RANDOM step; same contract."""
        index = self._open()
        intent = StepIntent(
            step_index=index,
            kind=StepKind.RANDOM,
            name="random",
            args_hash=_args_hash(None),
            program_version=self.program_version,
        )
        return float(await self._run(intent))
