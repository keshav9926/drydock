"""The `crashproof` command tree (§25.3).

Day 2 ships `world` — the World alone, which is what an adapter is developed against and what the
day-2 demo aims a kill into. `inject`, `chaos`, `bench` and `report` arrive with the supervisor and
the matrix on day 3.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Annotated

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


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
