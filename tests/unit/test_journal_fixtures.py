"""Every recorded run is a control-flow regression test (§10.9, §28.5).

`tests/journals/*.jsonl` are real journals, captured with `keel events $RUN --json`. This file
replays each of them against the *current* code with `MemoryJournal`, in-process: no database, no
provider key, no network, no World. It runs in milliseconds, and it fails the moment a program
change reorders a step that a real run once took.

That is the whole argument for keeping journals around. A production journal is a far better source
of control-flow cases than anything a test author would think to write, and capture costs one
redirect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from keel.agents import demo
from keel.effects.registry import ToolRegistry
from keel.replay.determinism import logical_projection_hash
from keel.replay.fixtures import Fixture, load_all, verify_fixture
from keel.state.fold import fold

JOURNALS = Path(__file__).resolve().parents[1] / "journals"
FIXTURES = load_all(JOURNALS)
PROGRAMS = {"tool_chain": demo.tool_chain}
#: The registry is the program's *present*, supplied here as code; the fixture is its past.
TOOLS = ToolRegistry([demo.search, demo.create_issue_tool("EXTERNAL")])


def test_there_are_fixtures_to_replay() -> None:
    """A fixture directory that quietly empties turns this whole file into a no-op that passes."""
    assert FIXTURES, f"no journal fixtures in {JOURNALS}"
    assert {f.name for f in FIXTURES} >= {"clean_tool_chain", "recovered_tool_chain"}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
async def test_every_recorded_journal_still_agrees_with_the_program(fixture: Fixture) -> None:
    result = await verify_fixture(fixture, PROGRAMS[fixture.program], tools=TOOLS)
    assert result.ok, f"{fixture.name}: {result.diff}"
    assert not result.drift, f"{fixture.name}: prompt drift {result.drift}"
    if fixture.terminal:
        assert result.projection_hash is not None


def test_a_crash_did_not_change_what_the_run_decided() -> None:
    """The two fixtures are the same program on the same inputs; one of them crashed inside the
    effect window and probed its way back. §10.5 says they are the same run, logically — and the
    hash is where that claim is either true or a comfortable story."""
    by_name = {f.name: f for f in FIXTURES}
    clean = fold(by_name["clean_tool_chain"].events)
    recovered = fold(by_name["recovered_tool_chain"].events)

    assert recovered.steps[3].state == "RESOLVED_COMPLETED", "the fixture stopped being a recovery"
    assert clean.steps[3].state == "COMPLETED"
    assert logical_projection_hash(clean) == logical_projection_hash(recovered)


async def test_a_reordered_program_fails_against_a_recorded_journal() -> None:
    """The failure this file exists to catch, on a journal captured before the change was made."""
    from typing import Any

    async def reordered(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        await ctx.tool("search", query="anything")
        return await demo.tool_chain(ctx, args)

    result = await verify_fixture(
        next(f for f in FIXTURES if f.name == "clean_tool_chain"), reordered, tools=TOOLS
    )
    assert not result.ok
    assert result.diff["step_index"] == 0
