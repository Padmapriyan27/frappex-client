"""Concurrency limits, measured by how many requests a fake site sees at once."""

from __future__ import annotations

import asyncio
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest

from frappex_client import AsyncClient, Client, ConfigurationError, RetryPolicy, ServerError

URL = "https://erp.example.com"


class InFlight:
    """Counts concurrent requests; each takes a little time to answer."""

    def __init__(self, delay: float = 0.02) -> None:
        self.delay = delay
        self.now = 0
        self.peak = 0
        self.total = 0
        self._lock = threading.Lock()

    def _enter(self) -> None:
        with self._lock:
            self.now += 1
            self.total += 1
            self.peak = max(self.peak, self.now)

    def _leave(self) -> None:
        with self._lock:
            self.now -= 1

    def sync_handler(self, request: httpx.Request) -> httpx.Response:
        self._enter()
        try:
            time.sleep(self.delay)
            return httpx.Response(200, json={"data": {"name": "T-1"}})
        finally:
            self._leave()

    async def async_handler(self, request: httpx.Request) -> httpx.Response:
        self._enter()
        try:
            await asyncio.sleep(self.delay)
            if request.url.path.startswith("/files/"):
                return httpx.Response(200, content=b"file")
            return httpx.Response(200, json={"data": {"name": "T-1"}})
        finally:
            self._leave()


def run_async(site: InFlight, requests: int, **options: Any) -> list[Any]:
    async def main() -> list[Any]:
        transport = httpx.MockTransport(site.async_handler)
        async with AsyncClient(URL, transport=transport, **options) as client:
            return list(
                await asyncio.gather(*(client.get_doc("ToDo", "T-1") for _ in range(requests)))
            )

    return asyncio.run(main())


class TestAsyncConcurrency:
    def test_defaults_to_ten_in_flight(self) -> None:
        site = InFlight()
        assert len(run_async(site, 40)) == 40
        assert site.peak == 10

    def test_limit_is_respected_and_every_request_completes(self) -> None:
        site = InFlight()
        assert len(run_async(site, 25, max_concurrency=3)) == 25
        assert site.peak == 3
        assert site.total == 25

    def test_none_removes_the_limit(self) -> None:
        site = InFlight()
        run_async(site, 30, max_concurrency=None)
        assert site.peak == 30

    def test_downloads_take_a_slot_too(self) -> None:
        site = InFlight()

        async def main() -> None:
            transport = httpx.MockTransport(site.async_handler)
            async with AsyncClient(URL, transport=transport, max_concurrency=2) as client:
                await asyncio.gather(
                    *(client.download_to("/files/a.txt", io.BytesIO()) for _ in range(8))
                )

        asyncio.run(main())
        assert site.peak == 2

    def test_a_slot_is_not_held_while_waiting_to_retry(self) -> None:
        calls: list[float] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(time.monotonic())
            if request.url.path.endswith("/slow"):
                return httpx.Response(503, json={})
            return httpx.Response(200, json={"data": {"name": "fast"}})

        async def main() -> float:
            transport = httpx.MockTransport(handler)
            retry = RetryPolicy(max_attempts=2, backoff_base=0.5, backoff_max=0.5)
            async with AsyncClient(
                URL, transport=transport, max_concurrency=1, retry=retry
            ) as client:
                slow = asyncio.create_task(client.get_doc("ToDo", "slow"))
                await asyncio.sleep(0.05)
                started = time.monotonic()
                await client.get_doc("ToDo", "fast")
                elapsed = time.monotonic() - started
                with pytest.raises(ServerError):
                    await slow
                return elapsed

        # The fast request ran during the slow one's back-off, not after it.
        assert asyncio.run(main()) < 0.3


class TestSyncConcurrency:
    def test_threads_share_the_limit(self) -> None:
        site = InFlight()
        transport = httpx.MockTransport(site.sync_handler)
        with (
            Client(URL, transport=transport, max_concurrency=4) as client,
            ThreadPoolExecutor(max_workers=16) as pool,
        ):
            results = list(pool.map(lambda _: client.get_doc("ToDo", "T-1"), range(32)))
        assert len(results) == 32
        assert site.peak == 4


@pytest.mark.parametrize("kind", [Client, AsyncClient])
class TestSetting:
    def test_is_reported(self, kind: Any) -> None:
        assert kind(URL).max_concurrency == 10
        assert kind(URL, max_concurrency=3).max_concurrency == 3
        assert kind(URL, max_concurrency=None).max_concurrency is None

    @pytest.mark.parametrize("value", [0, -1, True, 2.5, "4"])
    def test_must_be_a_positive_integer(self, kind: Any, value: Any) -> None:
        with pytest.raises(ConfigurationError, match="max_concurrency"):
            kind(URL, max_concurrency=value)

    def test_pool_matches_the_limit(self, kind: Any) -> None:
        client = kind(URL, max_concurrency=7)
        pool = client._http._transport._pool
        assert pool._max_connections == 7
        assert pool._max_keepalive_connections == 7
