"""The World's HTTP surface — one asyncio server, no framework (§11.1).

It runs on the harness's own event loop because of aiming: the cell "kill 0 ms after the World
receives `create_issue` and before it responds" needs the receipt handler and the killer to be two
lines in one coroutine, with no IPC hop between them. `hold(endpoint, ms)` is the other half of
that pair — it parks the response so the kill lands inside the window.

The protocol surface is small enough to speak directly: fixed JSON bodies, `Content-Length`
always, `Connection: close` always. A dependency to parse forty lines of HTTP would be its own
joke, and an in-loop server is a requirement, not a preference.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from crashproof.world import oracle
from crashproof.world.services import UnknownEndpoint, World

_MAX_BODY = 1 << 20
_NEVER = 3600.0  # `hold(..., -1)` = never answer; the caller's timeout is what ends it


class WorldServer:
    def __init__(self, world: World, *, host: str = "127.0.0.1", port: int = 8600) -> None:
        self.world = world
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]  # 0 => an ephemeral port, for tests
        return self.port

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # --- one request ---------------------------------------------------------
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await self._read_request(reader)
            if request is None:
                return
            method, path, body, key = request
            status, payload = await self._dispatch(method, path, body, key)
        except Exception as exc:  # noqa: BLE001 - the World answers, it never dies
            status, payload = 500, {"error": f"{type(exc).__name__}: {exc}"}
        try:
            writer.write(_response(status, payload))
            await writer.drain()
        except (ConnectionError, BrokenPipeError):  # the SUT was killed mid-answer: expected
            pass
        finally:
            writer.close()

    @staticmethod
    async def _read_request(
        reader: asyncio.StreamReader,
    ) -> tuple[str, str, dict[str, Any], str | None] | None:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()
        length = min(int(headers.get("content-length", 0)), _MAX_BODY)
        raw = await reader.readexactly(length) if length else b""
        body = json.loads(raw) if raw else {}
        # The key travels in a header, never in the body: it is not an argument, it never feeds
        # `canonical_args`, and a workload must be free to use any field name it likes.
        return method, path, body, headers.get("idempotency-key")

    async def _dispatch(
        self, method: str, path: str, body: dict[str, Any], effect_key: str | None = None
    ) -> tuple[int, Any]:
        world = self.world
        if path == "/health":
            return 200, {"ok": True, "endpoints": sorted(world.endpoints)}
        if path == "/oracle/applied":
            return 200, oracle.applied(world)
        if path == "/oracle/receipts":
            return 200, oracle.receipts(world)
        if path == "/oracle/state":
            return 200, oracle.state(world)
        if path == "/oracle/probe":
            return 200, oracle.probe(
                world,
                endpoint=body.get("endpoint"),
                effect_key=body.get("effect_key"),
                args=body.get("args"),
            )
        if path == "/control/hold":
            world.hold(body["endpoint"], float(body["ms"]), body.get("times"))
            return 200, {"held": body["endpoint"], "ms": body["ms"]}
        if path == "/control/dedup":
            ep = world.set_dedup(body["endpoint"], dedup=body.get("dedup"), natural=body.get("natural"))
            return 200, {"endpoint": ep.id, "dedup": ep.dedup, "natural": ep.natural}
        if method != "POST":
            return 405, {"error": f"{method} {path}"}

        endpoint_id = path.lstrip("/").replace("/", ".", 1)
        try:
            result = self.world.receive(endpoint_id, body, effect_key=effect_key)
        except UnknownEndpoint:
            return 404, {"error": f"no endpoint {endpoint_id}"}
        # ---- the effect has been applied and durably receipted; the caller has not heard ----
        held = world.hold_ms(endpoint_id)
        if held:
            await asyncio.sleep(_NEVER if held < 0 else held / 1000.0)
        return 200, result


def _response(status: int, payload: Any) -> bytes:
    body = json.dumps(payload, default=str).encode()
    reason = {200: "OK", 404: "Not Found", 405: "Method Not Allowed", 500: "Server Error"}[status]
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode() + body
