"""Two workers, one run: exactly one appends.

Written before the worker loop, because a missing conjunct in the fence or the acquire predicate
produces a system that looks correct until day 3 and then fails `pause_past_ttl` in a way that is
indistinguishable from a real finding (§28.1).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from keel.core.clock import FakeClock
from keel.core.errors import Fenced
from keel.core.ids import new_run_id
from keel.core.versions import KEEL_VERSION
from keel.events import RunCreated, RunSuspended
from keel.journal.memory import MemoryJournal
from keel.journal.protocol import RunRow

TTL = timedelta(seconds=2)


async def _one_run(journal: MemoryJournal):
    rid = new_run_id()
    row = RunRow(
        run_id=rid,
        run_root_id=rid,
        program="p",
        program_version="1.0+abc",
        keel_version=KEEL_VERSION,
        phase="CREATED",
        trace_id=rid,
    )
    await journal.create_run(
        row, RunCreated(program="p", program_version="1.0+abc"), runnable_at=journal.clock.now()
    )
    return rid


async def test_second_claim_finds_nothing_while_the_lease_is_live() -> None:
    journal = MemoryJournal(clock=FakeClock())
    await _one_run(journal)
    first = await journal.claim("w1", TTL)
    assert first is not None
    assert await journal.claim("w2", TTL) is None


async def test_reaper_needs_the_lease_to_lapse_first() -> None:
    journal = MemoryJournal(clock=FakeClock())
    await _one_run(journal)
    await journal.claim("w1", TTL)
    assert await journal.reap() == []  # lease still live
    journal.clock.advance(3)
    assert len(await journal.reap()) == 1


async def test_fenced_worker_cannot_append_and_successor_can() -> None:
    journal = MemoryJournal(clock=FakeClock())
    run_id = await _one_run(journal)
    old = await journal.claim("w1", TTL)
    assert old is not None
    journal.clock.advance(3)
    await journal.reap()
    new = await journal.claim("w2", TTL)
    assert new is not None
    assert new.epoch == old.epoch + 1
    assert new.cause == "ORPHANED"

    with pytest.raises(Fenced):
        async with journal.append(old) as tx:
            await tx.append(RunSuspended(reason="from the zombie"))

    async with journal.append(new) as tx:
        seq = await tx.append(RunSuspended(reason="from the successor"))
    events = await journal.read(run_id)
    assert [e.type for e in events] == ["RUN_CREATED", "RUN_SUSPENDED"]
    assert events[-1].seq == seq
    assert events[-1].body.reason == "from the successor"


async def test_a_fenced_append_rewinds_the_seq_counter() -> None:
    journal = MemoryJournal(clock=FakeClock())
    await _one_run(journal)
    old = await journal.claim("w1", TTL)
    assert old is not None
    before = old.next_seq
    journal.clock.advance(3)
    await journal.reap()
    await journal.claim("w2", TTL)
    with pytest.raises(Fenced):
        async with journal.append(old) as tx:
            await tx.append(RunSuspended(reason="x"))
    assert old.next_seq == before


async def test_released_lease_cannot_be_resurrected_by_a_late_heartbeat() -> None:
    """(1) carries `AND lease_expires_at IS NOT NULL`: a NULL lease is one the scheduler may hand
    to anyone, so a heartbeat from the old epoch must not bring it back (§5.4)."""
    journal = MemoryJournal(clock=FakeClock())
    await _one_run(journal)
    lease = await journal.claim("w1", TTL)
    assert lease is not None
    await journal.release(lease, runnable_at=journal.clock.now())
    assert await journal.heartbeat(lease, TTL) is False


async def test_acquire_waits_for_the_attempt_deadline() -> None:
    """The reaper predicate is now() > max(lease_expires_at, attempt_deadline), and `acquire`
    carries it too — otherwise a successor could start before the zombie's request timed out."""
    journal = MemoryJournal(clock=FakeClock())
    run_id = await _one_run(journal)
    lease = await journal.claim("w1", TTL)
    assert lease is not None
    async with journal.append(lease) as tx:
        await tx.set_run(attempt_deadline=journal.clock.now() + timedelta(seconds=10))
    journal.clock.advance(3)  # lease lapsed, attempt still in flight
    assert await journal.reap() == []
    assert await journal.claim("w2", TTL) is None
    journal.clock.advance(10)
    assert await journal.reap() == [run_id]
    assert await journal.claim("w2", TTL) is not None
