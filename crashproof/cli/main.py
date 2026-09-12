"""The `crashproof` command tree (§25.3).

    inject   one trial, printed in full — the developer form
    chaos    one cell: n seeds of one spec against one adapter
    bench    a matrix of cells, resumable
    report   the cells folded into a page
    verify   the verifier re-run over facts already on disk — nothing executed
    compare  two arms, paired per (location, fault)
    world    the World alone, for adapter development

`--seed N --seeds K` means seeds N … N+K-1, one trial per seed, trial id `t-<seed>`. There is no
`--trials`, because a cell is a set of seeds: `(spec_hash, seed)` is the reproduction key and the
pairing key at once, and that is only true if the seed varies per trial.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from crashproof.workloads.spec import load, load_named
from crashproof.world.server import WorldServer
from crashproof.world.services import world_from_endpoints

for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(add_completion=False, help="Crashproof - fault injection and conformance for agent runtimes.")
out = Console()
err = Console(stderr=True)

#: Adapters that exist. A cell naming one that does not is reported as a missing arm rather than
#: quietly dropped: a missing arm and an N/A arm are different findings (§13.3).
ADAPTERS: dict[str, Any] = {}


def _adapters() -> dict[str, Any]:
    if not ADAPTERS:
        from crashproof.adapters.keel import KeelAdapter

        ADAPTERS["keel"] = KeelAdapter
        try:
            from crashproof.adapters.langgraph import LangGraphAdapter

            ADAPTERS["langgraph"] = LangGraphAdapter
        except ImportError:  # the extra is not installed; the column prints as a missing arm
            pass
    return ADAPTERS


def _run(coro: Any) -> Any:
    """psycopg cannot use Windows' default event loop, and the adapters open connections."""
    from crashproof.runner import aio

    return aio.run(coro)


def _commit() -> str:
    import subprocess

    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:  # pragma: no cover
        return ""


# --- world -------------------------------------------------------------------
@app.command()
def world(
    workload: Annotated[str, typer.Option("--workload", help="name in workloads/scripts, or a path")] = "tool_chain_1_effect",
    port: Annotated[int, typer.Option("--port")] = 8600,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    dedup: Annotated[list[str], typer.Option("--dedup", help="endpoint=true|false, repeatable")] = None,
    natural: Annotated[list[str], typer.Option("--natural", help="endpoint=true|false, repeatable")] = None,
    hold: Annotated[list[str], typer.Option("--hold", help="endpoint=ms, repeatable")] = None,
    log: Annotated[Path | None, typer.Option("--log", help="receipt log (JSONL, fsynced)")] = None,
) -> None:
    """Run the World: deterministic services, a fsynced receipt log, and the oracle."""
    wl = load(workload) if Path(workload).exists() else load_named(workload)
    w = world_from_endpoints(wl.endpoint_decls(), log_path=log)
    for spec in dedup or []:
        name, _, value = spec.partition("=")
        w.set_dedup(name, dedup=value.lower() in ("1", "true", "yes"))
    for spec in natural or []:
        name, _, value = spec.partition("=")
        w.set_dedup(name, natural=value.lower() in ("1", "true", "yes"))
    for spec in hold or []:
        name, _, value = spec.partition("=")
        w.hold(name, float(value))

    server = WorldServer(w, host=host, port=port)

    async def go() -> None:
        bound = await server.start()
        err.print(f"world {wl.workload} spec={wl.spec_hash} on http://{host}:{bound}")
        table = Table(box=None)
        for col in ("endpoint", "kind", "dedup", "natural", "hold_ms"):
            table.add_column(col)
        for e in w.endpoints.values():
            table.add_row(e.id, e.kind, str(e.dedup), str(e.natural), str(w.hold_ms(e.id)))
        err.print(table)
        await server.serve_forever()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(go())
    out.print(json.dumps({"applied": w.applied_counts(), "receipts": w.receipt_counts()}))


@app.command()
def workloads() -> None:
    """List the canonical workloads and what each variant is measured against."""
    wl = load_named("tool_chain_1_effect")
    table = Table(box=None)
    for col in ("workload", "variant", "key_source", "tool", "class", "endpoint", "required"):
        table.add_column(col)
    for name, variant in wl.variants.items():
        for tool in wl.tools_for(name):
            table.add_row(
                wl.workload, name, variant.key_source, tool.name, tool.effect_class,
                tool.endpoint, ",".join(variant.required_effects),
            )
    out.print(table)


