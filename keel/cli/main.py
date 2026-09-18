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
from keel.events.schema import TERMINAL_TYPES
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
#: §25.2: a VERIFY mismatch has its own code, because CI branches on it and a run that failed is a
#: different thing from a program that no longer agrees with its journal.
EXIT_VERIFY_MISMATCH = 6
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
    from keel.core.errors import AmbiguousRunRef

    try:
        run_id = await keel.journal.resolve_run_id(run_ref)
    except AmbiguousRunRef as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(EXIT_USAGE) from exc
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
        if view.plan:
            # The durable plan (§16.2): the PLAN_UPDATED fold, which compaction never touches.
            plan = Table(box=None, title="plan")
            for col in ("id", "status", "title"):
                plan.add_column(col)
            for item in view.plan:
                plan.add_row(str(item["id"]), item["status"], item["title"])
            out.print(plan)
        # The parent's view of its children is the `delegations` row and nothing else (§17.3):
        # contract, status, what was reserved and what was settled. Never the child's journal.
        delegations = await keel.journal.delegations(run_id)
        if delegations:
            kids = Table(box=None, title="children")
            for col in ("step", "ordinal", "retry", "child", "role", "status", "reserved", "settled"):
                kids.add_column(col)
            for d in delegations:
                kids.add_row(
                    str(d.parent_step_index), str(d.child_ordinal), str(d.retry_no),
                    str(d.child_run_id), d.role, d.status,
                    json.dumps(d.budget_reserved), json.dumps(d.usage_settled) if d.usage_settled else "-",
                )
            out.print(kids)

    _run(go())


@app.command()
def events(
    run_ref: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    from_seq: Annotated[int, typer.Option("--from")] = 0,
    epoch: Annotated[str | None, typer.Option("--epoch", help="E or 'all'")] = None,
    follow: Annotated[bool, typer.Option("--follow", help="keep printing as the journal grows")] = False,
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
        if follow and state.phase in ("COMPLETED", "FAILED", "CANCELLED"):
            # The tail polls, so following a run that has already ended waits forever for an event
            # nobody will ever append. Say so instead.
            out.print(f"[dim]— {state.phase}; nothing further will be appended —[/]")
        elif follow:
            await _follow(keel, run_id, from_seq=evs[-1].seq if evs else from_seq)

    _run(go())


async def _follow(keel: Any, run_id: Any, *, from_seq: int) -> None:
    """`--follow`: the journal as it is written, until the run reaches a terminal state.

    This is §28.7's stated substitute for the `keel watch` TUI, and it is a substitute rather than
    a consolation. What the TUI was for is the BEFORE CRASH / AFTER RESTART split, and that split
    is *in the event stream*: RECOVERY_STARTED is the line where a different process took over, and
    `origin` marks every step it replayed rather than re-ran. A tail shows both without a second
    rendering of the same projection to keep in step with the first.

    The poll is the journal's (1 s; LISTEN/NOTIFY is v1), so a follower never sees an event the
    store has not committed.
    """
    out.print("[dim]— following; ctrl-c to stop —[/]")
    with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
        async for e in keel.journal.tail(run_id, from_seq=from_seq):
            si = e.step_index
            out.print(
                f"{e.seq:>4} {e.lease_epoch:>3}  {e.type:<24}"
                f" {'-' if si is None else si:>3}  {_detail(e)}"
            )
            if e.type in TERMINAL_TYPES:
                out.print(f"[dim]— {e.type}; nothing further will be appended —[/]")
                return


def _detail(e: Any) -> str:
    b = e.body
    t = e.type
    if t == "RUN_CREATED":
        return f"{b.program} {b.program_version}"
    if t == "RECOVERY_STARTED":
        return f"cause={b.cause} from_seq={b.from_seq}" + (f" from_segment={b.from_segment}" if b.from_segment else "")
    if t == "SEGMENT_STARTED":
        return f"segment={b.segment_no} first_step={b.first_step_index}"
    if t == "RECOVERY_COMPLETED":
        return f"live_from_step={b.live_from_step} replayed_steps={b.replayed_steps}"
    if t == "STEP_INTENDED":
        cls = f" [{b.effect_class}]" if b.effect_class else ""
        return f"{b.kind} {b.name}{cls}"
    if t == "STEP_ATTEMPT_STARTED":
        return f"attempt={b.attempt_no}" + (f" deadline={b.attempt_deadline:%H:%M:%S}" if b.attempt_deadline else "")
    if t == "STEP_CHUNK":  # what streamed before an outcome, labelled by attempt (§10.7)
        return f"attempt={b.attempt_no} chunk={b.chunk_no} " + _short(b.blob, 30)
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
    if t == "PLAN_UPDATED":
        return f"{b.op} " + _short(b.diff, 40)
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
            # §16.1's memory snapshot, derived rather than stored: the plan and context projections
            # at this seq, and the latest continuation boundary's state blob.
            "plan": st.plan,
            "context": st.context,
            "segment": st.segment,
            "steps": list(st.steps.values()),
        }))

    _run(go())


