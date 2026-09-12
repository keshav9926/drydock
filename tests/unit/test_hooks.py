"""Hook boundaries: the crash windows inside Keel's own write path (§11.2, §28.6).

The shim breaks a runtime where it touches the outside world, which is the right boundary for
*comparing* runtimes and the wrong one for proving Keel's journal protocol correct. The interesting
windows are inside a single transaction, and nothing outside the process can reach them.

What has to be true of a hook boundary, and is checked here:

    it is a no-op unless installed        production pays a call that returns
    it fires where its name says          the order is the protocol, written down
    it can end the process                or it is documentation, not a fault

The third is what makes the conformance table possible: `before:outcome_commit` names the window
where the effect has happened and the journal does not know, and a fault that fires there is the
only way to prove the recovery table handles it.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from crashproof.workloads.tool_chain_1_effect import build_world
from crashproof.world.server import WorldServer
from keel import Budget, Keel
from keel.agents import demo
from keel.core.clock import FakeClock
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider
from keel.runtime import hooks


@pytest.fixture(autouse=True)
def _no_hook_leaks():
    """A hook is process-global. One test forgetting to remove it would silently arm every test
    after it, so removal is the fixture's job rather than each test's."""
    hooks.reset()
    yield
    hooks.reset()


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    w = build_world()
    server = WorldServer(w, port=0)
    await server.start()
    monkeypatch.setattr(demo, "WORLD_URL", server.base_url)
    try:
        yield w
    finally:
        await server.stop()


def _keel(clock: FakeClock, variant: str = "EXTERNAL") -> Keel:
    return Keel(
        journal=MemoryJournal(clock=clock),
        provider=ScriptedProvider(demo.SCRIPT),
        tools=[demo.search, demo.create_issue_tool(variant)],
        programs=[demo.tool_chain],
        clock=clock,
    )


def test_nothing_is_installed_by_default() -> None:
    """Production imports this module and pays one call that returns. There is no configuration
    that turns hooks on, which is the point: a fault boundary cannot exist by accident."""
    assert not hooks.installed()
    hooks.at("before:outcome_commit", step_index=0)  # returns, does nothing


def test_install_returns_the_previous_hook_so_it_can_be_put_back() -> None:
    seen: list[str] = []
    previous = hooks.install(lambda b, d: seen.append(b))
    assert hooks.installed()
    hooks.at("before:intent_commit", step_index=0)
    hooks.install(previous)
    hooks.at("before:intent_commit", step_index=0)
    assert seen == ["before:intent_commit"], "the restored hook still fired"


async def test_the_boundaries_fire_in_the_order_the_protocol_declares(world) -> None:
    """The write-ahead protocol, read off a real run.

    Intent and the first attempt share one transaction, so their `after:` boundaries close
    together and no crash can land between them — the property the INTENDED/RUNNING split in the
    recovery table rests on. Then the effect runs, and only then is its outcome durable.
    """
    seen: list[tuple[str, Any]] = []
    hooks.install(lambda b, d: seen.append((b, d.get("step_index"))))

    clock = FakeClock()
    result = await _keel(clock).run(
        demo.tool_chain, {"task": "file an issue"}, budget=Budget(max_tokens=50_000)
    )
    assert result.phase == "COMPLETED"

    step0 = [b for b, i in seen if i == 0]
    assert step0 == [
        "before:intent_commit",
        "after:intent_commit",
        "after:attempt_commit",
        "before:effect_exec",
        "after:effect_exec",
        "before:outcome_commit",
        "after:outcome_commit",
    ]
    # Five steps in this workload, every one of them through the same sequence.
    assert len({i for _, i in seen if i is not None}) == 5
    assert not [b for b, _ in seen if b not in hooks.BOUNDARIES], "an undeclared boundary fired"


async def test_a_crash_before_the_outcome_commit_leaves_the_effect_done_and_unrecorded(world) -> None:
    """The window the whole recovery table exists for, reached from inside for the first time.

    `after:effect_exec` is the instant the World has the effect and the journal does not. A fault
    there is indistinguishable from a power cut, and what the journal holds afterwards — STARTED
    with no outcome — is the row the successor has to dispose of by effect class.

    It has to raise `hooks.Crash`, not an ordinary exception. The engine catches `Exception` around
    a tool call because a tool that raises has produced an outcome, and it cannot tell a hook's
    exception from a tool's — so an ordinary raise here records STEP_FAILED and closes the very
    window the boundary exists to open.
    """
    clock = FakeClock()
    k = _keel(clock)
    handle = await k.start(demo.tool_chain, {"task": "file an issue"})

    def crash_after_the_effect(boundary: str, detail: dict[str, Any]) -> None:
        if boundary == "after:effect_exec" and detail.get("step_index") == 3:
            raise hooks.Crash("power cut")

    hooks.install(crash_after_the_effect)
    from datetime import timedelta

    lease = await k.journal.claim("w1", timedelta(seconds=2))
    with contextlib.suppress(BaseException):
        await k.worker(worker_id="w1", lease_ttl=2.0).execute(lease)
    hooks.reset()

    # The World did the work; the journal never heard.
    assert world.applied_counts().get("issues.create#1") == 1
    from keel.state.fold import fold

    state = fold(await k.events(handle.run_id))
    assert state.steps[3].state == "RUNNING", "the journal must not claim an outcome it never got"
