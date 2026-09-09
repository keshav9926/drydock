"""Phase 2's demo: an effect that may or may not have landed is *surfaced and resolved*, not
guessed — and something outside the process knows the truth (§28.2).

    docker compose up -d postgres
    uv run python scripts/day2_demo.py

It starts a real World, a real `keel worker`, and kills the worker (SIGKILL) at the instant the
World has durably receipted the effect and the worker has not been told. Then it does it again
against a receiver that deduplicates, and prints what each band cost:

    EXTERNAL   @ issues.create (dedup: false)  →  AMBIGUOUS → probe → RESOLVED_COMPLETED, applied 1
    IDEMPOTENT @ issues.upsert (dedup: true)   →  re-fired under the same key, receipts 2, applied 1

The kill is aimed by watching the receiver's own oracle, never by sleeping and hoping — the same
discipline day 3's fault injector needs.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DSN = os.environ.get("KEEL_DSN", "postgresql://keel:keel@localhost:5432/keel")
APP = "keel.agents.demo:app"
PORT = int(os.environ.get("KEEL_WORLD_PORT", "8600"))
WORLD_URL = f"http://127.0.0.1:{PORT}"
LEASE_TTL = 2.0
TOOL_TIMEOUT = 1.0
HOLD_MS = 800  # the World withholds the response, so the kill lands inside the window

BANDS = [("EXTERNAL", "issues.create"), ("IDEMPOTENT", "issues.upsert")]


def oracle(path: str) -> dict:
    conn = HTTPConnection("127.0.0.1", PORT, timeout=5)
    try:
        conn.request("GET", path)
        return json.loads(conn.getresponse().read() or b"{}")
    finally:
        conn.close()


def keel(*argv: str, env: dict, check: bool = True) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "keel.cli.main", *argv],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf8", errors="replace",
    )
    if check and proc.returncode not in (0, 4):
        sys.exit(f"{' '.join(argv)} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def spawn(argv: list[str], env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", *argv], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


async def band(variant: str, endpoint: str, log: Path) -> None:
    env = {**os.environ, "KEEL_DSN": DSN, "KEEL_WORLD_URL": WORLD_URL,
           "KEEL_DEMO_VARIANT": variant, "COLUMNS": "100"}
    print(f"\n{'=' * 78}\n== band {variant} @ {endpoint} ==\n{'=' * 78}")
    world = spawn(
        ["crashproof.cli.main", "world", "--port", str(PORT),
         f"--hold={endpoint}={HOLD_MS}", "--log", str(log)],
        env,
    )
    try:
        await _await_world()
        await _truncate()
        run_id = keel("run", "tool_chain", "--app", APP, "--args", '{"task": "file an issue"}', env=env)
        print(f"run {run_id}")

        # Aim at the endpoint the hold is on, not at the first receipt of any kind: the PURE
        # search lands first, and killing there would measure a different window entirely.
        label = f"{endpoint}#1"
        w1 = spawn(["keel.cli.main", "worker", "--app", APP, "--lease-ttl", str(LEASE_TTL)], env)
        deadline = time.monotonic() + 30
        while not oracle("/oracle/receipts").get(label) and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
        if not oracle("/oracle/receipts").get(label):
            w1.kill()
            sys.exit(f"{label} never landed; nothing to be ambiguous about")
        w1.kill()
        w1.wait()
        print(f"  killed pid {w1.pid}: the World has the receipt, the journal has no outcome")

        wait_s = LEASE_TTL + TOOL_TIMEOUT + 1.0
        print(f"  waiting {wait_s:.0f}s for max(lease_expires_at, attempt_deadline)")
        await asyncio.sleep(wait_s)

        w2 = spawn(["keel.cli.main", "worker", "--app", APP, "--lease-ttl", str(LEASE_TTL)], env)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if '"phase": "COMPLETED"' in keel("show", run_id, "--app", APP, "--json", env=env):
                break
            await asyncio.sleep(0.1)
        w2.terminate()
        w2.wait()

        print()
        print(keel("events", run_id, "--app", APP, "--epoch", "all", env=env))
        print(keel("effects", run_id, "--app", APP, env=env))
        _verdict(endpoint)
    finally:
        world.terminate()
        world.wait()


def _verdict(endpoint: str) -> None:
    applied = oracle("/oracle/applied")
    receipts = oracle("/oracle/receipts")
    label = f"{endpoint}#1"
    got, sent = applied.get(label, 0), receipts.get(label, 0)
    print(f"\nWorld  {label}  receipts={sent}  applied={got}")
    print("       " + ("no duplicate effect" if got == 1 else f"DUPLICATE EFFECT (applied {got}x)"))


async def _await_world() -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if oracle("/health").get("ok"):
                return
        except OSError:
            await asyncio.sleep(0.05)
    sys.exit(f"the World never came up on {WORLD_URL}")


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


async def main() -> None:
    env = {**os.environ, "KEEL_DSN": DSN}
    print("== migrate ==")
    keel("db", "migrate", "--app", APP, env=env)
    for variant, endpoint in BANDS:
        log = ROOT / f".demo-receipts-{variant.lower()}.jsonl"
        log.unlink(missing_ok=True)
        await band(variant, endpoint, log)


if __name__ == "__main__":
    from keel.core import aio

    aio.run(main())
