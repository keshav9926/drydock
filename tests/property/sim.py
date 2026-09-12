"""The simulator the state machine drives (§12.3, §28.6).

The risk in a stateful property suite is that the sim drifts from the runtime and starts proving
things about itself. The mitigation is that there is almost no sim here: the journal is the real
`MemoryJournal`, the step engine, worker, retry policy and effect table are the real ones, the
program and its tools are `keel.agents.demo`, and the judge is the same `invariants.verify` the
benchmark calls. Three things are faked, and only three:

    the clock    `FakeClock`, so time travel is a method call rather than a sleep
    the World    the harness's own deterministic receiver, in-process on an ephemeral port
    the process  a crash is `hooks.Crash` at a named boundary, not a signal

Everything a rule does, a worker could have done. `restart` runs the reaper predicate and the real
conditional acquire; a crash leaves the journal exactly as a power cut would, because `hooks.Crash`
derives from `BaseException` and nothing in the runtime catches it.

One loop, owned here and not by pytest-asyncio, because the machine's rules are synchronous and
have to drive the same loop across an entire example — a worker that crashed in rule 3 and a
successor that recovers it in rule 7 are the same journal and the same World.

§12.3 lists rules this sim does not have, and they are absent for one reason worth writing down:
its workers do not park at boundaries. Parking needs a hook that blocks and later releases, and a
hook cannot await — in one process the worker owning the loop would block the releaser. So a fault
is delivered by *running to* a boundary and dying there rather than by parking at it, which costs
the rules that need two live workers interleaved (`zombie_resume` mid-effect, `duplicate_response`,
`drain`) and the ones whose mechanisms are week 2 (`deliver_signal`, `expire_approval`). The rest
of §12.3 — crash at a boundary, restart, tick, lease expiry, journal fault, timeout — is here.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from typing import Any

from crashproof.adapters.keel import KeelAdapter
from crashproof.verifier import invariants
from crashproof.workloads.tool_chain_1_effect import build_world, required_effects
from crashproof.world.server import WorldServer
from keel import Keel
from keel.agents import demo
from keel.core import aio
from keel.core.clock import FakeClock
from keel.core.errors import StoreUnavailable
from keel.journal.memory import MemoryJournal
from keel.providers.scripted import ScriptedProvider
from keel.replay.verify import verify as run_verify
from keel.runtime import hooks
from keel.state.fold import fold

TTL = 2.0
#: The steps of `tool_chain_1_effect`: model, search (PURE), model, create_issue, model. A fault
#: aimed past the end simply never fires, which the machine reports rather than asserting away.
STEPS = (0, 1, 2, 3, 4)


class Sim:
    """One run: one journal, one World, one loop, and however many workers the example asks for."""

    def __init__(self, variant: str = "EXTERNAL") -> None:
        self.variant = variant
        self.loop = aio.loop_factory()
        self.clock = FakeClock()
        self.world = build_world()
        self.server = WorldServer(self.world, port=0)
        self._previous_url = demo.WORLD_URL
        self.crashes = 0
        self.restarts = 0
        self.faults: list[dict[str, Any]] = []

        self.loop.run_until_complete(self.server.start())
        demo.WORLD_URL = self.server.base_url
        self.keel = Keel(
            journal=MemoryJournal(clock=self.clock),
            provider=ScriptedProvider(demo.SCRIPT),
            tools=[demo.search, demo.create_issue_tool(variant)],
            programs=[demo.tool_chain],
            clock=self.clock,
        )
        handle = self.loop.run_until_complete(
            self.keel.start(demo.tool_chain, {"task": "file an issue"})
        )
        self.run_id = handle.run_id
        self.worker_no = 0

    # --- what a rule does ----------------------------------------------------
    def work(self, *, boundary: str | None = None, fault: str = "crash", step: int | None = None) -> bool:
        """Take the lease and run, optionally dying at a named boundary. False if nobody could.

        The acquire is the real conditional update, so a run whose lease has not lapsed refuses the
        successor exactly as it would in Postgres — which is the point of asking the journal rather
        than tracking liveness here.
        """
        self.worker_no += 1
        worker_id = f"w{self.worker_no}"
        lease = self.loop.run_until_complete(
            self.keel.journal.acquire(self.run_id, worker_id, timedelta(seconds=TTL))
        )
        if lease is None:
            return False
        if self.worker_no > 1:
            self.restarts += 1
        landed: list[str] = []
        if boundary is not None:
            self._arm(boundary, fault, step, landed)
        try:
            with contextlib.suppress(BaseException):
                self.loop.run_until_complete(
                    self.keel.worker(worker_id=worker_id, lease_ttl=TTL).execute(lease)
                )
        finally:
            hooks.reset()
        if landed:
            self.crashes += 1
            self.faults.append(
                {"type": fault, "boundary": boundary, "landmark": landed[0], "executed": True}
            )
        return True

    def _arm(self, boundary: str, fault: str, step: int | None, landed: list[str]) -> None:
        spent: list[bool] = []

        def hook(seen: str, detail: dict[str, Any]) -> None:
            if spent or seen != boundary:
                return
            if step is not None and detail.get("step_index") not in (None, step):
                return
            spent.append(True)
            landed.append(f"step={detail.get('step_index', '-')}")
            if fault == "journal_error":
                raise StoreUnavailable(f"store unavailable at {seen}")
            raise hooks.Crash(f"power cut at {seen}")

        hooks.install(hook)

    def tick(self, seconds: float) -> None:
        self.clock.advance(seconds)

    def reap(self) -> list[Any]:
        """The real reaper predicate over the real rows. Nothing here decides who is dead."""
        return self.loop.run_until_complete(self.keel.journal.reap())

    def hold(self, ms: float) -> None:
        """Make the next call to the endpoint under test outlive the tool timeout, which is how a
        `tool_timeout` reaches an in-process worker: the client is blocking on purpose, so the wait
        is a real one and not a cancellation the loop can serve."""
        self.world.hold(self.endpoint, ms, times=1)

    @property
    def endpoint(self) -> str:
        return required_effects(self.variant)[0].split("#")[0]

    @property
    def identity(self) -> str:
        return required_effects(self.variant)[0]

    # --- what an invariant reads ---------------------------------------------
    def pending_steps(self) -> list[int]:
        """Steps this run has not settled yet — the only ones a fault can still be aimed at.

        A machine that draws a step index uniformly spends most of its budget aiming behind the
        run: a step that already completed will never reach a boundary again, so the rule fires
        nothing and the example explores a sequence of no-ops. Drawing from here instead means the
        randomness goes into *which* boundary and *what order*, which is what the machine is for.
        """
        settled = {
            index for index, row in self.state().steps.items()
            if row.state not in ("RUNNING", "INTENDED")
        }
        return [index for index in STEPS if index not in settled]

    def phase(self) -> str:
        return self.state().phase

    def state(self) -> Any:
        return fold(self.events())

    def events(self) -> list[Any]:
        return self.loop.run_until_complete(self.keel.events(self.run_id))

    def facts(self) -> invariants.TrialFacts:
        """The same shape the benchmark builds, judged by the same function. A property suite with
        its own private notion of correctness proves things about the property suite."""
        events = self.events()
        effects = self.loop.run_until_complete(self.keel.journal.effects(self.run_id))
        replay = self.loop.run_until_complete(
            run_verify(self.keel.journal, self.run_id, demo.tool_chain.fn, tools=self.keel.tools)
        )
        return invariants.TrialFacts(
            world_receipts=[
                {"endpoint": r.endpoint, "effect_key": r.effect_key,
                 "logical_identity": r.logical_identity, "ts": r.ts}
                for r in self.world.receipts
            ],
            world_applied=self.world.applied_counts(),
            sut_committed={
                e.external_ref for e in effects
                if e.status in ("COMMITTED", "RESOLVED_COMMITTED") and e.external_ref
            },
            journal=[
                {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(),
                 "step_index": e.step_index, "attempt_no": e.attempt_no,
                 "body": e.body.model_dump(mode="json")}
                for e in events
            ],
            status=fold(events).phase,
            required_effects=required_effects(self.variant),
            claims=KeelAdapter.claims,
            effect_class=self.variant,
            faults=self.faults,
            restarts=self.restarts,
            #: The machine may legitimately restart more often than a benchmark cell allows; L2 is
            #: a statement about a *cell's* bound, and the machine sets its own.
            max_recoveries=99,
            reached_terminal=fold(events).phase in ("COMPLETED", "FAILED", "CANCELLED"),
            replay=replay.as_dict(),
            sut_effects=[
                {"effect_key": e.effect_key, "step_index": e.step_index, "class": e.effect_class,
                 "status": e.status, "external_ref": e.external_ref, "resolution": e.resolution}
                for e in effects
            ],
        )

    def close(self) -> None:
        hooks.reset()
        demo.WORLD_URL = self._previous_url
        with contextlib.suppress(Exception):
            self.loop.run_until_complete(self.server.stop())
        with contextlib.suppress(Exception):
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        self.loop.close()
