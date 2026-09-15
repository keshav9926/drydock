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
from keel.runtime.delegation import ChildResult, Delegation, canonical
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

    async def approve(
        self,
        payload: dict[str, Any] | None = None,
        *,
        name: str = "approve",
        expires_in: float | None = None,
        gates: tuple[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """APPROVAL step: a durable wait for a human, costing no compute and no ticks.

        `gates=(tool, args)` makes it a *bound* approval, and binding is the point. The runtime owns
        the step counter, so it can compute `effect_key(run_root_id, i+1, tool, args)` before anyone
        decides and record it as `binds_effect_key` — the approval then names the exact effect it
        authorises rather than authorising whatever happens next. The gated call must therefore be
        the program's very next step; anything else fails with `ApprovalBindingError` rather than
        executing an effect nobody approved (§7.5).

        Returns `{decision, by, decided_at}` for `granted`, `rejected` and `expired` alike. What a
        rejection means is the program's business; a bound tool call is refused separately.
        """
        index = self._open()
        args: dict[str, Any] = {"payload": dict(payload or {})}
        if expires_in is not None:
            args["expires_in"] = expires_in
        if gates is not None:
            tool_name, tool_args = gates
            args["binds_effect_key"] = _effect_key(self.run_root_id, index + 1, tool_name, tool_args)
        intent = StepIntent(
            step_index=index,
            kind=StepKind.APPROVAL,
            name=name,
            args=args,
            # Identity excludes `expires_in` and the bound key: an operator extending a deadline on
            # a parked run must not turn it into a different step on replay. What the approval *is*
            # is its name and its payload.
            args_hash=_args_hash(args["payload"]),
            program_version=self.program_version,
        )
        return await self._run(intent)

    async def delegate(self, contract: Delegation | dict[str, Any], *, name: str = "delegate") -> ChildResult:
        """One child, one contract. Always the `ChildResult` wrapper, never the bare result, so
        the failure path cannot be skipped by accident (§17.8)."""
        [result] = await self.delegate_many([contract], name=name)
        return result

    async def delegate_many(
        self, contracts: Sequence[Delegation | dict[str, Any]], *, name: str = "delegate_many"
    ) -> list[ChildResult]:
        """DELEGATE step: spawn children under contracts and park until every one is terminal.

        Identity = (DELEGATE, name, hash of the journaled contracts) — the result schema included,
        so a redeploy that changes what a child is asked to return trips `NondeterminismDetected`
        here rather than re-grading children spawned under the old contract (§17.8). The run holds
        no lease and costs no ticks while the children work; each child's terminal event commits
        with the `child_result` row that wakes this run (§5.10).

        Results come back in ordinal order, one per contract, whatever their status: what a failed
        child *means* is the program's business unless the contract said `fail_parent`.
        """
        index = self._open()
        try:
            cs = [c if isinstance(c, Delegation) else Delegation.model_validate(c) for c in contracts]
            args = {"contracts": canonical(cs)}
            intent = StepIntent(
                step_index=index,
                kind=StepKind.DELEGATE,
                name=name,
                args=args,
                args_hash=_args_hash(args),
                program_version=self.program_version,
            )
        except BaseException:
            self._in_flight = False
            raise
        return [ChildResult.model_validate(r) for r in await self._run(intent)]

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
