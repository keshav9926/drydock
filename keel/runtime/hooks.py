"""Hook boundaries: the crash windows inside Keel's own write path (§11.2, §28.6).

The shim can only break a runtime where it touches the outside world — before a tool call, after an
effect lands, around a model call. That is the right boundary for *comparing* runtimes, because it
is the same instant in every one of them. It is the wrong boundary for proving that Keel's own
journal protocol is correct, because the interesting windows are all *inside* a single transaction:
between appending the intent and committing it, between the effect landing and the outcome being
written, between the last heartbeat and the lease lapsing.

Those windows cannot be reached from outside the process, so this module puts a named point at each
one and lets something in the same process decide what happens there. Two rules keep it honest:

**It is a no-op unless something installs a hook.** Production code pays one attribute lookup and a
function call that returns immediately. Nothing is imported, nothing is configured, and there is no
way for a hook to exist by accident.

**A hook may not return a value.** It can raise, sleep, or kill the process — those are faults. It
cannot *change* what the runtime does next, because a fault injector that alters control flow is no
longer measuring the runtime; it is measuring itself.

**Raising an ordinary `Exception` is not a crash.** The step engine catches `Exception` around the
effect and turns it into `Failed` — a tool's own error is an outcome, not a worker crash, and it
has no way to tell a hook's exception from a tool's. A hook that raises therefore produces a step
that *failed*, with the journal recording an outcome, which is the opposite of the window most of
these boundaries exist to open. To stop a worker where a power cut would stop it, a hook must
either end the process (`os._exit`) or raise a `BaseException`, which nothing in the runtime
catches. `Crash` below is that exception, so a caller does not have to know this to get it right.

The white-box results these produce are published in their own table and never unioned with the
cross-runtime matrix (§28.6). A boundary only Keel has is not a fair column.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: The ten boundaries whose mechanisms exist today. The remaining seven arrive with the mechanisms
#: they name — signals and approvals in week 2, segments and streams in week 3 — and are absent
#: rather than stubbed, so a spec naming one is refused instead of firing nothing (§28.6).
BOUNDARIES = (
    "before:intent_commit",
    "after:intent_commit",
    "before:attempt_commit",
    "after:attempt_commit",
    "before:effect_exec",
    "after:effect_exec",
    "before:outcome_commit",
    "after:outcome_commit",
    "before:lease_heartbeat",
    "before:lease_release",
)


class Crash(BaseException):
    """What a hook raises to stop a worker where a power cut would stop it.

    A `BaseException` on purpose: the step engine catches `Exception` around a tool call, because a
    tool that raises has produced an *outcome*, and it cannot tell a hook's exception from a real
    one. Deriving from `BaseException` puts a hook's crash outside that net, so the journal is left
    exactly as a real crash would leave it — with no outcome at all.
    """


Hook = Callable[[str, dict[str, Any]], None]


def _nothing(boundary: str, detail: dict[str, Any]) -> None:
    return None


#: Module-level rather than passed through every constructor, because the hook has to be reachable
#: from the journal transaction, the step engine and the worker loop, and threading an injector
#: through all three would put fault-injection plumbing in every signature in the runtime.
_hook: Hook = _nothing


def install(hook: Hook) -> Hook:
    """Install a hook and return the previous one. Called by the harness inside the SUT process,
    never by production code — `keel` ships with `_nothing` and no way to configure otherwise."""
    global _hook
    previous, _hook = _hook, hook
    return previous


def reset() -> None:
    install(_nothing)


def installed() -> bool:
    return _hook is not _nothing


def at(boundary: str, **detail: Any) -> None:
    """One boundary. Returns normally when nothing is installed, and may not return at all when
    something is — which is the entire point of it."""
    _hook(boundary, detail)
