"""K11(a): kill the World process mid-request, and read the log it left behind (§30, §28.2).

The instrument's claim is one ordering: a receipt is written and **fsynced before the response is
computed** (`crashproof/world/services.py`), which is what makes `after:tool_effect` a boundary and
not a guess. §30 checks it by killing the World process over 300 seeds and looking for "any receipt
missing from the World log".

What is observable after a SIGKILL is the log, and the only reading that convicts is a client that
**was answered** for a request whose receipt is not in it: the response can only have been computed
before the log reached disk. The other three outcomes are all consistent with the contract.

    answered + receipt     the kill landed after the answer
    no answer + receipt    the kill landed after the receipt and before the client heard
    no answer + no receipt the kill landed before the World wrote anything
    answered + no receipt  K11(a) FIRES

Three bands, because an audit that cannot fail on a broken World says nothing about a correct one:

    natural   the kill at a delay drawn from the measured round trip of the same endpoint
    held      the response withheld for seconds, so the kill lands after the receipt and the
              effect and before the caller hears — the "no answer + receipt" column
    mutant    CALIBRATION. `scripts/_k11_world.py` defers the receipt to `gap` ms *after* the
              answer, which is the implementation K11(a) exists to catch. The audit is only
              believable if this band convicts.

The reach this buys, stated rather than implied: a kill from outside is itself slow — measured at
0.5 to 1.1 s on this platform, which is `taskkill` spawning — so the audit detects a mis-ordering
whose gap is of that order or wider (the calibration band pins it) and cannot detect one of
microseconds. What it cannot see at all is an effect that crossed
into the World's own memory without a receipt: `applied` is in-memory and dies with the
process, so the receipt log is the whole of what a killed World leaves behind.

    uv run python scripts/k11_oracle_audit.py --seeds 300 --out <path>.md
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import socket
import subprocess
import sys
import tempfile
import threading
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from crashproof.faults import process  # noqa: E402
from crashproof.world.client import WorldClient  # noqa: E402

AUDITED = {"title": "K11 audit", "body": "kill between receipt and response"}
WARM = {"title": "K11 warm", "body": "the round trip of the endpoint under test"}
HELD_MS = 4000     # wider than the kill's own latency, measured at 0.5-1.1 s on this platform
MUTANT_GAP_MS = 4000
BANDS = ("natural", "held", "mutant")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start(log: pathlib.Path, band: str) -> tuple[subprocess.Popen, WorldClient, float]:
    """A World of its own, answering, with the round trip it answers `issues.create` in."""
    port = _free_port()
    cmd = [sys.executable, str(REPO / "scripts" / "_k11_world.py"),
           "world", "--port", str(port), "--log", str(log)]
    if band == "held":
        cmd += ["--hold", f"issues.create={HELD_MS}"]
    env = {**os.environ, "K11_MUTATE_GAP_MS": str(MUTANT_GAP_MS)} if band == "mutant" else None
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            cwd=str(REPO), env=env)
    client = WorldClient(f"http://127.0.0.1:{port}", timeout=5.0)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            client.call("kv.search", {"q": "ready"})
            break
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("the World exited before it answered")
            time.sleep(0.02)
    else:
        raise RuntimeError("the World never answered")
    # The round trip is measured on the endpoint under test, not on a read: `issues.create` applies,
    # and a delay drawn from a cheaper code path aims at the wrong instant. The warm-up carries its
    # own identity, so `_receipted` never mistakes it for the audited request.
    t0 = time.perf_counter()
    client.call("issues.create", dict(WARM))
    rtt = time.perf_counter() - t0
    if band == "held":
        rtt -= HELD_MS / 1000.0  # the warm-up was held too; the round trip is what is left
    return proc, client, max(rtt, 0.001)


def _receipted(log: pathlib.Path) -> bool:
    """Is the audited request — not the warm-up — in the log the dead process left?"""
    if not log.exists():
        return False
    for line in log.read_text(encoding="utf8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a line torn by the kill is not a receipt
        if row.get("endpoint") == "issues.create" and (row.get("args") or {}).get("title") == AUDITED["title"]:
            return True
    return False


def trial(seed: int, band: str, tmp: pathlib.Path) -> dict:
    """One kill. The request goes out on a thread; the kill lands a drawn delay later."""
    log = tmp / f"receipts-{band}-{seed}.jsonl"
    proc, client, rtt = _start(log, band)
    answered: list[bool] = []

    def send() -> None:
        try:
            client.call("issues.create", dict(AUDITED))
            answered.append(True)
        except Exception:
            answered.append(False)

    rng = random.Random(seed)
    if band == "natural":
        delay = rng.uniform(0, 3 * rtt)
    elif band == "held":                     # inside the hold, which follows the receipt
        delay = rtt * 0.5 + rng.uniform(HELD_MS * 0.05, HELD_MS * 0.35) / 1000.0
    else:                                    # inside the mutant's gap, which follows the answer
        delay = rtt + rng.uniform(MUTANT_GAP_MS * 0.05, MUTANT_GAP_MS * 0.35) / 1000.0

    sender = threading.Thread(target=send, daemon=True)
    t0 = time.perf_counter()
    sender.start()
    while time.perf_counter() - t0 < delay:
        time.sleep(0.0002)
    process.kill(proc.pid)  # the harness's own killer, so the audit measures the same instrument
    sender.join(timeout=60)
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        # `taskkill` spawns a process to do its work and can be starved on a loaded machine; this
        # one is a syscall. A trial whose kill had to be repeated is still a kill.
        proc.kill()
        proc.wait(timeout=60)
    got = bool(answered and answered[0])
    has = _receipted(log)
    try:  # a process Windows has just killed can hold its handle open a moment longer
        log.unlink(missing_ok=True)
    except OSError:
        pass
    return {"seed": seed, "band": band, "answered": got, "receipt": has,
            "rtt_ms": round(rtt * 1000, 2), "kill_at_ms": round(delay * 1000, 2),
            "outcome": "VIOLATION" if (got and not has) else
                       "answered" if got else "in window" if has else "before receipt"}


def run(seeds: int, bands: tuple[str, ...], calibration_seeds: int, quiet: bool = False,
        held_seeds: int | None = None, rows_out: pathlib.Path | None = None) -> list[dict]:
    rows: list[dict] = []
    counts = {"mutant": calibration_seeds, "held": seeds if held_seeds is None else held_seeds}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = pathlib.Path(td)
        for band in bands:
            for seed in range(counts.get(band, seeds)):
                rows.append(trial(seed, band, tmp))
                r = rows[-1]
                if rows_out is not None:  # one line per trial: a crash keeps what it measured
                    with rows_out.open("a", encoding="utf8") as fh:
                        fh.write(json.dumps(r) + "\n")
                if not quiet:
                    print(f"  {r['band']:8s} seed {seed:3d}  rtt {r['rtt_ms']:6.2f} ms  "
                          f"kill@ {r['kill_at_ms']:7.2f} ms  {r['outcome']}", flush=True)
    return rows


def page(rows: list[dict], seeds: int, elapsed: float) -> tuple[str, bool, bool]:
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        counts[(r["band"], r["outcome"])] = counts.get((r["band"], r["outcome"]), 0) + 1
    bands = [b for b in BANDS if any(r["band"] == b for r in rows)]
    calibrated = counts.get(("mutant", "VIOLATION"), 0) > 0
    audited = [b for b in bands if b != "mutant"]
    violations = sum(counts.get((b, "VIOLATION"), 0) for b in audited)
    lines = [
        "# K11(a) — the oracle audited by killing it (§30, §28.2)",
        "",
        "The World writes a receipt and fsyncs it *before* it computes the response"
        " (`crashproof/world/services.py`), which is what every `after:tool_effect` cell in the matrix"
        " rests on. This audit kills the World process mid-request and reads the log the dead process"
        " left. It convicts on one outcome: a client **answered** for a request with no receipt.",
        "",
        f"Run {time.strftime('%Y-%m-%dT%H:%M:%S%z')} · {len(rows)} trials · {elapsed:.0f} s ·"
        f" natural {sum(1 for r in rows if r['band'] == 'natural')}"
        f" · held {sum(1 for r in rows if r['band'] == 'held')}"
        f" · calibration {sum(1 for r in rows if r['band'] == 'mutant')}",
        "",
        "| band | answered + receipt | killed in the window (receipt, no answer) | before the receipt | **answered, no receipt** |",
        "|---|---|---|---|---|",
    ]
    label = {"natural": "`natural`", "held": "`held`", "mutant": "`mutant` — calibration"}
    for b in bands:
        lines.append(f"| {label[b]} | {counts.get((b, 'answered'), 0)} | {counts.get((b, 'in window'), 0)} "
                     f"| {counts.get((b, 'before receipt'), 0)} | **{counts.get((b, 'VIOLATION'), 0)}** |")
    lines += [
        "",
        f"**Calibration: the audit {'convicts' if calibrated else 'DOES NOT convict'} the mis-ordered"
        f" World.** `scripts/_k11_world.py` defers the receipt {MUTANT_GAP_MS} ms past the answer — the"
        " implementation K11(a) exists to catch — and the `mutant` band "
        + ("scores it a violation, so the instrument has power."
           if calibrated else "did not catch it, so this run establishes nothing."),
        "",
        f"**K11(a): {'FIRES' if violations else 'not fired'}** — {violations} of"
        f" {sum(1 for r in rows if r['band'] != 'mutant')} audited trials were answered without a"
        " receipt in the log.",
        "",
        "**Reach.** A kill from outside is itself slow — 0.5 to 1.1 s on this platform, which is"
        " `taskkill` spawning — so this audit sees a mis-ordering whose gap is of that order or wider"
        f" (calibrated at {MUTANT_GAP_MS} ms) and cannot see one of microseconds; the `natural` band's"
        " kills land after the answer for that reason, and"
        " the `held` band's land after the receipt because a held response is withheld"
        " *after* `receive` has logged, applied and computed it. What no post-mortem of a killed World"
        " can see is an effect that crossed into its memory without a receipt: `applied` is in-memory"
        " and dies with the process, so the receipt log is the whole of what it leaves behind. The"
        " ordering itself is asserted structurally by"
        " `tests/unit/test_world.py::test_receipt_is_durable_before_the_response_is_computed`, and this"
        " audit's power is pinned in CI by `tests/unit/test_k11_audit.py`.",
    ]
    return "\n".join(lines) + "\n", bool(violations), calibrated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--held-seeds", type=int, default=100)
    ap.add_argument("--calibration-seeds", type=int, default=100)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--bands", default=",".join(BANDS))
    args = ap.parse_args()

    t0 = time.time()
    rows = run(args.seeds, tuple(args.bands.split(",")), args.calibration_seeds,
               held_seeds=args.held_seeds,
               rows_out=args.out.with_suffix(".jsonl") if args.out else None)
    text, fired, calibrated = page(rows, args.seeds, time.time() - t0)
    print("\n" + text)
    if args.out:
        args.out.write_text(text, encoding="utf8", newline="\n")
        # the rows are beside it already: `run` appended each one as its trial finished
    return 1 if (fired or not calibrated) else 0


if __name__ == "__main__":
    raise SystemExit(main())
