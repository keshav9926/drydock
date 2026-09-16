"""The proxy: the black-box injector, at the network edge (§11.2, §27.7).

The SUT is pointed at this instead of the World. Every tool request crosses it twice — on the way
in and on the way out — and those crossings are the shim's three boundaries seen one process
further out, with the precision §11.2's correspondence table says is lost:

    before:tool_call    request received, not yet forwarded       (it has already left the SUT)
    after:tool_effect   the World has answered; nothing written back to the SUT's socket
    after:tool_return   the response bytes are flushed             (before the SUT parses them)

What it can do to a request is what a network can do to one: not forward it, forward it and never
answer, answer late, answer 5xx, answer garbage, or close the socket. What it cannot do is anything
inside the SUT — and that is the point. A proxy cell needs no shim in the SUT at all, so it is the
mode for a runtime that cannot take a library provider, and for real-model mode later. The shim
still rides along in the SUT, observe-only, so model calls are counted at the wire as in every
other mode; it can never fire.

It runs on the harness's event loop beside the World — the receipt handler and the killer are two
lines in one coroutine, as §11.1 requires — and forwards with the blocking World client on a
thread, so a held or slow World never stalls the loop the two servers share. Everything that is
not a tool call (`/oracle/*`, `/control/*`, `/health`) passes through untouched: the SUT's own
probe reaches the World through the same URL it was given.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping
from typing import Any

from crashproof.faults.injectors.proxy import ProxyInjector
from crashproof.faults.triggers import landmark_of
from crashproof.world.client import WorldClient
from crashproof.world.server import read_request, response_bytes

_PASSTHROUGH = ("/oracle", "/control", "/health")
#: The garbage `tool_malformed` answers with: a 200 whose body is not the JSON its header
#: promises. A client that parses leniently and journals it as a result has produced a phantom
#: completion (S3); a client that treats it as unknown has done the right thing (§11.5).
_NOT_JSON = b"<html>502 upstream said something</html>"


class Proxy:
    def __init__(
        self,
        world_url: str,
        injector: ProxyInjector,
        *,
        tool_names: Mapping[str, str],
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.world = WorldClient(world_url, timeout=3600.0)  # the SUT's timeout ends a hold, never ours
        self.injector = injector
        #: endpoint id → workload tool name, so a proxy spec speaks `tool:create_issue` exactly
        #: as a shim spec does (§11.3); an endpoint the workload did not declare is addressed
        #: as `endpoint:<service>.<op>`, the proxy-only landmark.
        self.tool_names = dict(tool_names)
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._closing = asyncio.Event()
        injector.closing = self._closing  # a parked freeze is released by the same stop

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._closing.set()  # release any never-answered request before waiting on its handler
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # --- one request ---------------------------------------------------------
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await self._serve(reader, writer)
        except (ConnectionError, BrokenPipeError, asyncio.IncompleteReadError):
            pass  # the SUT was killed mid-request, or gave up: expected in this line of work
        except Exception as exc:  # noqa: BLE001 - the proxy answers, it never dies
            with contextlib.suppress(ConnectionError, BrokenPipeError):
                writer.write(response_bytes(502, {"error": f"proxy: {type(exc).__name__}: {exc}"}))
                await writer.drain()
        finally:
            writer.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await read_request(reader)
        if request is None:
            return
        method, path, body, key = request
        if method != "POST" or path.startswith(_PASSTHROUGH):
            status, payload = await self._forward(method, path, body, key)
            await self._reply(writer, status, payload)
            return

        endpoint = path.lstrip("/").replace("/", ".", 1)
        name = self.tool_names.get(endpoint)
        landmark = landmark_of("tool", name) if name else f"endpoint:{endpoint}"

        # before:tool_call — received, not forwarded. A kill here kills the sender of a request
        # nothing else has seen; a 500 here is a refusal before any effect.
        never_answer = False
        entry = self.injector.arm(landmark, "before:tool_call")
        if entry is not None:
            action = await self.injector.apply(entry)
            if action in ("killed", "dropped"):
                return
            if action == "500":
                await self._reply(writer, 500, {"error": "tool_500", "applied": False})
                return
            never_answer = action == "timeout"  # forward — the World applies — then say nothing

        status, payload = await self._forward(method, path, body, key)
        # ---- the World has applied and receipted it; the SUT has not heard ----
        entry = self.injector.arm(landmark, "after:tool_effect")
        action = await self.injector.apply(entry) if entry is not None else "continue"
        if action in ("killed", "dropped"):
            return  # the socket closes with nothing written: the SUT's client raises
        if action == "timeout" or never_answer:
            await self._hold(reader)
            return
        if action == "500":
            status, payload = 500, {"error": "tool_500", "applied": True}
        await self._reply(writer, status, payload, raw=_NOT_JSON if action == "malformed" else None)

        # after:tool_return — flushed. The kill lands before the SUT parses the bytes, which is
        # the precision this mode loses against the shim's `call_soon`; the table says so.
        entry = self.injector.arm(landmark, "after:tool_return")
        if entry is not None:
            await self.injector.apply(entry)

    async def _forward(
        self, method: str, path: str, body: dict[str, Any], key: str | None
    ) -> tuple[int, Any]:
        headers = {"Idempotency-Key": key} if key else {}
        return await asyncio.to_thread(
            self.world.request_raw, method, path, body if method == "POST" else None, headers
        )

    @staticmethod
    async def _reply(
        writer: asyncio.StreamWriter, status: int, payload: Any, *, raw: bytes | None = None
    ) -> None:
        writer.write(response_bytes(status, payload, raw=raw))
        await writer.drain()

    async def _hold(self, reader: asyncio.StreamReader) -> None:
        """Never answer. The handler ends when the SUT gives up and closes its side — its own
        timeout is what ends the attempt, which is the thing a `tool_timeout` cell measures — or
        when the proxy stops, so a held request cannot outlive its trial."""
        gone = asyncio.ensure_future(reader.read(1))
        closing = asyncio.ensure_future(self._closing.wait())
        try:
            await asyncio.wait({gone, closing}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (gone, closing):
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
