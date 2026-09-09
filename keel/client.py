"""The public client: `Keel`, `RunHandle`, and the `@program` decorator (§24.1)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from keel.core.clock import Clock, SystemClock
from keel.core.errors import KeelError
from keel.core.ids import RunId, new_run_id
from keel.core.versions import KEEL_VERSION, code_hash, program_version
from keel.effects.registry import ToolRegistry, ToolSpec  # registers StepExecutor(TOOL) (§23.2)
from keel.events import Event, RunCreated
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import JournalBackend, RunRow
from keel.state.fold import fold
from keel.state.views import RunSummary, RunView, run_summary, run_view

PROGRAMS: dict[str, "Program"] = {}


class Budget(BaseModel):
    """Reserve-then-settle per attempt, so crashed model attempts are charged (§8.6).
    Admission is day 4; the shape is fixed on day 1 because RUN_CREATED carries it."""

    max_tokens: int | None = None
    max_usd: float | None = None
    max_model_calls: int | None = None
    max_tool_calls: int | None = None
    deadline_at: datetime | None = None
    on_exceed: str = "fail"


@dataclass(slots=True)
class Program:
    fn: Callable[..., Any]
    name: str
    declared_version: str
    version: str
    entrypoint: str

    async def __call__(self, ctx: Any, args: Any) -> Any:
        return await self.fn(ctx, args)


def program(*, name: str, version: str = "1.0") -> Callable[[Callable[..., Any]], Program]:
    def wrap(fn: Callable[..., Any]) -> Program:
        p = Program(
            fn=fn,
            name=name,
            declared_version=version,
            version=program_version(version, fn),
            entrypoint=f"{fn.__module__}:{fn.__qualname__}",
        )
        PROGRAMS[name] = p
        return p

    return wrap


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
        self.programs: dict[str, Program] = {p.name: p for p in programs} or dict(PROGRAMS)

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
            **kwargs,
        )

    async def resume(self, run_id: RunId) -> bool:
        """MVP: a direct conditional UPDATE of runs.runnable_at — an explicitly temporary second
        control path, replaced (not supplemented) by the signals inbox at v1 (§27.2, 4.10)."""
        return await self.journal.mark_runnable(run_id, "RESUME")

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
