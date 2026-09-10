"""The shim: the same three instants inside every runtime under test (§11.2).

    before:tool_call    nothing has been sent
    after:tool_effect   the World has durably receipted it; the framework has not seen the value
    after:tool_return   the framework has the value and is doing whatever it does with it

The second is the window this whole project is about, and it is bit-for-bit the same window for
Keel and for every framework it is compared against, because it is the same four lines of code.

Two mechanics decide what a cell measures, and both are here rather than in the adapters:

*`after:tool_return` cannot literally run after a function returns.* The kill is scheduled with
`loop.call_soon` immediately before returning, so it lands on the first scheduler turn after the
framework received the value — typically inside its checkpoint or outcome-commit write, which is
exactly why T3 is a real crash window and not a no-op for a checkpointing framework.

*A freeze must be uninterruptible, or it degrades into a timeout.* Keel wraps every non-PURE
dispatch in `asyncio.timeout`, so a `pause_past_ttl` followed by an `await` on an async client
would be cancelled the instant the loop ran again: the request would never leave the process and
the cell would measure a timeout instead of a zombie, while a thread-based runtime in the same cell
*would* send it. So the freeze and the request happen together on one worker thread, with a
blocking client, where the event loop's cancellation cannot reach either.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

from crashproof.faults.injectors.base import Injector
from crashproof.faults.triggers import landmark_of
from crashproof.world.client import WorldClient


class ToolShim(Injector):
    """Wraps the one World client. Every adapter hands its framework this and nothing else, which
    is what makes a Keel cell and a LangGraph cell the same experiment."""

    def __init__(self, *args: Any, world: WorldClient, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.world = world

    async def tool_call(
        self, name: str, endpoint: str, args: Mapping[str, Any], *, effect_key: str | None = None
    ) -> Any:
        """One instrumented tool call. May not return: that is the point of it."""
        landmark = landmark_of("tool", name)
        result = await asyncio.to_thread(self._send, landmark, endpoint, dict(args), effect_key)
        self._after_return(landmark)
        return result

    def _send(
        self, landmark: str, endpoint: str, args: dict[str, Any], effect_key: str | None
    ) -> Any:
        """Everything that must be uninterruptible, on one thread: the freeze, the request, and
        the boundary that fires once the World has the effect and we do not have the answer."""
        self.at(landmark, "before:tool_call")
        result = self.world.call(endpoint, args, effect_key=effect_key)
        self.at(landmark, "after:tool_effect")
        return result

    def _after_return(self, landmark: str) -> None:
        """Scheduled, not called: the framework has to receive the value first. `call_soon` puts
        the fault on the next scheduler turn, which is where a checkpointing runtime is writing."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - a synchronous framework
            self.at(landmark, "after:tool_return")
            return
        loop.call_soon(self.at, landmark, "after:tool_return")

    # --- model side ----------------------------------------------------------
    def model_call(self, node: str, complete: Callable[[], Any]) -> Any:
        """The scripted provider's decision node is the landmark, because it is a pure function of
        request content and therefore the same point in every runtime."""
        landmark = landmark_of("model", node)
        self.at(landmark, "before:model_call")
        response = complete()
        self.at(landmark, "after:model_return")
        return response
