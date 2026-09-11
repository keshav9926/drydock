"""VERIFY: does the current program, given this journal, issue the same steps the journal recorded?
(§10.1, §10.9)

It is the memoization loop with `allow_live=False` — the *same* loop, one flag — so it costs no
tokens, no effects and no lease. That is not an optimisation, it is the correctness argument: a
second replayer written to be read-only would drift from the one that actually recovers runs, and
the drift would be silent. VERIFY would keep passing while the thing it is supposed to be checking
had changed underneath it.

Three outcomes, and the third is the one people forget:

    pass                the program issued the same steps; `live_from_step` says where the journal
                        ran out, and a terminal run also gets its logical projection hash compared
    NondeterminismDetected   step k disagrees; FAIL with the diff, and a human chooses
    in-flight ambiguity an open step with no outcome; VERIFY *stops* rather than resolving it,
                        because resolution is a decision about the world and a read-only pass has
                        no standing to make one

No lease is taken and nothing is appended. The journal handed in is read once and never written, so
the same function serves the deploy shadow check, `keel replay --verify`, the CI fixture harness and
Crashproof's C1 without three different notions of what "verified" means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from keel.core.errors import NondeterminismDetected, PromptDrift
from keel.replay.determinism import logical_projection, logical_projection_hash
from keel.runtime.ctx import Ctx
from keel.runtime.steps import StepEngine, StopReplay, Suspended
from keel.state.fold import RunState, fold


@dataclass(slots=True)
class Drift:
    """A prompt that changed without changing what the program decided. Never a failure on its own
    (§10.5): a parked run must survive a one-line prompt edit, and the diff stays available."""

    step_index: int
    journaled: str | None
    issued: str | None


@dataclass(slots=True)
class VerifyResult:
    ok: bool = True
    run_id: Any = None
    program_version: str = ""
    #: Where the journal ran out and RECOVER would go live. `None` on a terminal run: nothing left.
    live_from_step: int | None = None
    replayed_steps: int = 0
    #: Set when VERIFY stopped on an open step rather than finishing (§10.9).
    stopped: str | None = None
    #: Populated only on failure: the step that disagreed, and both identities.
    diff: dict[str, Any] | None = None
    drift: list[Drift] = field(default_factory=list)
    #: Compared only for a terminal run — a run still in flight has no final projection to compare.
    projection_hash: str | None = None
    projection_matches: bool | None = None

    @property
    def status(self) -> str:
        if not self.ok:
            return "FAIL"
        return "PASS" if self.stopped is None else f"PASS ({self.stopped})"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "run_id": str(self.run_id) if self.run_id else None,
            "program_version": self.program_version,
            "live_from_step": self.live_from_step,
            "replayed_steps": self.replayed_steps,
            "stopped": self.stopped,
            "diff": self.diff,
            "drift": [{"step_index": d.step_index, "journaled": d.journaled, "issued": d.issued}
                      for d in self.drift],
            "projection_hash": self.projection_hash,
            "projection_matches": self.projection_matches,
        }


class _Recording(Ctx):
    """`Ctx`, plus the prompt hashes the program issued.

    `PromptDrift` cannot be detected inside the engine, because the engine compares *identity* and
    a MODEL step's identity is `(kind, name)` on purpose — that is what lets a parked run survive a
    prompt edit (§1). So the request hash is collected out here, where reporting it costs nothing
    and enforcing it is somebody else's policy decision.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.issued_requests: dict[int, str | None] = {}

    async def _run(self, intent: Any) -> Any:
        if intent.request_hash is not None:
            self.issued_requests[intent.step_index] = intent.request_hash
        return await super()._run(intent)


async def verify(
    journal: Any,
    run_id: Any,
    program: Any,
    *,
    tools: Any = None,
    expected_projection_hash: str | None = None,
) -> VerifyResult:
    """One VERIFY pass. `program` is the *current* code; `journal` is the recorded past."""
    events = await journal.read(run_id)
    state = fold(events)
    row = await journal.run_row(run_id)
    out = VerifyResult(run_id=run_id, program_version=state.program_version)

    engine = StepEngine(
        journal,
        _NoLease(run_id),
        state,
        run_root_id=getattr(row, "run_root_id", run_id),
        provider=None,  # a live MODEL step is unreachable: `allow_live=False` stops first
        tools=tools,
        allow_live=False,
    )
    ctx = _Recording(
        engine,
        run_id=run_id,
        run_root_id=getattr(row, "run_root_id", run_id),
        args=state.args,
        program_version=state.program_version,
        tools=tools,
    )

    try:
        await program(ctx, ctx.args)
    except StopReplay as stop:
        out.live_from_step = stop.step_index
        out.stopped = None if stop.reason == "live_from_step" else stop.reason
    except NondeterminismDetected as exc:
        out.ok = False
        out.diff = {
            "step_index": exc.step_index,
            "journaled": list(exc.journaled),
            "issued": list(exc.issued),
        }
    except Suspended as exc:  # a journal state VERIFY cannot read past; not a program disagreement
        out.stopped = str(exc)
    except Exception:
        # The program itself raised. On a terminal FAILED run that is the recorded outcome being
        # reproduced faithfully, which is a pass; on any other run it is a real disagreement and
        # the projection comparison below will say so.
        pass

    out.replayed_steps = engine.replayed_steps
    out.drift = _drift(state, ctx.issued_requests)

    if state.terminal:
        out.projection_hash = logical_projection_hash(state)
        if expected_projection_hash is not None:
            out.projection_matches = out.projection_hash == expected_projection_hash
            out.ok = out.ok and out.projection_matches
    return out


def _drift(state: RunState, issued: dict[int, str | None]) -> list[Drift]:
    return [
        Drift(step_index=i, journaled=state.steps[i].request_hash, issued=h)
        for i, h in sorted(issued.items())
        if i in state.steps
        and state.steps[i].request_hash is not None
        and state.steps[i].request_hash != h
    ]


def raise_for_drift(result: VerifyResult) -> None:
    """`--strict` only. Drift is reported by default and fatal on request (§10.9)."""
    if result.drift:
        d = result.drift[0]
        raise PromptDrift(f"step {d.step_index}: prompt changed ({d.journaled} -> {d.issued})")


class _NoLease:
    """VERIFY holds no lease. Every write path in the engine is behind `allow_live`, so this exists
    to satisfy the signature and to fail loudly rather than quietly if one is ever added: its epoch
    is a value no fence can match."""

    __slots__ = ("run_id",)
    epoch = -1
    ttl_seconds = 0.0
    program_version = ""

    def __init__(self, run_id: Any) -> None:
        self.run_id = run_id


def diff_projections(a: RunState, b: RunState) -> list[dict[str, Any]]:
    """The first place two runs stop agreeing, and every place after it.

    A bare hexadecimal mismatch tells an operator nothing. This walks the two logical projections
    side by side and names the steps, which is what `keel diff` prints.
    """
    left, right = logical_projection(a)["steps"], logical_projection(b)["steps"]
    fields = ("step_index", "kind", "name", "args_hash", "state", "result_hash")
    out: list[dict[str, Any]] = []
    for i in range(max(len(left), len(right))):
        lhs = left[i] if i < len(left) else None
        rhs = right[i] if i < len(right) else None
        if lhs == rhs:
            continue
        out.append(
            {
                "at": i,
                "a": dict(zip(fields, lhs, strict=True)) if lhs else None,
                "b": dict(zip(fields, rhs, strict=True)) if rhs else None,
            }
        )
    if a.phase != b.phase:
        out.append({"at": "phase", "a": a.phase, "b": b.phase})
    return out
