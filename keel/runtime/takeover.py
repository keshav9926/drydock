"""Lease takeover: the forced path, and the only one (§7.6.2, §17.7).

A child that ignores a `cancel` — busy, wedged, or never claimed at all — is not appended to from
outside; nothing is. Its lease is *taken*. The fifth control-plane statement moves the epoch, the
old worker is fenced by its next append, and the new writer closes the run in the new epoch, in
this order:

    RECOVERY_STARTED{cause=ORPHANED, forced_by}   a takeover is an acquisition: the first-append rule holds
    STEP_CANCELLED{step_index, attempt_no}        the open step, if any — its effect may still fire under
                                                  a zombie, which is what S6 reports
    CANCEL_ACKNOWLEDGED{step_index}               the replay anchor, exactly as for a cooperative cancel
    RUN_CANCELLED{reason=parent_cancel, forced_by}
    + child_result → the parent's inbox            in the same transaction, like every child's terminal event

Depth-first (§17.7): a child's own children are asked, and forced in their turn, *before* the child
is taken over, so RUN_CANCELLED of a child always follows its descendants' terminal events (S8).
Until they are all terminal the answer is `refused`, and the caller asks again after the grace.

No RECOVERY_COMPLETED is appended, because no step goes live; the `recoveries` row says
FORCED_CANCEL. Two callers: the parent's worker, on waking after `cancel_grace`, and the reaper,
for a stray whose parent is already terminal. Both go through the store's predicate, which refuses
until the child has had `cancel_grace` to acknowledge on its own and until any open non-PURE
attempt's deadline has passed — so the grace is judged by one clock, the store's.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from keel.core.errors import Fenced
from keel.core.ids import RunId
from keel.events import CancelAcknowledged, RecoveryStarted, RunCancelled, StepCancelled
from keel.runtime.delegation import cancel_signal, child_result_signal, usage_of
from keel.state.fold import fold

#: §7.6.2: `max(open step timeout, 5 s)`. A DELEGATE step has no tool timeout of its own, and the
#: children's tools are bounded by their own attempt deadlines — which the takeover predicate
#: honours separately — so the floor is the value.
DEFAULT_CANCEL_GRACE_S = 5.0


async def force_cancel(
    journal: Any,
    child_run_id: RunId,
    *,
    worker_id: str,
    ttl_s: float,
    forced_by: str,
    cancel_grace_s: float,
) -> str:
    """Take the child's lease and cancel it. `refused` when the store's predicate says not yet, or
    the child's own children are not all terminal yet — the caller re-parks and asks again after
    the grace; `terminal` when the child got there on its own between the caller's read and the
    takeover; `cancelled` when this epoch closed it; `lost_race` when another taker fenced this one
    between its takeover and its close (two reapers on one stray)."""
    open_grandchildren = [c for c in await journal.children(child_run_id) if c.terminal_at is None]
    if open_grandchildren:
        for g in open_grandchildren:
            # Told first, keyed so every tick and every taker produce one row; forced in their turn.
            await journal.insert_signal(
                cancel_signal(g.run_id, client_key=f"cancel:forced:{child_run_id}", by=forced_by, reason="parent_cancel")
            )
            await force_cancel(
                journal, g.run_id, worker_id=worker_id, ttl_s=ttl_s, forced_by=forced_by,
                cancel_grace_s=cancel_grace_s,
            )
        if any(c.terminal_at is None for c in await journal.children(child_run_id)):
            return "refused"
    lease = await journal.takeover(
        child_run_id,
        worker_id,
        timedelta(seconds=ttl_s),
        cancel_grace=timedelta(seconds=cancel_grace_s),
    )
    if lease is None:
        return "refused"
    state = fold(await journal.read(child_run_id))
    row = await journal.run_row(child_run_id)
    if state.terminal:
        await journal.release(lease, phase=state.phase)
        await journal.set_recovery(child_run_id, lease.epoch, outcome="TERMINAL")
        return "terminal"
    open_step = state.open_step
    at = open_step.step_index if open_step is not None else state.next_step_index
    try:
        return await _close(journal, lease, child_run_id, state, row, open_step, at, forced_by)
    except Fenced:
        await journal.set_recovery(child_run_id, lease.epoch, outcome="FENCED")
        return "lost_race"


async def _close(
    journal: Any, lease: Any, child_run_id: RunId, state: Any, row: Any, open_step: Any, at: int, forced_by: str
) -> str:
    async with journal.append(lease) as tx:
        started = await tx.append(
            RecoveryStarted(
                lease_epoch=lease.epoch,
                cause="ORPHANED",
                from_seq=lease.next_seq - 1,
                forced_by=forced_by,
            )
        )
        if open_step is not None:
            await tx.append(
                StepCancelled(
                    step_index=open_step.step_index,
                    attempt_no=open_step.attempts or None,
                    forced_by=forced_by,
                ),
                causation_seq=started,
            )
        ack = await tx.append(CancelAcknowledged(step_index=at), causation_seq=started)
        await tx.append(RunCancelled(reason="parent_cancel", forced_by=forced_by), causation_seq=ack)
        await tx.set_run(phase="CANCELLED", wake_at=None)
        if row is not None and row.parent_run_id is not None:
            await tx.insert_signal(
                child_result_signal(
                    row.parent_run_id,
                    child_run_id,
                    status="cancelled",
                    error="ChildCancelled",
                    usage=usage_of(state),
                )
            )
    await journal.set_recovery(child_run_id, lease.epoch, started_seq=started, outcome="FORCED_CANCEL")
    await journal.release(lease, phase="CANCELLED")
    return "cancelled"
