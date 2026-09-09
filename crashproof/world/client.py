"""The one World client (§11.1).

Every SUT reaches the World through this module — in `shim` mode the adapter hands it to its
framework as a tool, and the shim's fault boundaries are the four lines of `call()`. There is one
client so that `before:tool_call`, `after:tool_effect` and `after:tool_return` are bit-for-bit the
same three instants for Keel and for every framework it is compared against.

It is **blocking**, on purpose. §11.2: a freeze must be uninterruptible or it degrades into a
timeout — a `pause_past_ttl` followed by an `await` on an async HTTP client would be cancelled the
instant the loop ran again and the request would never leave the process, so the cell would measure
a timeout instead of a zombie. `acall` therefore runs the same blocking call on a worker thread,
where the event loop's cancellation cannot reach it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from http.client import HTTPConnection
from typing import Any
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:8600"


class WorldClient:
    def __init__(self, base_url: str = DEFAULT_URL, *, timeout: float = 30.0) -> None:
        parts = urlsplit(base_url if "://" in base_url else f"http://{base_url}")
        self.host = parts.hostname or "127.0.0.1"
        self.port = parts.port or 80
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # --- the tool call -------------------------------------------------------
    def call(
        self, endpoint: str, args: Mapping[str, Any], *, effect_key: str | None = None
    ) -> dict[str, Any]:
        """POST one endpoint. `effect_key` travels as `Idempotency-Key` — F1. Omit it for F0, and
        the World applies the request unconditionally on a `dedup:false` endpoint."""
        headers = {"Idempotency-Key": effect_key} if effect_key else {}
        return self._request("POST", "/" + endpoint.replace(".", "/", 1), args, headers)

    async def acall(
        self, endpoint: str, args: Mapping[str, Any], *, effect_key: str | None = None
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self.call, endpoint, args, effect_key=effect_key)

    # --- the oracle ----------------------------------------------------------
    def probe(
        self,
        endpoint: str | None = None,
        args: Mapping[str, Any] | None = None,
        *,
        effect_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/oracle/probe",
            {"endpoint": endpoint, "args": dict(args or {}), "effect_key": effect_key},
        )

    async def aprobe(self, *a: Any, **kw: Any) -> dict[str, Any]:
        return await asyncio.to_thread(lambda: self.probe(*a, **kw))

    def applied(self) -> dict[str, int]:
        return self._request("GET", "/oracle/applied")

    def receipts(self) -> dict[str, int]:
        return self._request("GET", "/oracle/receipts")

    def state(self) -> dict[str, Any]:
        return self._request("GET", "/oracle/state")

    # Every blocking method has an `a`-prefixed twin. A caller on the loop that *hosts* the World
    # must use these: the server cannot answer a request made from the coroutine waiting on it.
    async def aapplied(self) -> dict[str, int]:
        return await asyncio.to_thread(self.applied)

    async def areceipts(self) -> dict[str, int]:
        return await asyncio.to_thread(self.receipts)

    async def astate(self) -> dict[str, Any]:
        return await asyncio.to_thread(self.state)

    # --- control -------------------------------------------------------------
    def hold(self, endpoint: str, ms: float) -> dict[str, Any]:
        return self._request("POST", "/control/hold", {"endpoint": endpoint, "ms": ms})

    def set_dedup(self, endpoint: str, *, dedup: bool | None = None, natural: bool | None = None) -> dict[str, Any]:
        return self._request(
            "POST", "/control/dedup", {"endpoint": endpoint, "dedup": dedup, "natural": natural}
        )

    def healthy(self) -> bool:
        try:
            return bool(self._request("GET", "/health").get("ok"))
        except OSError:
            return False

    # --- transport -----------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        conn = HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            payload = json.dumps(body).encode() if body is not None else None
            hdrs = {"Content-Type": "application/json", **(headers or {})}
            conn.request(method, path, body=payload, headers=hdrs)
            resp = conn.getresponse()
            raw = resp.read()
            data = json.loads(raw) if raw else None
            if resp.status >= 400:
                raise WorldError(f"{resp.status} {path}: {data}")
            return data
        finally:
            conn.close()


class WorldError(RuntimeError):
    pass
