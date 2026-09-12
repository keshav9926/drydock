"""The hook injector: faults inside the runtime's own write path (§11.2, §28.6).

The shim fires where a runtime touches the outside world, which is the same instant in every
framework and therefore the only fair place to compare them. This fires *inside* Keel — between
appending an intent and committing it, between an effect landing and its outcome being written —
and no other arm has those points, so everything it produces goes in a separate table and is never
unioned with a cross-runtime row. A boundary only one runtime has is not a column.

What it adds beyond the shim is two faults the outside cannot reach:

    journal_unavailable   the store stops answering mid-run — the database a durable runtime is
                          durable *into*. A runtime that loses its journal must lose the run
                          safely, not finish it from memory.
    blob_write_fail       a large payload fails to externalise while the event that references it
                          is being written. The event must not commit pointing at a blob that
                          does not exist.

Both are `hook` mode. Both are Keel-only by construction, and saying so is the point rather than
an embarrassment: the reason no other arm can run them is that no other arm exposes the boundary.
"""

from __future__ import annotations

from typing import Any

from crashproof.faults.injectors.base import Injector
from crashproof.faults.schedule import Entry
from crashproof.faults.triggers import landmark_of

#: Faults only this injector can fire. `kill`, `pause_past_ttl` and the delays are inherited from
#: the base, because "stop the process here" means the same thing at any boundary.
HOOK_FAULT_TYPES = frozenset({"journal_unavailable", "blob_write_fail"})


def _store_unavailable(message: str) -> Exception:
    """Raise what a *backend* would raise, not something of the harness's own.

    An outage reaches the runtime as `StoreUnavailable` because that is what Keel's backends wrap
    their driver errors in — so this fault exercises the real path rather than a parallel one the
    harness invented. Imported lazily: the injector is loaded in the supervisor process too, and
    merely naming a fault should not drag Keel into the harness.
    """
    from keel.core.errors import StoreUnavailable

    return StoreUnavailable(message)


class HookInjector(Injector):
    """Installed into `keel.runtime.hooks` inside the SUT process.

    The landmark is the step's own `kind:name` — the same vocabulary the shim uses — so a hook spec
    reads `tool:create_issue` rather than "step 3 of this runtime's traffic". A step *index* is an
    ordinal in one framework's traffic and §11.3 forbids addressing one; the index travels in the
    detail for a spec that legitimately wants a single occurrence, but it is never the landmark.
    """

    def install(self) -> None:
        from keel.runtime import hooks

        hooks.install(self._at)

    def _at(self, boundary: str, detail: dict[str, Any]) -> None:
        kind, name = detail.get("kind"), detail.get("name")
        # The lease boundaries belong to the worker, not to a step, so they have no kind or name.
        landmark = landmark_of(kind, name) if kind and name else "lease:*"
        self.at(landmark, boundary)

    def _execute(self, entry: Entry) -> None:
        if entry.type == "journal_unavailable":
            # Raised rather than "the connection is closed underneath it", because the failure has
            # to happen at a *named instant*. Closing a pool would fail at whatever statement came
            # next, which is a different window on every run and reproduces nothing.
            raise _store_unavailable(f"store unavailable at {entry.boundary}")
        if entry.type == "blob_write_fail":
            raise _store_unavailable(f"blob store write failed at {entry.boundary}")
        super()._execute(entry)
