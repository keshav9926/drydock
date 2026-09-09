"""Day 1's demo: a run that survives `kill -9` and resumes without re-deciding anything (§28.1).

    docker compose up -d postgres
    uv run python scripts/day1_demo.py

It starts a real `keel worker` subprocess, kills it (SIGKILL / TerminateProcess) at the instant the
effect has landed at the receiver but its outcome has not been journaled, waits for the lease and
the attempt deadline to pass, starts a second worker, and prints the journal.

The kill is aimed by polling the receiver's log, not by sleeping and hoping — the same discipline
day 3's fault injector needs.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SINK = ROOT / ".demo-sink.jsonl"
DSN = os.environ.get("KEEL_DSN", "postgresql://keel:keel@localhost:5432/keel")
APP = "keel.agents.demo:app"
LEASE_TTL = 2.0
TOOL_TIMEOUT = 1.0

ENV = {**os.environ, "KEEL_DSN": DSN, "KEEL_DEMO_SINK": str(SINK), "KEEL_DEMO_DELAY_MS": "800"}


def receipts() -> list[dict]:
    if not SINK.exists():
        return []
    return [json.loads(x) for x in SINK.read_text(encoding="utf8").splitlines() if x.strip()]


def keel(*argv: str, check: bool = True) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "keel.cli.main", *argv],
        cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf8", errors="replace",
    )
    if check and proc.returncode not in (0, 4):
        sys.exit(f"{' '.join(argv)} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def worker() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "keel.cli.main", "worker", "--app", APP, "--lease-ttl", str(LEASE_TTL)],
        cwd=ROOT, env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


async def main() -> None:
    SINK.unlink(missing_ok=True)
    print("== migrate ==")
    keel("db", "migrate", "--app", APP)
    await _truncate()

    run_id = keel("run", "tool_chain", "--app", APP, "--args", '{"task": "file an issue"}')
    print(f"== run {run_id} created ==")

    print("== worker 1: run until the effect has landed, then kill -9 ==")
    w1 = worker()
    deadline = time.monotonic() + 30
    while not receipts() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    if not receipts():
        w1.kill()
        sys.exit("the effect never landed; nothing to be ambiguous about")
    w1.kill()
    w1.wait()
    print(f"   killed pid {w1.pid} with the effect applied and no outcome journaled")

    wait_s = LEASE_TTL + TOOL_TIMEOUT + 1.0
    print(f"== waiting {wait_s:.0f}s for max(lease_expires_at, attempt_deadline) ==")
    await asyncio.sleep(wait_s)

    print("== worker 2: claims the orphan and re-executes from the journal ==")
    w2 = worker()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if '"phase": "COMPLETED"' in keel("show", run_id, "--app", APP, "--json"):
            break
        await asyncio.sleep(0.1)
    w2.terminate()
    w2.wait()

    print()
    print(keel("events", run_id, "--app", APP, "--epoch", "all"))
    print(keel("effects", run_id, "--app", APP))
    print(keel("show", run_id, "--app", APP))
    n = len(receipts())
    print(f"receiver saw {n} receipt(s) — {'no duplicate effect' if n == 1 else 'DUPLICATE EFFECT'}")


async def _truncate() -> None:
    from keel.journal.postgres import PostgresJournal

    j = PostgresJournal(DSN)
    pool = await j._ready()
    async with pool.connection() as conn:
        await conn.execute(
            "TRUNCATE artifacts, replays, recoveries, delegations, signals, effects, events,"
            " runs, blobs, programs RESTART IDENTITY CASCADE"
        )
    await j.close()


if __name__ == "__main__":
    from keel.core import aio

    aio.run(main())