async def _send(keel: Keel, run_ref: str, type_: str, payload: dict[str, Any], client_key: str | None) -> None:
    """Every control command is one row in the inbox and nothing else (§4.10).

    Not a conditional UPDATE, not a direct write: the CLI does not hold the lease and therefore may
    not decide anything. It states what it wants; the holder decides at the next step boundary, from
    the run's state at that moment. That is why a cancel sent to a finished run is refused here and
    a cancel sent twice is merely ignored there.
    """
    from keel.core.ids import uuid7
    from keel.journal.protocol import SignalRow

    run_id = await _resolve(keel, run_ref)
    ok = await keel.journal.insert_signal(
        SignalRow(
            signal_id=uuid7(),
            run_id=run_id,
            type=type_,
            payload=payload,
            client_key=client_key,
            source="api:cli",
        )
    )
    if not ok:
        err.print(f"[yellow]not sent: the run is terminal, or {client_key!r} was already used[/]")
        raise typer.Exit(EXIT_ERROR)
    out.print(f"{type_} queued for {run_id}")


@app.command()
def approve(
    run_ref: str,
    approval: Annotated[str | None, typer.Option("--approval", help="approval id; omit for the open one")] = None,
    by: Annotated[str, typer.Option("--by")] = "",
    client_key: Annotated[str | None, typer.Option("--client-key")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """Grant the open approval. The decision is journaled by the *holder* at the drain, not here."""
    _run(_decide(_load_app(app_ref, dsn), run_ref, "approve", {"by": by}, approval, client_key))


async def _decide(
    keel: Keel, run_ref: str, type_: str, payload: dict[str, Any], approval: str | None, client_key: str | None
) -> None:
    """A decision always names its gate (§7.5). Omitting `--approval` means *the approval open
    now*, resolved here from the journal and written into the row — so a click retried after that
    approval was decided is ignored as `approval_terminal` at the drain, instead of deciding
    whichever approval happens to be open by then."""
    if approval is None:
        from keel.state.fold import fold

        run_id = await _resolve(keel, run_ref)
        open_ = [a for a in fold(await keel.journal.read(run_id)).approvals.values() if not a.terminal]
        if not open_:
            err.print("[yellow]no open approval on this run; pass --approval to name one[/]")
            raise typer.Exit(EXIT_ERROR)
        approval = str(open_[-1].approval_id)
    await _send(keel, run_ref, type_, payload | {"approval_id": approval}, client_key)


@app.command()
def reject(
    run_ref: str,
    approval: Annotated[str | None, typer.Option("--approval")] = None,
    by: Annotated[str, typer.Option("--by")] = "",
    reason: Annotated[str, typer.Option("--reason")] = "",
    client_key: Annotated[str | None, typer.Option("--client-key")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """Refuse the open approval. The APPROVAL step still completes — with `rejected` — and the
    bound tool call is refused before it starts an attempt."""
    _run(_decide(_load_app(app_ref, dsn), run_ref, "reject", {"by": by, "reason": reason}, approval, client_key))


@app.command()
def cancel(
    run_ref: str,
    reason: Annotated[str, typer.Option("--reason")] = "",
    client_key: Annotated[str | None, typer.Option("--client-key")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """Ask a run to stop. Acknowledged at the next step boundary, never mid-step."""
    _run(_send(_load_app(app_ref, dsn), run_ref, "cancel", {"reason": reason}, client_key))


@app.command()
def pause(
    run_ref: str,
    client_key: Annotated[str | None, typer.Option("--client-key")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """Park a run at the next step boundary. Zero compute until `keel resume`."""
    _run(_send(_load_app(app_ref, dsn), run_ref, "pause", {}, client_key))


@app.command()
def signal(
    run_ref: str,
    type_: Annotated[str, typer.Option("--type", help="custom | timer | child_result | …")] = "custom",
    payload: Annotated[str, typer.Option("--payload", help="JSON object")] = "{}",
    resolve: Annotated[
        str | None, typer.Option("--resolve", help="STEP=completed|failed|cancelled: a human's decision")
    ] = None,
    evidence: Annotated[str, typer.Option("--evidence", help="what the human saw; journaled")] = "",
    result: Annotated[str | None, typer.Option("--result", help="JSON the step returns (completed)")] = None,
    client_key: Annotated[str | None, typer.Option("--client-key")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """One raw row in the inbox. A type with no handler is consumed as SIGNAL_IGNORED, journaled.

    `--resolve STEP=completed|failed` is the human decision for a RESOLVED_UNKNOWN step: one
    `custom{kind: resolve_step}` row, which also lifts the suspension — no `keel resume` after it
    (§7.2.1). `STEP=cancelled` is the ordinary cancel, closing that step with STEP_CANCELLED."""
    keel = _load_app(app_ref, dsn)
    if resolve is None:
        _run(_send(keel, run_ref, type_, json.loads(payload), client_key))
        return
    step, _, outcome = resolve.partition("=")
    if not step.isdigit() or outcome not in ("completed", "failed", "cancelled"):
        err.print("[red]--resolve STEP=completed|failed|cancelled, STEP a step index[/]")
        raise typer.Exit(EXIT_USAGE)

    async def go() -> None:
        run_id = await _resolve(keel, run_ref)
        ok = await keel.resolve_step(
            run_id, int(step), outcome, evidence=evidence,
            result=json.loads(result) if result is not None else None, client_key=client_key,
        )
        if not ok:
            err.print(f"[yellow]not sent: the run is terminal, or {client_key!r} was already used[/]")
            raise typer.Exit(EXIT_ERROR)
        out.print(f"resolve step {step} as {outcome} queued for {run_id}")

    _run(go())


@app.command()
def rebind(
    run_ref: str,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    client_key: Annotated[str | None, typer.Option("--client-key")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """Change the model binding for LIVE MODEL steps (§16.7) — one `rebind` row; the holder journals
    MODEL_BINDING_CHANGED at the drain. Memoized steps keep what the old binding answered."""
    binding = {k: v for k, v in (("provider", provider), ("model", model)) if v}
    if not binding:
        err.print("[red]give --provider and/or --model[/]")
        raise typer.Exit(EXIT_USAGE)
    _run(_send(_load_app(app_ref, dsn), run_ref, "rebind", {"model_config": binding}, client_key))


@app.command()
def resume(
    run_ref: str,
    client_key: Annotated[str | None, typer.Option("--client-key")] = None,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
) -> None:
    """Wake a paused or suspended run — one `resume` row in the inbox (§24.1).

    The MVP's direct `runnable_at` UPDATE is gone. It was a second control path, marked temporary
    when it was written, and two ways to influence a run is one more than the fence can defend.
    """
    _run(_send(_load_app(app_ref, dsn), run_ref, "resume", {}, client_key))


# --- replay ------------------------------------------------------------------
@app.command()
def replay(
    run_ref: str,
    verify_only: Annotated[bool, typer.Option("--verify", help="VERIFY: prove the program still agrees")] = True,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    strict: Annotated[bool, typer.Option("--strict", help="a changed prompt is a failure too")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """VERIFY: does the current program, given this journal, issue the same steps? (§10.9)

    No lease, no tokens, no effects. On a terminal run the logical projection hash is computed too,
    which is the thing C1 compares. A `replays` row records the pass, because VERIFY appends nothing
    to the journal and without the row the result would be a log line.
    """
    from keel.replay.verify import raise_for_drift, verify as run_verify

    if not verify_only:
        err.print("[red]RECOVER from the CLI is what `keel resume` and a worker do; only --verify here[/]")
        raise typer.Exit(EXIT_USAGE)
    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        run_id = await _resolve(keel, run_ref)
        row = await keel.journal.run_row(run_id)
        result = await run_verify(
            keel.journal,
            run_id,
            keel.resolve(row.program),  # the Program, so VERIFY can restore a boundary's state
            tools=keel.tools,
            requested_by="cli",
        )
        if json_out:
            out.print(_dump(result.as_dict()))
        else:
            colour = "green" if result.ok else "red"
            out.print(f"[{colour}]{result.status}[/]  run {run_id}  replayed {result.replayed_steps} steps")
            if result.live_from_step is not None:
                out.print(f"  live_from_step={result.live_from_step}")
            if result.projection_hash:
                out.print(f"  projection {result.projection_hash[:16]}")
            for d in result.drift:
                out.print(f"  [yellow]drift[/] step {d.step_index}: {d.journaled} -> {d.issued}")
            if result.diff:
                out.print(
                    f"  [red]step {result.diff['step_index']}[/]: journal {result.diff['journaled']} "
                    f"!= program {result.diff['issued']}"
                )
        if not result.ok:
            raise typer.Exit(EXIT_VERIFY_MISMATCH)
        if strict:
            try:
                raise_for_drift(result)
            except Exception as exc:  # noqa: BLE001 - --strict asked for this
                err.print(f"[red]{exc}[/]")
                raise typer.Exit(EXIT_VERIFY_MISMATCH) from exc

    _run(go())


@app.command()
def diff(
    run_a: str,
    run_b: str,
    app_ref: Annotated[str | None, typer.Option("--app")] = None,
    dsn: Annotated[str | None, typer.Option("--dsn")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Where two runs stop agreeing, step by step.

    Compares the *logical* projections (§10.5), so a run that crashed four times and probed its way
    to the answer reads as identical to one that never crashed — which is the only way the output
    is useful for the question people actually ask it: did the change I deployed change anything?
    """
    from keel.replay.determinism import logical_projection_hash
    from keel.replay.verify import diff_projections

    keel = _load_app(app_ref, dsn)

    async def go() -> None:
        a_id, b_id = await _resolve(keel, run_a), await _resolve(keel, run_b)
        a, b = fold(await keel.events(a_id)), fold(await keel.events(b_id))
        rows = diff_projections(a, b)
        if json_out:
            out.print(_dump({"a": str(a_id), "b": str(b_id), "same": not rows, "diff": rows}))
            return
        ha, hb = logical_projection_hash(a), logical_projection_hash(b)
        out.print(f"A {a_id}  {ha[:16]}")
        out.print(f"B {b_id}  {hb[:16]}")
        if not rows:
            out.print("[green]identical[/] logical projection")
            return
        table = Table(box=None)
        for col in ("at", "field", "A", "B"):
            table.add_column(col)
        for r in rows:
            if r["at"] == "phase":
                table.add_row("phase", "phase", str(r["a"]), str(r["b"]))
                continue
            for k in ("kind", "name", "args_hash", "state", "result_hash"):
                av = (r["a"] or {}).get(k)
                bv = (r["b"] or {}).get(k)
                if av != bv:
                    table.add_row(str(r["at"]), k, _short(av, 24), _short(bv, 24))
        out.print(table)

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
