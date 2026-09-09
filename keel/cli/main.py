"""The `keel` command tree (§25).

Developer-first conventions: every read command emits one JSON document under `--json`; Rich
rendering otherwise; diagnostics to stderr; any unique prefix of a run id is accepted, like git;
nothing prompts, so `--yes` does not exist.

Exit codes: 0 ok · 1 error · 2 usage · 3 run FAILED (--wait) · 4 needs a human · 5 fenced.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import importlib
import json
import os
import sys
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from keel.client import Budget, Keel
from keel.core import aio
from keel.core.errors import KeelError
from keel.state.fold import fold

# Windows consoles and pipes default to a legacy code page; the help text and the journal both
# carry non-ASCII. Reconfigure once, here, rather than making every message ASCII.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(add_completion=False, help="Keel - durable execution for agents.")
db = typer.Typer(help="Schema management.")
app.add_typer(db, name="db")

out = Console()
err = Console(stderr=True)

EXIT_ERROR, EXIT_USAGE, EXIT_FAILED, EXIT_NEEDS_HUMAN = 1, 2, 3, 4
_NEEDS_HUMAN = {"WAITING_APPROVAL", "WAITING_RESOLUTION", "SUSPENDED"}


def _load_app(app_ref: str | None, dsn: str | None) -> Keel:
    ref = app_ref or os.environ.get("KEEL_APP")
    if ref:
        module_name, _, attr = ref.partition(":")
        module = importlib.import_module(module_name)
        keel = getattr(module, attr or "app")
        if dsn:
            keel = Keel(dsn, provider=keel.provider, tools=list(keel.tools), programs=list(keel.programs.values()))
        return keel
    dsn = dsn or os.environ.get("KEEL_DSN")
    if not dsn:
        err.print("[red]need --app module:attr (or KEEL_APP), or --dsn for read-only commands[/]")
        raise typer.Exit(EXIT_USAGE)
    return Keel(dsn)


def _run(coro: Any) -> Any:
    return aio.run(coro)


async def _resolve(keel: Keel, run_ref: str) -> Any:
    run_id = await keel.journal.resolve_run_id(run_ref)
    if run_id is None:
        err.print(f"[red]no run matches {run_ref!r}[/]")
        raise typer.Exit(EXIT_ERROR)
    return run_id


def _dump(obj: Any) -> str:
    def enc(o: Any) -> Any:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        if hasattr(o, "model_dump"):
            return o.model_dump(mode="json")
        return str(o)

    return json.dumps(obj, indent=2, default=enc)


# --- run ---------------------------------------------------------------------
@app.command()
def run(
    program: str,
    args: Annotated[str, typer.Option(help="JSON object")] = "{}",
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    budget: Annotated[list[str], typer.Option("--budget", help="k=v, repeatable")] = None,
    wait: bool = False,
    inline: Annotated[bool, typer.Option("--inline", help="run in an in-process worker")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a run and mark it runnable; a `keel worker` executes it."""
    keel = _load_app(app_ref, dsn)
    budget_kwargs = dict(kv.split("=", 1) for kv in (budget or []))

    async def go() -> None:
        b = Budget(**{k: json.loads(v) for k, v in budget_kwargs.items()})
        if inline:
            result = await keel.run(program, json.loads(args), budget=b)
            _emit_result(result.run_id, result.phase, json_out)
            return
        handle = await keel.start(program, json.loads(args), budget=b)
        if wait:
            result = await handle.wait(timeout=300)
            _emit_result(handle.run_id, result.phase, json_out)
            return
        out.print(str(handle.run_id)) if not json_out else out.print(_dump({"run_id": str(handle.run_id)}))

    _run(go())


def _emit_result(run_id: Any, phase: str, json_out: bool) -> None:
    out.print(_dump({"run_id": str(run_id), "phase": phase}) if json_out else f"{run_id}  {phase}")
    if phase == "FAILED":
        raise typer.Exit(EXIT_FAILED)
    if phase in _NEEDS_HUMAN:
        raise typer.Exit(EXIT_NEEDS_HUMAN)


