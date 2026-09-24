"""The public client: `Keel`, `RunHandle`, and the `@program` decorator (§24.1)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from keel.core.clock import Clock, SystemClock
from keel.core.errors import KeelError
from keel.core.ids import RunId, new_run_id
from keel.core.protocols import COMPENSATE
from keel.core.versions import KEEL_VERSION, code_hash, program_version
from keel.effects.registry import ToolRegistry, ToolSpec  # registers StepExecutor(TOOL) (§23.2)
from keel.events import Event, RunCreated
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import JournalBackend, RunRow
from keel.providers import pricing
from keel.state.fold import committed_effect, fold
from keel.state.views import RunSummary, RunView, run_summary, run_view

PROGRAMS: dict[str, "Program"] = {}


class Budget(BaseModel):
    """Reserve-then-settle per attempt, so crashed model attempts are charged (§8.6).
    Admission is day 4; the shape is fixed on day 1 because RUN_CREATED carries it."""

    max_tokens: int | None = None
    max_usd: float | None = None
    max_model_calls: int | None = None
    max_tool_calls: int | None = None
    #: Wall clock from RUN_CREATED, parked time included — a run waiting three days on an approval
    #: burns none of the other dimensions and all of this one (§16.4). Converted to an absolute
    #: deadline once, by the store's clock; the earlier of it and `deadline_at` is the run's deadline.
    max_wall_clock: timedelta | None = None
    deadline_at: datetime | None = None
    on_exceed: str = "fail"


@dataclass(slots=True)
class Program:
    fn: Callable[..., Any]
    name: str
    declared_version: str
    version: str
    entrypoint: str
    #: The Pydantic v2 model of `Continue(state)` (§18.3). None: the program never continues, so a
    #: run of it replays from step 0 however long it gets.
    state_model: type[BaseModel] | None = None

    async def __call__(self, ctx: Any, args: Any, state: Any = None) -> Any:
        """`prog(ctx, args)` in the first segment; `prog(ctx, args, state)` from a boundary."""
        return await (self.fn(ctx, args) if state is None else self.fn(ctx, args, state))


def program(
    *, name: str, version: str = "1.0", state: type[BaseModel] | None = None
) -> Callable[[Callable[..., Any]], Program]:
    """Register a program. `state=` declares the model a `Continue(state)` carries across a
    continuation boundary; its JSON schema is recorded in `programs.state_schema` (§5.8)."""

    def wrap(fn: Callable[..., Any]) -> Program:
        p = Program(
            fn=fn,
            name=name,
            declared_version=version,
            version=program_version(version, fn),
            entrypoint=f"{fn.__module__}:{fn.__qualname__}",
            state_model=state,
        )
        PROGRAMS[name] = p
        return p

    return wrap


@program(name="keel.compensate", version="1.0")
async def compensation(ctx: Any, args: dict[str, Any]) -> Any:
    """The operator half of the compensate hook (§9.5, §25.2): one TOOL step, `<tool>.compensate`, undoing
    another run's committed effect — its facts are this run's args, so the step is replayable from them."""
    facts = {k: args[k] for k in ("of_run", "of_step", "of_effect_key", "args", "result")}
    return await ctx.tool(args["tool"] + COMPENSATE, **facts)


@dataclass(slots=True)
class RunResult:
    run_id: RunId
    phase: str
    result: Any = None
    error: str | None = None
    view: RunView | None = None


class RunHandle:
    def __init__(self, keel: "Keel", run_id: RunId) -> None:
        self._keel = keel
        self.run_id = run_id

    async def view(self) -> RunView:
        return await self._keel.get(self.run_id)

    async def wait(self, *, timeout: float | None = None) -> RunResult:
        deadline = None if timeout is None else asyncio.get_running_loop().time() + timeout
        while True:
            view = await self.view()
            if view.phase in ("COMPLETED", "FAILED", "CANCELLED", "SUSPENDED"):
                return RunResult(self.run_id, view.phase, view.result, view.error, view)
            if deadline is not None and asyncio.get_running_loop().time() > deadline:
                return RunResult(self.run_id, view.phase, view.result, view.error, view)
            await asyncio.sleep(0.05)


class Keel:
    def __init__(
        self,
        dsn: str | None = None,
        *,
        journal: JournalBackend | None = None,
        provider: Any = None,
        tools: Iterable[ToolSpec] = (),
        clock: Clock | None = None,
        programs: Iterable[Program] = (),
        policy: Any = None,
        sandbox: Any = None,
    ) -> None:
        if dsn and journal:
            raise KeelError("pass exactly one of dsn / journal")
        self.clock: Clock = clock or SystemClock()
        if journal is not None:
            self.journal = journal
        elif dsn and dsn != "memory://":
            from keel.journal.postgres import PostgresJournal

            self.journal = PostgresJournal(dsn)
        else:
            self.journal = MemoryJournal(clock=self.clock)
        self.provider = provider
        self.tools = ToolRegistry(tools)
        #: §20.2 / §24.1: the `Policy` every worker built from this client consults (StaticPolicy,
        #: `keel/runtime/policy.py`, is the default implementation). None: allow-all.
        self.policy = policy
        #: §20.5: `LocalSandbox(root)` gives LOCAL_FS tools a per-epoch workspace; None, no workspace.
        self.sandbox = sandbox
        self.programs: dict[str, Program] = {p.name: p for p in programs} or dict(PROGRAMS)
        self.programs.setdefault(compensation.name, compensation)  # any worker can run an operator's undo

    # --- registration --------------------------------------------------------
    def register(self, p: Program) -> Program:
        self.programs[p.name] = p
        return p

    async def upsert_programs(self) -> None:
        for p in self.programs.values():
            await self.journal.register_program(
                program=p.name,
                program_version=p.version,
                declared_version=p.declared_version,
                code_hash=code_hash(p.fn),
                entrypoint=p.entrypoint,
                keel_version=KEEL_VERSION,
                tools=self.tools.manifest(),
                state_schema=p.state_model.model_json_schema() if p.state_model else None,
            )

    def resolve(self, program_ref: Program | str) -> Program:
        if isinstance(program_ref, Program):
            return program_ref
        try:
            return self.programs[program_ref]
        except KeyError as exc:
            raise KeelError(
                f"program {program_ref!r} is not defined by this --app module; "
                "a run nobody can claim is worse than a refusal at start"
            ) from exc

    # --- lifecycle -----------------------------------------------------------
    async def start(
        self,
        program_ref: Program | str,
        args: Mapping[str, Any] | None = None,
        *,
        budget: Budget | None = None,
        model_config: Mapping[str, Any] | None = None,
        run_id: RunId | None = None,
    ) -> RunHandle:
        p = self.resolve(program_ref)
        await self.upsert_programs()
        rid = run_id or new_run_id()
        budget = budget or Budget()
        model_config = dict(model_config or {"provider": getattr(self.provider, "name", "scripted")})
        # §16.4: the price table is pinned here, once, so a later price change never re-values this run.
        ref = pricing.current_ref(str(model_config.get("provider") or getattr(self.provider, "name", "")))
        if ref is not None:
            model_config.setdefault("pricing_ref", ref)
        row = RunRow(
            run_id=rid,
            run_root_id=rid,
            program=p.name,
            program_version=p.version,
            keel_version=KEEL_VERSION,
            phase="CREATED",
            trace_id=rid,
            args=dict(args or {}),
            budget=budget.model_dump(mode="json"),
            model_config=model_config,
        )
        created = RunCreated(
            program=p.name,
            program_version=p.version,
            args=dict(args or {}),
            budget=budget.model_dump(mode="json"),
            model_config=model_config,
        )
        await self.journal.create_run(row, created, runnable_at=self.clock.now())
        return RunHandle(self, rid)

    async def run(
        self,
        program_ref: Program | str,
        args: Mapping[str, Any] | None = None,
        *,
        budget: Budget | None = None,
        model_config: Mapping[str, Any] | None = None,
        timeout: float | None = 30.0,
    ) -> RunResult:
        """start() plus an in-process worker until terminal; tests and the demo (§24.1)."""
        handle = await self.start(program_ref, args, budget=budget, model_config=model_config)
        await self.worker(worker_id="inline").run_until_idle(run_id=handle.run_id, timeout=timeout)
        return await handle.wait(timeout=0)

    def worker(self, **kwargs: Any) -> Any:
        """Build a Worker bound to this client's journal, provider, tools and programs. The worker
        itself knows nothing about `Keel` — `runtime` imports no sibling package (§23.2)."""
        from keel.runtime.worker import Worker

        return Worker(
            self.journal,
            resolve=self.resolve,
            provider=self.provider,
            tools=self.tools,
            clock=self.clock,
            policy=self.policy,
            sandbox=self.sandbox,
            **kwargs,
        )

    async def signal(
        self,
        run_id: RunId,
        type_: str,
        payload: dict[str, Any] | None = None,
        *,
        client_key: str | None = None,
        source: str = "api",
    ) -> bool:
        """Put one row in the inbox. The only way anything that is not the lease holder influences
        a run (§4.10), and therefore the only thing `resume`, `cancel` and `pause` are."""
        from keel.core.ids import uuid7
        from keel.journal.protocol import SignalRow

        return await self.journal.insert_signal(
            SignalRow(
                signal_id=uuid7(),
                run_id=run_id,
                type=type_,
                payload=payload or {},
                client_key=client_key,
                source=source,
            )
        )

    # --- §24.1's control calls: each one row in the inbox, the same row the CLI writes ---------
    async def pause(self, run_id: RunId, *, client_key: str | None = None) -> bool:
        return await self.signal(run_id, "pause", {}, client_key=client_key)

    async def cancel(self, run_id: RunId, *, reason: str = "", client_key: str | None = None) -> bool:
        """Cooperative; acknowledged at the next step boundary; propagates to children (§17.7)."""
        return await self.signal(run_id, "cancel", {"reason": reason}, client_key=client_key)

    async def approve(self, run_id: RunId, approval_id: Any, *, by: str, client_key: str | None = None) -> bool:
        """Names its gate, always: a decision for an approval already decided is ignored at the
        drain rather than applied to whichever approval is open by then (§7.5)."""
        return await self.signal(
            run_id, "approve", {"by": by, "approval_id": str(approval_id)}, client_key=client_key
        )

    async def reject(
        self, run_id: RunId, approval_id: Any, *, by: str, reason: str = "", client_key: str | None = None
    ) -> bool:
        return await self.signal(
            run_id, "reject", {"by": by, "reason": reason, "approval_id": str(approval_id)}, client_key=client_key
        )

    async def compensate(self, run_id: RunId, step_index: int) -> RunHandle:
        """An operator's compensation of a committed effect (§9.5; `keel signal RUN --compensate STEP`): a
        compensation run whose one step is `<tool>.compensate`, with its own key. A run, not a signal into
        `run_id` — a step that run's program never issued would make its journal unreplayable, and a
        terminal run has no holder left to drain a signal. Refused (`ContractInvalid`) unless the step is
        a committed TOOL effect; `UnknownTool` unless its tool declares a compensate hook."""
        facts = committed_effect(await self.events(run_id), step_index)
        self.tools.get(facts["tool"] + COMPENSATE)
        return await self.start(compensation, {"of_run": str(run_id), **facts})

    async def rebind(self, run_id: RunId, model_config: dict[str, Any], *, client_key: str | None = None) -> bool:
        """Journaled as MODEL_BINDING_CHANGED at the drain; affects live MODEL steps only (§16.7)."""
        return await self.signal(run_id, "rebind", {"model_config": dict(model_config)}, client_key=client_key)

    async def resume(self, run_id: RunId) -> bool:
        """One `resume` row in the inbox.

        The MVP's direct conditional UPDATE of `runs.runnable_at` is gone rather than kept beside
        this: it was marked temporary when it was written, and a second way to influence a run is
        one the fence cannot defend — the holder never learns that it happened (§27.2, §4.10).
        """
        return await self.signal(run_id, "resume")

    async def resolve_step(
        self,
        run_id: RunId,
        step_index: int,
        outcome: str,
        *,
        evidence: str = "",
        result: Any = None,
        by: str = "",
        client_key: str | None = None,
    ) -> bool:
        """A human's decision for a RESOLVED_UNKNOWN step: `completed`, `failed` or `cancelled`
        (§7.3, §25.2's `keel signal --resolve STEP=…`). The first two are one `custom{kind:
        resolve_step}` row, which also lifts the suspension (§7.2.1); `cancelled` is the ordinary
        run cancel, which closes the step with STEP_CANCELLED at its acknowledgement."""
        from keel.runtime import human

        if outcome == "cancelled":
            reason = f"resolved cancelled at step {step_index}" + (f": {evidence}" if evidence else "")
            return await self.cancel(run_id, reason=reason, client_key=client_key)
        if outcome not in human.OUTCOMES:
            raise KeelError(f"resolve as completed | failed | cancelled, not {outcome!r}")
        payload = human.signal_payload(step_index, outcome, evidence=evidence, result=result, by=by)
        return await self.signal(run_id, "custom", payload, client_key=client_key)

    # --- reads ---------------------------------------------------------------
    async def get(self, run_id: RunId) -> RunView:
        row = await self.journal.run_row(run_id)
        if row is None:
            raise KeelError(f"no such run: {run_id}")
        state = fold(await self.journal.read(run_id))
        effects = await self.journal.effects(run_id)
        return run_view(row, state, datetime.now(UTC), effects)

    async def events(self, run_id: RunId, *, from_seq: int = 0) -> list[Event]:
        return await self.journal.read(run_id, from_seq=from_seq)

    async def runs(self, *, phase: str | None = None, limit: int = 50) -> list[RunSummary]:
        out = []
        for row in await self.journal.list_runs(phase=phase, limit=limit):
            state = fold(await self.journal.read(row.run_id))
            out.append(run_summary(row, state, datetime.now(UTC)))
        return out

    async def close(self) -> None:
        await self.journal.close()
