"""Journal fixtures: every recorded run becomes a control-flow regression test (§10.9, §28.5).

    keel events $RUN --json > tests/journals/<name>.jsonl

is the whole capture step — no new CLI flags, because §10.9's `keel events --export` and
`keel replay --journal` are undeclared in §25.2 and flagged for deletion there. What that file
holds is a list of event envelopes and bodies; what this module does is load it back into a
`MemoryJournal` and run VERIFY against the current code, in-process.

The result is a test that runs in milliseconds, needs no database, no provider key and no network,
and fails the moment a program change reorders a step that some real run once took. A recorded
production journal is a far better source of control-flow cases than anything a test author would
think to write, and this is what makes keeping one cost nothing.

The fixture is *data*, deliberately: it is the run's past, and the past does not get to be re-run.
Nothing here writes, and the `MemoryJournal` it builds is discarded with the test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keel.events import Event
from keel.journal.memory import MemoryJournal, memory_run_row
from keel.replay.verify import VerifyResult, verify
from keel.state.fold import fold


@dataclass(slots=True)
class Fixture:
    """One recorded journal, ready to replay."""

    name: str
    events: list[Event]
    run_id: Any
    program: str
    phase: str

    @property
    def terminal(self) -> bool:
        return self.phase in ("COMPLETED", "FAILED", "CANCELLED")


def load(path: Path | str) -> Fixture:
    """Read a `keel events --json` dump back into events."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf8"))
    events = [Event.model_validate(e) for e in raw]
    if not events:
        raise ValueError(f"{path}: a fixture with no events proves nothing")
    state = fold(events)
    return Fixture(
        name=path.stem,
        events=events,
        run_id=events[0].run_id,
        program=state.program,
        phase=state.phase,
    )


def load_all(directory: Path | str) -> list[Fixture]:
    """Every `*.jsonl` under `directory`, sorted, so a CI run is stable and its failures nameable."""
    return [load(p) for p in sorted(Path(directory).glob("*.jsonl"))]


def journal_for(fixture: Fixture) -> MemoryJournal:
    """A read-only-by-use `MemoryJournal` holding exactly this fixture's past.

    Built by assignment rather than by replaying appends: an append path would need a lease, and a
    lease would make loading a fixture a *write*, which is the one thing a recorded past must never
    become.
    """
    journal = MemoryJournal()
    run_id = fixture.run_id
    state = fold(fixture.events)
    journal._events[run_id] = list(fixture.events)
    row = memory_run_row(
        run_id=run_id,
        program=state.program,
        program_version=state.program_version,
        keel_version="",
        args=state.args,
        budget=state.budget,
        model_config={},
    )
    row.phase = state.phase
    journal._runs[run_id] = row
    return journal


async def verify_fixture(fixture: Fixture, program: Any, *, tools: Any) -> VerifyResult:
    """VERIFY this fixture against the current code.

    `tools` is required, not optional. VERIFY executes no tool, but it cannot build a TOOL step's
    *intent* without the registry — the effect class and modifiers travel on it — so a fixture
    replayed without tools raises `UnknownTool` at the first one. The registry is code, not data:
    the fixture is the run's past, and the tools are the program's present.

    No `requested_by`, so no `replays` row: an in-process CI pass over a throwaway journal has
    nowhere durable to write and nothing to gain from pretending otherwise.
    """
    return await verify(journal_for(fixture), fixture.run_id, program, tools=tools)
