"""The Sandbox, minus git: a per-epoch workspace checkout for LOCAL_FS tools (§20.5, §9.3).

MVP's LOCAL_FS window was at-least-once-with-*reordering*: a worker paused past its lease resumes
and its stale write lands in the run's one directory *after* the successor's newer write to the same
file. v1 closes it by construction — every lease epoch writes into its own directory:

    <root>/<run_id>/<lease_epoch>/

created on the epoch's first LOCAL_FS dispatch as a copy of the newest earlier epoch's directory.
A zombie of epoch e holds `tctx.workspace = .../e/` for its whole life, so whatever it writes after a
successor has checked out `e+1` lands in the dead directory. The copy is to a temporary name and then
renamed, so a checkout torn by a crash is never the directory the next epoch copies from.

What the copy carries forward is the dead epoch's directory as it stood — including a write of the
open attempt the successor is about to re-run. That is why LOCAL_FS stays PURE or
IDEMPOTENT-by-content (full content, atomic temp + replace; `ToolSpec` refuses the rest): the re-run
converges on the same bytes. The part of §20.5 that makes EXTERNAL + LOCAL_FS exact — `snapshot()`
on the outcome commit, `restore()` to the last COMPLETED step's snapshot at acquisition, the
`artifacts` row, the tree-hash probe — is git, and git is **cut**: first in §29.2's cut order,
"Sandbox git snapshot (keep the per-epoch checkout)". `exec` is not built either: nothing here runs a
subprocess yet, and the protocol grows the method with its first caller.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4


class LocalSandbox:
    """`workspace/<run_id>/<lease_epoch>/` on the worker's own disk. No isolation beyond the
    directory, documented as such (§20.5's table)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def checkout(self, run_id: Any, epoch: int) -> Path:
        here = self.root / str(run_id) / str(epoch)
        if here.is_dir():
            return here
        run_dir = here.parent
        run_dir.mkdir(parents=True, exist_ok=True)
        earlier = [int(p.name) for p in run_dir.iterdir() if p.is_dir() and p.name.isdigit() and int(p.name) < epoch]
        tmp = run_dir / f".{epoch}.{uuid4().hex}"
        if earlier:
            shutil.copytree(run_dir / str(max(earlier)), tmp, copy_function=_copy_unless_gone)
        else:
            tmp.mkdir()
        tmp.rename(here)
        return here


def _copy_unless_gone(src: str, dst: str) -> None:
    """The directory being copied may still have a zombie writing into it — that is the case this
    module exists for. A file it renames or removes mid-copy belongs to the zombie's open attempt,
    which the successor re-runs anyway; skipping it is right, failing the checkout would not be."""
    try:
        shutil.copy2(src, dst)
    except FileNotFoundError:
        pass
