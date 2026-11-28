"""Concurrent requests against a real site."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from frappex_client import AsyncClient, Client

from .conftest import OPTIONS, URL, token_auth


@pytest.mark.parametrize("limit", [5, None])
def test_parallel_async_reads(client: Client, marker: str, limit: int | None) -> None:
    names = client.insert_many("ToDo", [{"description": f"{marker} {i}"} for i in range(30)])

    async def scenario() -> list[str]:
        async with AsyncClient(URL, token_auth(), max_concurrency=limit, **OPTIONS) as live:
            docs = await asyncio.gather(*(live.get_doc("ToDo", name) for name in names))
            return [doc["name"] for doc in docs]

    assert asyncio.run(scenario()) == names


def test_threads_share_one_sync_client(client: Client, marker: str) -> None:
    names = client.insert_many("ToDo", [{"description": f"{marker} {i}"} for i in range(20)])
    with (
        Client(URL, token_auth(), max_concurrency=4, **OPTIONS) as shared,
        ThreadPoolExecutor(max_workers=8) as pool,
    ):
        docs = list(pool.map(lambda name: shared.get_doc("ToDo", name), names))
    assert [doc["name"] for doc in docs] == names
