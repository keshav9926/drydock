"""`keel events --follow`, and the `keel watch` cut (§25.2, §28.7).

§28.7 cuts the Rich TUI and names `keel events --follow` as what suffices. That is a substitute
rather than a consolation, and the reason is worth stating: what the TUI was for is the BEFORE
CRASH / AFTER RESTART split, and that split already lives in the event stream. RECOVERY_STARTED is
the line where a different process took over, and the `origin` column marks every step it replayed
rather than re-ran. A second rendering of the same projection would be one more thing to keep in
step with the first.

`--follow` was declared MVP in §25.2's command tree and was the one flag there that did not exist.
Two behaviours decide whether it is usable, and both are failures a reader would blame on the
runtime rather than on the CLI:

    it stops at a terminal event            or it polls forever for an append nobody will make
    it refuses to follow a finished run     same hang, reached before the first poll
"""

from __future__ import annotations

from typing import Any

import pytest

from keel.cli import main as cli


class _Body:
    """Whatever the renderer asks for. The subject here is the stopping rule, not the formatting —
    which `keel events` already renders and `tests/unit/test_journal_fixtures.py` already pins."""

    def __getattr__(self, name: str) -> Any:
        return ""


class _Event:
    def __init__(self, seq: int, kind: str, step: int | None = None) -> None:
        self.seq, self.type, self.step_index, self.lease_epoch = seq, kind, step, 1
        self.body = _Body()


class _Journal:
    """Yields a scripted stream and then blocks, exactly as the real tail's 1 s poll does. If
    `_follow` does not stop itself, this test hangs — which is the failure being caught."""

    def __init__(self, events: list[_Event]) -> None:
        self.events = events
        self.yielded: list[int] = []

    async def tail(self, run_id: Any, *, from_seq: int = 0):
        for e in self.events:
            if e.seq > from_seq:
                self.yielded.append(e.seq)
                yield e
        raise AssertionError("the follower read past the terminal event")


async def test_follow_stops_at_the_terminal_event() -> None:
    journal = _Journal([
        _Event(15, "RECOVERY_STARTED"),
        _Event(16, "STEP_AMBIGUOUS", 3),
        _Event(17, "STEP_RESOLVED", 3),
        _Event(18, "RUN_COMPLETED"),
    ])
    keel = type("K", (), {"journal": journal})()
    await cli._follow(keel, "run", from_seq=14)
    assert journal.yielded == [15, 16, 17, 18], "everything up to and including the terminal event"


async def test_follow_starts_after_the_events_already_printed() -> None:
    """`--from` and `--follow` compose: the tail resumes where the table stopped, so an event is
    never printed twice and never skipped between the read and the first poll."""
    journal = _Journal([_Event(16, "STEP_AMBIGUOUS", 3), _Event(17, "RUN_COMPLETED")])
    keel = type("K", (), {"journal": journal})()
    await cli._follow(keel, "run", from_seq=16)
    assert journal.yielded == [17]


def test_watch_is_cut_rather_than_stubbed() -> None:
    """§28.7's cut, asserted. A `watch` command that existed and printed a placeholder would be
    worse than one that does not exist: the command tree is the contract."""
    names = {c.name or c.callback.__name__ for c in cli.app.registered_commands}
    assert "watch" not in names
    assert "events" in names

    follow = next(
        p for p in cli.events.__annotations__.values() if "follow" in str(p)
    )
    assert follow is not None, "--follow is declared MVP in §25.2 and has to exist"


@pytest.mark.parametrize("phase", ["COMPLETED", "FAILED", "CANCELLED"])
def test_a_terminal_phase_is_the_set_the_follower_stops_on(phase: str) -> None:
    from keel.events.schema import TERMINAL_TYPES

    assert f"RUN_{phase}" in TERMINAL_TYPES