# --- inject / chaos ----------------------------------------------------------
#: §25.2's exit codes. A harness whose failure mode is a line of red text in a log nobody reads is
#: not a CI gate; these are what a pipeline actually branches on.
EXIT_INVARIANT_FAIL = 7
EXIT_TOO_NOISY = 8


def _violated(rows: list[Any]) -> bool:
    """A FAIL in any *scored* trial. A void trial has no verdict to fail: the harness did not take
    the measurement, which is a different thing from the runtime breaking a rule."""
    return any(
        v == "FAIL"
        for r in rows
        if getattr(r, "valid", True)
        for v in (r.verdicts if hasattr(r, "verdicts") else {}).values()
    )


@app.command()
def inject(
    adapter: Annotated[str, typer.Option("--adapter")] = "keel",
    workload: Annotated[str, typer.Option("--workload")] = "tool_chain_1_effect",
    variant: Annotated[str, typer.Option("--variant")] = "EXTERNAL",
    spec: Annotated[Path | None, typer.Option("--spec", help="fault spec YAML; omit for a baseline")] = None,
    seed: Annotated[int, typer.Option("--seed")] = 7,
    out_dir: Annotated[Path, typer.Option("--out")] = Path("bench/trials"),
) -> None:
    """One trial, printed in full. The developer form of what `chaos` does thirty times."""
    rows = _cell(adapter, workload, variant, spec, seed, 1, out_dir, verbose=True)
    raise typer.Exit(EXIT_INVARIANT_FAIL if _violated(rows) else 0)


@app.command()
def chaos(
    adapter: Annotated[str, typer.Option("--adapter")] = "keel",
    workload: Annotated[str, typer.Option("--workload")] = "tool_chain_1_effect",
    variant: Annotated[str, typer.Option("--variant")] = "EXTERNAL",
    spec: Annotated[Path | None, typer.Option("--spec")] = None,
    seed: Annotated[int, typer.Option("--seed", help="the first seed")] = 7,
    seeds: Annotated[int, typer.Option("--seeds", help="how many, one trial each")] = 30,
    out_dir: Annotated[Path, typer.Option("--out")] = Path("bench/results/chaos"),
) -> None:
    """One cell: n seeds of one spec against one adapter."""
    rows = _cell(adapter, workload, variant, spec, seed, seeds, out_dir, verbose=False)
    raise typer.Exit(EXIT_INVARIANT_FAIL if _violated(rows) else 0)


def _cell(
    adapter_name: str,
    workload_name: str,
    variant: str,
    spec_path: Path | None,
    base_seed: int,
    seeds: int,
    out_dir: Path,
    *,
    verbose: bool,
) -> list[Any]:
    from crashproof.faults.spec import from_doc
    from crashproof.faults.spec import load as load_spec
    from crashproof.runner.store import ResultStore, slug
    from crashproof.runner.trial import run_trial

    factory = _adapters().get(adapter_name)
    if factory is None:
        err.print(f"[red]no adapter {adapter_name!r}; built: {sorted(_adapters())}[/]")
        raise typer.Exit(2)
    wl = load_named(workload_name)
    spec = (
        load_spec(spec_path)
        if spec_path
        else from_doc({"name": "baseline", "workload": workload_name, "mode": "shim", "faults": []})
    )
    store = ResultStore(out_dir)
    rows: list[Any] = []
    # `<results>/<slug(cell_id)>/<trial_id>` is a rule, not a convention: `crashproof verify` finds
    # a published row's trial directory by applying it, and a second spelling here would mean it
    # could find a bench row's directory and not a chaos row's.
    cell_id = f"{adapter_name}.default.{variant}.{spec.name}"

    async def go() -> None:
        for seed in range(base_seed, base_seed + seeds):
            row = await run_trial(
                adapter=factory(wl, variant),
                workload=wl,
                variant=variant,
                spec=spec,
                seed=seed,
                out_dir=out_dir / slug(cell_id),
                cell_id=cell_id,
                keel_commit=_commit(),
            )
            store.append(row.as_dict())
            rows.append(row)
            _print_row(row, verbose=verbose)

    _run(go())
    return rows


