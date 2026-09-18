"""Ctx — the only door for nondeterminism (§24.2).

Every method here is a Step: the step index is incremented synchronously at entry before any await,
the intent is compared against the journal, and a journaled outcome is returned without awaiting
anything external. Agent code must not read time, randomness or the network outside this object;
that is the documented determinism contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from keel.core.errors import ConcurrentStepError, UnknownTool
from keel.core.hashing import args_hash as _args_hash
from keel.core.hashing import effect_key as _effect_key
from keel.core.hashing import request_hash as _request_hash
from keel.core.protocols import StepIntent, StepKind
from keel.providers.protocol import Message, ModelRequest, ModelResponse
from keel.runtime.delegation import ChildResult, Delegation, canonical
from keel.runtime.segments import FORCED_SEGMENT_STEPS
from keel.runtime.steps import StepEngine
from keel.state import context as _context
from keel.state import plan as _plan

#: What a COMPACT step asks the model (§16.2). A constant, so a compaction's request — and its
#: `request_hash` — is a function of the context alone, and VERIFY reports PromptDrift if it moves.
COMPACT_SYSTEM = (
    "Summarize the conversation so far for your own later use. Keep every decision, constraint and "
    "open question; drop what no later step needs. The durable plan is kept separately."
)


@dataclass(frozen=True, slots=True)
class ContextView:
    """`ctx.context` (§16.2): the context projection at the replay cursor. `tokens` is cut: it needs
    `ModelProvider.count_tokens` over the outcomes since the last MODEL step, and nothing in week 3
    compacts on size rather than on a schedule."""

    messages: list[dict[str, Any]]


class PlanApi:
    """`ctx.plan` (§16.1, §24.2): the durable plan, read at the replay cursor, changed only by PLAN steps.

    Reads are bounded by the cursor (§16.2): during re-execution at step *i* the program sees the plan
    as the ops *before* step *i* left it, never the journal's latest — otherwise a replay of step 5
    would read what step 50 did and take a different branch. The cursor plan is advanced by each PLAN
    step as its outcome is handed back, memoized or live, through the same `apply` the fold uses.
    """

    def __init__(self, ctx: "Ctx") -> None:
        self._ctx = ctx

    @property
    def items(self) -> list[dict[str, Any]]:
        return [dict(i) for i in self._ctx._plan]

    @property
    def done(self) -> bool:
        return bool(self._ctx._plan) and all(i["status"] == _plan.COMPLETED for i in self._ctx._plan)

    async def init(self, titles: Sequence[str]) -> None:
        """Replace the plan: one PLAN step. Item ids are `<step>.<k>`."""
        await self._ctx._plan_step("init", lambda i: _plan.init_diff(i, list(titles)))

    async def add(self, title: str) -> str:
        """Append one item: one PLAN step. Returns its id, `<step>`."""
        diff = await self._ctx._plan_step("add", lambda i: _plan.add_diff(i, title))
        return str(diff["item"]["id"])

    async def complete(self, item_id: str) -> None:
        """Mark an item completed: one PLAN step. An id the plan does not hold is a program bug,
        raised before any step is issued."""
        _plan.apply(self._ctx._plan, "complete", {"id": item_id})
        await self._ctx._plan_step("complete", lambda i: {"id": item_id})


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
        #: The plan at the replay cursor (§16.2). Seeded by the worker at a segment boundary.
        self._plan: list[dict[str, Any]] = []
        self.plan = PlanApi(self)
        #: The context projection at the replay cursor (§16.2), advanced as each outcome is handed back.
        self._context: list[dict[str, Any]] = _context.initial(args)
        #: The latest summary at the cursor: what a boundary resets the context to (§10.8).
        self._summary: dict[str, Any] | None = None
        #: Continuation segments (§18.3): where this segment began, N, and a boundary a safe point
        #: asked for, which is cut before the next step's INTENT if that step goes live.
        self._segment_first = 0
        self.segment_limit = FORCED_SEGMENT_STEPS
        self._pending_segment: dict[str, Any] | None = None

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
            if self._pending_segment is not None:
                blob, self._pending_segment = self._pending_segment, None
                # Before this step's INTENT, and only if it goes live: a journaled step here means
                # the original run did not cut here (another N), and the journal is what happened.
                if await self._engine.cut_segment(intent.step_index, blob, self._plan):
                    self._enter(intent.step_index)
            result = await self._engine.execute(intent)
        finally:
            self._in_flight = False
        # Only an outcome the program is handed moves the cursor context: memoized or live, the same
        # value, so a replay reads the context the original read (§16.2).
        self._context = _context.apply(self._context, str(intent.kind), intent.name, result)
        if intent.kind is StepKind.COMPACT:
            self._summary = _context.summary(result)
        return result

    # --- continuation segments (§18.3): non-step accessors --------------------
    @property
    def segment_steps(self) -> int:
        """Steps issued in this segment. Consumes no step index; never compared with the journal."""
        return self._next_index - self._segment_first

    def segment_point(self, state: Any) -> None:
        """A safe point: `state` is sufficient to restart the program from here. Once the segment has
        issued `segment_limit` steps, Keel cuts at the first safe point — before the next step's
        INTENT, if that step goes live. Consumes no step index and is never matched against the
        journal, so N is worker configuration that cannot trip nondeterminism detection (§10.8)."""
        if self.segment_steps >= self.segment_limit:
            self._pending_segment = state.model_dump(mode="json")

    def enter_segment(self, seg: Any, plan: list[dict[str, Any]], context: list[dict[str, Any]]) -> None:
        """Re-execution from a boundary (§10.8): the counter at its `first_step_index`, never reset,
        and the Keel-owned projections as the boundary left them."""
        self._next_index = seg.first_step_index
        self._segment_first = seg.first_step_index
        self._plan = [dict(i) for i in plan]
        self._context = [dict(m) for m in context]
        self._summary = dict(context[0]) if seg.compact_seq is not None and context else None

    async def _continue(self, blob: dict[str, Any]) -> None:
        """The program returned `Continue(state)`: journal the boundary at the next index."""
        await self._engine.cut_segment(self._next_index, blob, self._plan, returned=True)
        self._enter(self._next_index)

    def _enter(self, first_step_index: int) -> None:
        self._segment_first = first_step_index
        self._context = [dict(self._summary)] if self._summary else []

    @property
    def context(self) -> ContextView:
        """The context projection at the replay cursor: the latest summary, then what came since."""
        return ContextView([dict(m) for m in self._context])

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

    async def compact(self, *, name: str = "compact", max_tokens: int = 1024) -> str:
        """COMPACT step: MODEL identity and MODEL semantics — retried, budgeted, memoized — whose
        outcome is the summary (§16.1, §16.2). The request is the context at the cursor; after it the
        context projection is `[summary]` plus what follows. The plan is untouched."""
        index = self._open()
        req = ModelRequest(
            system=COMPACT_SYSTEM,
            messages=[Message(**m) for m in self._context],
            max_tokens=max_tokens,
        )
        payload = req.model_dump(mode="json")
        intent = StepIntent(
            step_index=index,
            kind=StepKind.COMPACT,
            name=name,
            args=payload,
            args_hash=_args_hash(payload),
            request_hash=_request_hash(payload),
            program_version=self.program_version,
        )
        return ModelResponse.model_validate(await self._run(intent)).text

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

    async def sleep(self, seconds: float) -> None:
        """SLEEP step: a durable timer, zero compute while it runs (§18.4).

        INTENT, STARTED, RUN_WAITING{sleep, wake_at} and the release commit together; `wake_at` is
        the store's `now()` plus `seconds`, never the worker's clock. The timer sweep wakes the run,
        and the step completes on the first wake the store's clock says is due — so a spurious
        wake re-parks, and a replay after the wake returns at once (§10.4)."""
        index = self._open()
        args = {"seconds": float(seconds)}
        intent = StepIntent(
            step_index=index,
            kind=StepKind.SLEEP,
            name="sleep",
            args=args,
            args_hash=_args_hash(args),
            program_version=self.program_version,
        )
        await self._run(intent)

    async def _plan_step(self, op: str, diff_at: Any) -> dict[str, Any]:
        """PLAN step; identity = (PLAN, plan.<op>, hash of op+diff) (§10.4). The diff is computed at
        entry from the index being issued, so an item id is fixed before anything is journaled."""
        index = self._open()
        try:
            diff = diff_at(index)
            after = _plan.apply(self._plan, op, diff)
            args = {"op": op, "diff": diff}
            intent = StepIntent(
                step_index=index,
                kind=StepKind.PLAN,
                name=f"plan.{op}",
                args=args,
                args_hash=_args_hash(args),
                program_version=self.program_version,
            )
        except BaseException:
            self._in_flight = False
            raise
        await self._run(intent)
        self._plan = after
        return diff

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
