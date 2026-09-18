"""The per-epoch workspace checkout (§20.5, §9.3): LOCAL_FS's reordering window, closed by directory.

The MVP window: a worker paused past its lease resumes, and its stale write lands in the run's one
directory *after* the successor's newer write. The v1 answer is that the two never share a directory —
so the tests are about exactly that: what a successor's checkout carries forward, and what a zombie's
late write can no longer touch.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from keel import EffectClass, Keel, Modifier, program, tool
from keel.core.clock import FakeClock
from keel.core.errors import ContractViolation
from keel.journal.memory import MemoryJournal
from keel.runtime.sandbox import LocalSandbox
from keel.state.fold import fold

TTL = 2.0
SEEN: list[Path | None] = []
STALL = asyncio.Event()
STALLED: list[bool] = []


@tool(effect=EffectClass.IDEMPOTENT, timeout=1.0, modifiers=(Modifier.LOCAL_FS,), name="write_file")
async def write_file(args: dict[str, Any], tctx: Any) -> dict[str, Any]:
    """IDEMPOTENT by content: the full file, temp then replace."""
    SEEN.append(tctx.workspace)
    if args.get("stall") and not STALLED:
        STALLED.append(True)
        await STALL.wait()  # the first attempt stalls past its lease: the zombie that finishes late
    target = tctx.workspace / args["path"]
    tmp = target.with_suffix(".tmp")
    tmp.write_text(args["text"], encoding="utf8")
    tmp.replace(target)
    return {"wrote": args["path"]}


@program(name="editor", version="1.0")
async def editor(ctx: Any, args: dict[str, Any]) -> Any:
    await ctx.tool("write_file", path="a.py", text="v1")
    await ctx.tool("write_file", path="b.py", text="b", stall=args.get("stall", False))
    await ctx.tool("write_file", path="a.py", text="v2")
    return "edited"


def test_a_checkout_copies_the_newest_earlier_epoch_and_nothing_after(tmp_path: Path) -> None:
    box = LocalSandbox(tmp_path)
    one = box.checkout("run", 1)
    (one / "a.py").write_text("v1")
    assert box.checkout("run", 1) == one, "an epoch has one directory"
    three = box.checkout("run", 3)  # epoch 2 never touched the workspace
    assert (three / "a.py").read_text() == "v1"
    (one / "a.py").write_text("stale")  # the zombie of epoch 1, after epoch 3 checked out
    assert (three / "a.py").read_text() == "v1", "a dead epoch's write lands in the dead directory"
    assert sorted(p.name for p in (tmp_path / "run").iterdir()) == ["1", "3"], "no torn temp directory left"


def test_local_fs_is_pure_or_idempotent_by_content() -> None:
    with pytest.raises(ContractViolation, match="LOCAL_FS"):
        tool(effect=EffectClass.EXTERNAL, modifiers=(Modifier.LOCAL_FS,), name="rm")(write_file._fn)


async def test_a_successor_re_runs_in_its_own_checkout_and_a_zombie_cannot_reach_it(tmp_path: Path) -> None:
    SEEN.clear()
    STALL.clear()
    STALLED.clear()
    clock = FakeClock()
    k = Keel(journal=MemoryJournal(clock=clock), tools=[write_file], programs=[editor], clock=clock,
             sandbox=LocalSandbox(tmp_path))
    handle = await k.start(editor, {"stall": True})

    # Epoch 1 writes a.py, then stalls inside b.py's attempt: STARTED, no outcome.
    lease = await k.journal.claim("w1", timedelta(seconds=TTL))
    zombie = asyncio.create_task(k.worker(worker_id="w1", lease_ttl=TTL).execute(lease))
    for _ in range(200):
        if len(SEEN) == 2:
            break
        await asyncio.sleep(0.005)
    epoch1 = tmp_path / str(handle.run_id) / "1"
    assert SEEN == [epoch1, epoch1]

    # The lease lapses, a successor takes the run in epoch 2 and finishes it — b.py re-run under the
    # same key (IDEMPOTENT), a.py rewritten v2 — without the stalled attempt ever returning.
    clock.advance(TTL + 2)
    await k.journal.reap()
    lease2 = await k.journal.claim("w2", timedelta(seconds=TTL))
    assert lease2 is not None and lease2.epoch == 2
    STALL.set()  # the zombie wakes now, with epoch 2 already holding the lease
    await k.worker(worker_id="w2", lease_ttl=TTL).execute(lease2)
    epoch2 = tmp_path / str(handle.run_id) / "2"
    assert fold(await k.events(handle.run_id)).phase == "COMPLETED"
    assert SEEN[2:] == [epoch2, epoch2], "the successor writes only in its own checkout"
    assert (epoch2 / "a.py").read_text() == "v2" and (epoch2 / "b.py").read_text() == "b"

    # The zombie's stalled write completes late — into epoch 1's directory. Its outcome is fenced.
    with contextlib.suppress(BaseException):
        await asyncio.wait_for(zombie, 5)
    assert (epoch1 / "b.py").read_text() == "b", "the zombie's write landed — in the dead directory"
    assert (epoch2 / "a.py").read_text() == "v2", "the reordering window is closed by construction"
    outcomes = [e for e in await k.events(handle.run_id) if e.type == "STEP_COMPLETED" and e.step_index == 1]
    assert [e.lease_epoch for e in outcomes] == [2], "and its outcome was fenced"