def _print_row(row: Any, *, verbose: bool) -> None:
    verdicts = " ".join(
        f"{k}{'OK' if v == 'PASS' else 'X' if v == 'FAIL' else '-'}" for k, v in row.verdicts.items()
    )
    raw = row.metrics["raw"]
    out.print(
        f"{row.trial_id}  {row.status:<10} restarts={row.restarts}  {verdicts}  "
        f"applied={raw['world_applied']} receipts={raw['world_receipts']}"
    )
    if not verbose:
        return
    for f in row.faults:
        out.print(f"   fault {f['type']} @ {f['boundary']} {f['landmark']} executed={f['executed']}")
    for c in row.counterexamples:
        err.print(f"   [red]{c['invariant']}: {c['detail']}[/]")
    out.print(f"   result: {json.dumps(row.result, default=str)[:100]}")


# --- bench / report ----------------------------------------------------------
@app.command()
def bench(
    matrix: Annotated[Path, typer.Option("--matrix")] = Path("bench/specs/matrix_v0.yaml"),
    seeds: Annotated[int | None, typer.Option("--seeds")] = None,
    base_seed: Annotated[int | None, typer.Option("--base-seed")] = None,
    cells: Annotated[list[str], typer.Option("--cells", help="glob, repeatable")] = None,
    out_dir: Annotated[Path, typer.Option("--out")] = Path("bench/results/latest"),
    resume: Annotated[bool, typer.Option("--resume")] = False,
) -> None:
    """Run a matrix. Baselines first, because every delta metric is paired against one."""
    from crashproof.runner.bench import Matrix, run_matrix

    m = Matrix.load(matrix)
    if seeds is not None:
        m.seeds = seeds
    if base_seed is not None:
        m.base_seed = base_seed
    err.print(f"matrix {m.workload}: {len(m.cells())} cells x {m.seeds} seeds -> {out_dir}")

    def on_row(row: Any, cell: Any, note: str | None) -> None:
        if note:
            err.print(f"[yellow]{cell.id}: {note}[/]")
            return
        _print_row(row, verbose=False)

    _run(
        run_matrix(
            m,
            out_dir=out_dir,
            adapters=_adapters(),
            cells=list(cells or []),
            resume=resume,
            on_row=on_row,
            keel_commit=_commit(),
        )
    )
    report(out_dir, fmt="md", out_path=out_dir / "matrix.md")
    from crashproof.report.matrix import fold
    from crashproof.runner.store import ResultStore

    cells = fold(list(ResultStore(out_dir).rows()))
    if any(v == "FAIL" for c in cells.values() for v in c.verdicts.values()):
        raise typer.Exit(EXIT_INVARIANT_FAIL)


@app.command()
def report(
    results: Annotated[Path, typer.Argument()] = Path("bench/results/latest"),
    fmt: Annotated[str, typer.Option("--fmt")] = "md",
    out_path: Annotated[Path | None, typer.Option("--out")] = None,
    mdd: Annotated[bool, typer.Option("--mdd", help="also echo the MDD tables to stdout")] = False,
) -> None:
    """Fold the rows into cells and render the matrix.

    `--mdd` echoes §15.7's tables to stdout. It does not gate them: they are in every rendered page
    whatever the flag says (§15.11 rule 6), because "you only ran it thirty times" is an objection
    a reader has while looking at the page.
    """
    from crashproof.report.markdown import render
    from crashproof.report.matrix import fold
    from crashproof.runner.store import ResultStore
    from crashproof.stats.ci import MDD_TABLES

    rows = list(ResultStore(results).rows())
    if not rows:
        err.print(f"[red]no results in {results}[/]")
        raise typer.Exit(1)
    if fmt != "md":
        err.print("[red]only --fmt md is built; html is v1 (§27.9)[/]")
        raise typer.Exit(2)
    page = render(fold(rows), workload=rows[0]["workload"], title=results.name)
    target = out_path or results / "matrix.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf8")
    err.print(f"wrote {target}  ({len(rows)} trials)")
    if mdd:
        out.print(MDD_TABLES)


