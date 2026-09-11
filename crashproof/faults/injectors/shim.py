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
import json
from collections.abc import Callable, Mapping
from typing import Any

from crashproof.faults.injectors.base import Injector
from crashproof.faults.schedule import Entry
from crashproof.faults.triggers import landmark_of
from crashproof.world.client import WorldClient

#: `tool_timeout` withholds one response indefinitely, so the SUT's own bound is what ends the
#: attempt — which is the thing the cell measures. One response, because the fault fired once: an
#: unbounded hold would time out every later attempt and measure a receiver that never came back.
HOLD_FOREVER_MS = -1


class ToolShim(Injector):
    """Wraps the one World client. Every adapter hands its framework this and nothing else, which
    is what makes a Keel cell and a LangGraph cell the same experiment."""

    def __init__(self, *args: Any, world: WorldClient, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.world = world
        self._endpoint: str | None = None

    def _execute(self, entry: Entry) -> None:
        """`tool_timeout` is armed at the receiver rather than simulated here: the request really
        is sent, the World really does receipt and apply it, and the response never comes. That is
        what makes the EXTERNAL answer AMBIGUOUS rather than FAILED — the effect landed, and the
        runtime has no way to know."""
        if entry.type == "tool_timeout" and self._endpoint:
            self.world.hold(self._endpoint, HOLD_FOREVER_MS, times=1)
            return
        super()._execute(entry)

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
        self._endpoint = endpoint
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
    @staticmethod
    def count_tokens(prompt: Any) -> int | None:
        """One token count, applied to every arm's outgoing prompt.

        Each framework assembles its own prompt, and how much it re-sends after a recovery is the
        thing `extra_tokens` is for — so the payload has to be the framework's. What must *not*
        differ is the counting, because measuring one runtime by its own self-report and another by
        the harness is how an economy metric becomes a statement about instrumentation (§14.3).
        Four characters to a token, on a canonical dump: crude, identical, and the same crudeness
        the scripted provider's own `count_tokens` uses, so Keel's budget and this column agree.
        """
        if prompt is None:
            return None
        return len(json.dumps(prompt, sort_keys=True, default=str)) // 4

    async def model_call(
        self, node: str, complete: Callable[[], Any], *, prompt: Any = None
    ) -> Any:
        """The scripted provider's decision node is the landmark, because it is a pure function of
        request content and therefore the same point in every runtime.

        On a thread, like the tool path, for one reason: a `model_timeout` is a blocking sleep, and
        a blocking sleep on the event loop would stop the runtime's own timeout from ever firing —
        the cell would measure a hang instead of a timeout.
        """
        return await asyncio.to_thread(
            self._ask, landmark_of("model", node), complete, self.count_tokens(prompt)
        )

    def _ask(self, landmark: str, complete: Callable[[], Any], tokens: int | None = None) -> Any:
        self.at(landmark, "before:model_call", tokens=tokens)
        response = complete()
        self.at(landmark, "after:model_return")
        return response
