"""A fake Frappe site that drives the sync and the async client alike."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from frappix import AsyncClient, Client, RetryPolicy, TokenAuth

URL = "https://erp.example.com"
API_SECRET = "s3cr3t-value-never-shown"


class Site:
    """Records requests and answers them from a queue of replies."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.requests: list[httpx.Request] = []
        self._replies: list[httpx.Response | Exception] = []

    def reply(
        self,
        status: int = 200,
        body: Any = None,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> None:
        if content is None:
            self._replies.append(httpx.Response(status, json=body, headers=headers))
        else:
            self._replies.append(httpx.Response(status, content=content, headers=headers))

    def fail(self, error: Exception) -> None:
        self._replies.append(error)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if not self._replies:
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def run(self, action: Callable[[Any], Any], **options: Any) -> Any:
        """Run ``action(client)`` and return its result, awaited or collected."""
        options.setdefault("auth", TokenAuth("key", API_SECRET))
        options.setdefault("retry", RetryPolicy(backoff_base=0))
        auth = options.pop("auth")
        transport = httpx.MockTransport(self._handle)

        if self.kind == "sync":
            with Client(URL, auth, transport=transport, **options) as client:
                result = action(client)
                return list(result) if inspect.isgenerator(result) else result

        async def main() -> Any:
            async with AsyncClient(URL, auth, transport=transport, **options) as client:
                result = action(client)
                if inspect.isasyncgen(result):
                    return [item async for item in result]
                return await result

        return asyncio.run(main())

    def body(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content)


@pytest.fixture(params=["sync", "async"])
def site(request: pytest.FixtureRequest) -> Site:
    return Site(request.param)