@app.command()
def verify(
    target: Annotated[Path, typer.Argument(help="a trial directory, or a results.jsonl")],
    recheck: Annotated[bool, typer.Option("--recheck", help="re-verify and diff against what was published")] = False,
    placement: Annotated[bool, typer.Option("--placement", help="where each fault landed (§19.5)")] = False,
    effects: Annotated[bool, typer.Option("--effects", help="the per-effect ledger (§19.5)")] = False,
    invariant: Annotated[list[str], typer.Option("--invariant", help="restrict to these, repeatable")] = None,
) -> None:
    """Re-run the verifier over facts already on disk. Nothing is executed and nothing is measured.

    The argument is a trial directory or a `results.jsonl`, never a results directory root: a root
    holds many cells and "verify this" would have no single answer. `--recheck` is the publication
    gate — it re-runs the verifier over every row's own trial directory and compares the result
    both against a second run of itself and against the verdict that was published. The first
    catches a verdict that is not a function of the logs; the second catches a results file that
    has drifted from the directories it claims to summarise.
    """
    import json

    from crashproof.runner.store import ResultStore, slug
    from crashproof.verifier import invariants, views

    def facts_of(trial_dir: Path):
        path = trial_dir / "facts.json"
        if not path.exists():
            return None
        return invariants.load(json.loads(path.read_text(encoding="utf8")))

    def canonical(facts) -> str:
        """What `--recheck` compares. Details and counterexamples are in it, not just the verdict
        letters: a verdict that stayed PASS while its reason changed is still a verifier that is
        not a pure function of its inputs."""
        v = invariants.verify(facts)
        return json.dumps(
            {
                "verdicts": v.as_dict(),
                "details": {n: f.detail for n, f in sorted(v.findings.items())},
                "counterexamples": v.counterexamples(),
            },
            sort_keys=True,
            default=str,
        )

    def show(trial_dir: Path, facts) -> None:
        v = invariants.verify(facts)
        wanted = set(invariant or []) or set(v.findings)
        table = Table(box=None, title=str(trial_dir))
        for col in ("invariant", "verdict", "detail"):
            table.add_column(col)
        for name, finding in v.findings.items():
            if name in wanted:
                colour = {"PASS": "green", "FAIL": "red"}.get(finding.verdict, "yellow")
                table.add_row(name, f"[{colour}]{finding.verdict}[/]", finding.detail)
        out.print(table)
        if placement:
            rows = views.placement(facts)
            p = Table(box=None, title="placement — where the schedule aimed, and where it landed")
            for col in ("fault", "boundary", "landmark", "#", "rec", "ran", "last seq",
                        "open step", "next seq", "recovery", "receipt before", "receipt after"):
                p.add_column(col)
            for r in rows:
                p.add_row(
                    r["type"], r["boundary"], r["landmark"], str(r["occurrence"]),
                    str(r["recovery_index"]), "yes" if r["executed"] else "[red]no[/]",
                    _n(r["last_seq_before"]), _n(r["open_step"]), _n(r["first_seq_after"]),
                    _n(r["recovery_seq"]), _n(r["receipt_before"]), _n(r["receipt_after"]),
                )
            out.print(p)
            if not rows:
                err.print("[yellow]no faults fired in this trial[/]")
        if effects:
            e = Table(box=None, title="effect ledger — one row per logical effect")
            for col in ("identity", "key", "class", "status", "started", "outcome",
                        "receipts", "applied", "claim", "S1", "S2", "S3", "S4", "C3"):
                e.add_column(col)
            for r in views.effect_ledger(facts):
                e.add_row(
                    r["identity"], r["effect_key"] or "—", r["effect_class"] or "—", r["status"] or "—",
                    _n(r["started_seq"]), _n(r["outcome_seq"]), str(r["world_receipts"]),
                    str(r["world_applied"]), r["claim"],
                    *(_verdict(r[k]) for k in ("S1", "S2", "S3", "S4", "C3")),
                )
            out.print(e)

    if target.is_dir():
        facts = facts_of(target)
        if facts is None:
            err.print(f"[red]{target} holds no facts.json; it is not a trial directory[/]")
            raise typer.Exit(2)
        show(target, facts)
        if recheck and canonical(facts) != canonical(facts):
            err.print("[red]the verifier is not a function of its inputs[/]")
            raise typer.Exit(EXIT_INVARIANT_FAIL)
        raise typer.Exit(EXIT_INVARIANT_FAIL if invariants.verify(facts).failed else 0)

    if target.name != "results.jsonl":
        err.print("[red]verify takes a trial directory or a results.jsonl, never a results root[/]")
        raise typer.Exit(2)

    root = target.parent
    rows = list(ResultStore(root).rows())
    missing, drifted, unstable, failed = [], [], [], []
    for row in rows:
        trial_dir = root / slug(row["cell_id"]) / row["trial_id"]
        facts = facts_of(trial_dir)
        if facts is None:
            missing.append(f"{row['cell_id']}/{row['trial_id']}")
            continue
        first = canonical(facts)
        if recheck and first != canonical(facts):
            unstable.append(f"{row['cell_id']}/{row['trial_id']}")
        fresh = invariants.verify(facts)
        if fresh.as_dict() != row["verdicts"]:
            drifted.append(f"{row['cell_id']}/{row['trial_id']}: {row['verdicts']} -> {fresh.as_dict()}")
        if fresh.failed and row.get("valid", True):
            failed.append(f"{row['cell_id']}/{row['trial_id']}: {fresh.failed}")

    err.print(f"{len(rows) - len(missing)} of {len(rows)} rows re-verified from their trial directories")
    for label, items, colour in (
        ("no facts.json", missing, "yellow"),
        ("verdict drifted from the published row", drifted, "red"),
        ("verifier not a function of its inputs", unstable, "red"),
        ("invariant FAIL", failed, "red"),
    ):
        for item in items[:10]:
            err.print(f"[{colour}]{label}: {item}[/]")
        if len(items) > 10:
            err.print(f"[{colour}]{label}: ... and {len(items) - 10} more[/]")
    # A missing facts.json is a trial from before the file existed, not a failure of this one.
    # Drift and instability are what the publication gate is for, and either one is exit 7.
    if drifted or unstable or failed:
        raise typer.Exit(EXIT_INVARIANT_FAIL)