# --- reads -------------------------------------------------------------------
@app.command()
def runs(
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    phase: str | None = None,
    limit: int = 50,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        rows = await keel.runs(phase=phase, limit=limit)
        if json_out:
            out.print(_dump(rows))
            return
        table = Table(box=None)
        for col in ("run", "program", "phase", "control", "epoch", "created"):
            table.add_column(col)
        for r in rows:
            table.add_row(
                str(r.run_id)[:8],
                r.program,
                r.phase,
                r.control_status or "-",
                str(r.lease_epoch),
                str(r.created_at or "")[:19],
            )
        out.print(table)

    _run(go())


@app.command()
def show(
    run_ref: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Phase ∪ lease status, open step, recoveries."""
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        run_id = await _resolve(keel, run_ref)
        view = await keel.get(run_id)
        recoveries = await keel.journal.recoveries(run_id)
        if json_out:
            out.print(_dump({"view": view, "recoveries": recoveries}))
            return
        out.print(
            f"run [bold]{view.run_id}[/]  {view.program} {view.program_version}\n"
            f"phase={view.phase}  control={view.control_status or '-'}  "
            f"epoch={view.lease_epoch}  last_seq={view.last_seq}"
        )
        if view.suspended_reason:
            out.print(f"[yellow]suspended: {view.suspended_reason}[/]")
        if view.error:
            out.print(f"[red]error: {view.error}[/]")
        if view.result is not None:
            out.print(f"result: {json.dumps(view.result)}")
        table = Table(box=None, title="recoveries")
        for col in ("epoch", "cause", "worker", "live_from", "replayed", "outcome"):
            table.add_column(col)
        for r in recoveries:
            table.add_row(
                str(r.lease_epoch), r.cause, r.worker_id,
                str(r.live_from_step), str(r.replayed_steps), r.outcome or "-",
            )
        out.print(table)

    _run(go())


@app.command()
def events(
    run_ref: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    from_seq: Annotated[int, typer.Option("--from")] = 0,
    epoch: Annotated[str | None, typer.Option("--epoch", help="E or 'all'")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """The journal, with `memo | recovered | live` origin markers (§25.4)."""
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        run_id = await _resolve(keel, run_ref)
        evs = await keel.events(run_id, from_seq=from_seq)
        state = fold(await keel.events(run_id))
        if json_out:
            out.print(_dump([{"env": e.env, "body": e.body} for e in evs]))
            return
        against = state.latest_epoch if epoch in (None, "all") else int(epoch)
        shown = evs if epoch in (None, "all") else [e for e in evs if e.lease_epoch == against]
        out.print(
            f"run [bold]{run_id}[/]  {state.program} {state.program_version}  "
            f"phase={state.phase}  epochs={len(state.epochs)}"
        )
        table = Table(box=None)
        for col, just in (("seq", "right"), ("ep", "right"), ("event", "left"),
                          ("step", "right"), ("detail", "left"), ("origin", "left")):
            table.add_column(col, justify=just)
        for e in shown:
            si = e.step_index
            table.add_row(
                str(e.seq),
                str(e.lease_epoch),
                e.type,
                "-" if si is None else str(si),
                _detail(e),
                "" if si is None else state.origin(si, against),
            )
        out.print(table)

    _run(go())


def _detail(e: Any) -> str:
    b = e.body
    t = e.type
    if t == "RUN_CREATED":
        return f"{b.program} {b.program_version}"
    if t == "RECOVERY_STARTED":
        return f"cause={b.cause} from_seq={b.from_seq}"
    if t == "RECOVERY_COMPLETED":
        return f"live_from_step={b.live_from_step} replayed_steps={b.replayed_steps}"
    if t == "STEP_INTENDED":
        cls = f" [{b.effect_class}]" if b.effect_class else ""
        return f"{b.kind} {b.name}{cls}"
    if t == "STEP_ATTEMPT_STARTED":
        return f"attempt={b.attempt_no}" + (f" deadline={b.attempt_deadline:%H:%M:%S}" if b.attempt_deadline else "")
    if t == "STEP_COMPLETED":
        return _short(b.result)
    if t == "STEP_FAILED":
        return f"{b.error} retryable={b.retryable}"
    if t == "STEP_AMBIGUOUS":
        return f"cause={b.cause}"
    if t == "STEP_RESOLVED":
        return f"{b.resolution} via {b.method}"
    if t == "RUN_COMPLETED":
        return _short(b.result)
    if t == "RUN_FAILED":
        return b.error
    if t == "RUN_SUSPENDED":
        return f"{b.reason}"
    return ""


def _short(value: Any, width: int = 46) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    return text if len(text) <= width else text[: width - 1] + "…"


@app.command()
def steps(
    run_ref: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        view = await keel.get(await _resolve(keel, run_ref))
        if json_out:
            out.print(_dump(view.steps))
            return
        table = Table(box=None)
        for col in ("i", "kind", "name", "state", "att", "class", "effect_key", "origin"):
            table.add_column(col)
        for s in view.steps:
            table.add_row(
                str(s.step_index), s.kind, s.name, s.state, str(s.attempts),
                s.effect_class or "-", (s.effect_key or "-")[:16], s.origin,
            )
        out.print(table)

    _run(go())


@app.command()
def effects(
    run_ref: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    ambiguous: Annotated[bool, typer.Option("--ambiguous")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        rows = await keel.journal.effects(await _resolve(keel, run_ref))
        if ambiguous:
            rows = [r for r in rows if r.status in ("AMBIGUOUS", "RESOLVED_UNKNOWN")]
        if json_out:
            out.print(_dump(rows))
            return
        table = Table(box=None)
        for col in ("step", "tool", "class", "status", "resolution", "external_ref", "effect_key"):
            table.add_column(col)
        for r in rows:
            table.add_row(
                str(r.step_index), r.tool, r.effect_class, r.status,
                r.resolution or "-", r.external_ref or "-", r.effect_key,
            )
        out.print(table)

    _run(go())


@app.command()
def state(
    run_ref: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    at: Annotated[int | None, typer.Option("--at", help="fold stopped at this seq")] = None,
) -> None:
    """The projection at a seq. A projection is a pure fold; `--at` is the same fold, stopped."""
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        run_id = await _resolve(keel, run_ref)
        evs = await keel.events(run_id)
        if at is not None:
            evs = [e for e in evs if e.seq <= at]
        st = fold(evs)
        out.print(_dump({
            "phase": st.phase,
            "last_seq": st.last_seq,
            "projection_hash": st.projection_hash(),
            "result": st.result,
            "error": st.error,
            "steps": list(st.steps.values()),
        }))

    _run(go())


@app.command()
def resume(
    run_ref: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """Mark a run runnable again. MVP: a direct conditional UPDATE — an explicitly temporary second
    control path, replaced by the signals inbox at v1 (§27.2)."""
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        run_id = await _resolve(keel, run_ref)
        ok = await keel.resume(run_id)
        out.print("runnable" if ok else "[yellow]already terminal[/]")

    _run(go())


# --- worker / db -------------------------------------------------------------
@app.command()
def worker(
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    lease_ttl: Annotated[float, typer.Option("--lease-ttl")] = 30.0,
    shutdown_grace: Annotated[float, typer.Option("--shutdown-grace")] = 10.0,
    worker_id: Annotated[str | None, typer.Option("--worker-id")] = None,
    reaper: Annotated[bool, typer.Option("--reaper/--no-reaper")] = True,
) -> None:
    """Claim runs, hold one lease each, heartbeat with the fence statement, re-execute."""
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        from keel.runtime.reaper import Reaper

        await keel.upsert_programs()
        w = keel.worker(worker_id=worker_id, lease_ttl=lease_ttl, shutdown_grace=shutdown_grace)
        err.print(f"worker {w.worker_id} lease_ttl={lease_ttl}s")
        tasks = [asyncio.create_task(w.run_forever())]
        if reaper:
            tasks.append(asyncio.create_task(Reaper(keel.journal).run_forever()))
        try:
            await tasks[0]
        finally:
            for t in tasks[1:]:
                t.cancel()

    try:
        _run(go())
    except KeelError as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(EXIT_ERROR) from exc


@db.command("migrate")
def db_migrate(
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
) -> None:
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        await keel.journal.migrate()
        out.print("migrated")

    _run(go())


@app.command()
def reap(
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """One reaper sweep: now() > max(lease_expires_at, attempt_deadline) (§8.4)."""
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        orphaned = await keel.journal.reap()
        out.print(_dump([str(r) for r in orphaned]))

    _run(go())


def main() -> None:  # pragma: no cover
    try:
        app()
    except KeelError as exc:
        err.print(f"[red]{exc}[/]")
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":  # pragma: no cover
    main()