def _n(value: Any) -> str:
    return "—" if value is None else str(value)


def _verdict(value: str) -> str:
    return {"PASS": "[green]PASS[/]", "FAIL": "[red]FAIL[/]"}.get(value, "[yellow]N/A[/]")


@app.command()
def compare(
    results: Annotated[Path, typer.Argument(help="a results directory")] = Path("bench/results/latest"),
    a: Annotated[str, typer.Option("--a", help="cell-id glob for arm A")] = "keel.*",
    b: Annotated[str, typer.Option("--b", help="cell-id glob for arm B")] = "langgraph.sync.*",
    out_path: Annotated[Path | None, typer.Option("--out")] = None,
    seed: Annotated[int, typer.Option("--seed", help="bootstrap seed")] = 7,
    strict: Annotated[bool, typer.Option("--strict", help="exit 8 if nothing can be claimed")] = False,
) -> None:
    """Compare two arms, paired on (workload, variant, trigger, spec_hash, seed)."""
    import fnmatch

    from crashproof.report.compare import compare as run_compare
    from crashproof.report.compare import render
    from crashproof.runner.store import ResultStore

    rows = list(ResultStore(results).rows())
    a_rows = [r for r in rows if fnmatch.fnmatch(r["cell_id"], a)]
    b_rows = [r for r in rows if fnmatch.fnmatch(r["cell_id"], b)]
    if not a_rows or not b_rows:
        err.print(f"[red]nothing to compare: A={len(a_rows)} rows, B={len(b_rows)} rows[/]")
        raise typer.Exit(1)
    result = run_compare(a_rows, b_rows, a_name=a, b_name=b, seed=seed)
    page = render(result)
    if out_path is None:
        out.print(page)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(page, encoding="utf8")
        err.print(f"wrote {out_path}")
    # `--strict` only: the default prints the verdict and exits 0, because "too noisy to claim" is
    # an answer, not an error. A gate that wants to fail on it has to say so (§25.2). "Not
    # claimable" counts the same way here: a comparison that establishes nothing establishes
    # nothing, whether the reason was the sample size or the confound.
    if strict and not any(r.claimed() for r in result.rows):
        raise typer.Exit(EXIT_TOO_NOISY)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
