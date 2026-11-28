"""Keyset paging in iter_list against a real site."""

from __future__ import annotations

import asyncio
from collections import Counter

from frappex_client import AsyncClient, Client

from .conftest import OPTIONS, URL, token_auth

ROWS = 250
TIED = 120


def like(marker: str) -> dict[str, list[str]]:
    return {"description": ["like", f"%{marker}%"]}


def make_tied_rows(client: Client, marker: str) -> list[str]:
    """Create rows, then give TIED of them one identical creation timestamp."""
    names = client.insert_many("ToDo", [{"description": f"{marker} {i:03d}"} for i in range(ROWS)])
    tie = client.get_value("ToDo", "creation", names[0])
    assert tie is not None
    failures = client.bulk_update(
        "ToDo", {name: {"creation": tie["creation"]} for name in names[:TIED]}
    )
    assert failures == []
    counts = Counter(
        row["creation"]
        for row in client.get_list("ToDo", fields=["creation"], filters=like(marker), limit=ROWS)
    )
    assert counts.most_common(1)[0][1] >= TIED, "the site did not store the tied timestamps"
    return names


def test_keyset_paging_returns_every_row_once_in_the_sites_order(
    client: Client, marker: str
) -> None:
    names = make_tied_rows(client, marker)
    # The site's own order for the same query, in one request.
    expected = [
        row["name"]
        for row in client.get_list(
            "ToDo", filters=like(marker), order_by="creation asc, name asc", limit=ROWS + 10
        )
    ]

    paged = [row["name"] for row in client.iter_list("ToDo", filters=like(marker), page_size=25)]

    assert len(paged) == len(set(paged)) == ROWS
    assert set(paged) == set(names)
    assert paged == expected


def test_fields_and_offset_fallback_match(client: Client, marker: str) -> None:
    make_tied_rows(client, marker)
    keyset = list(
        client.iter_list("ToDo", fields=["description"], filters=like(marker), page_size=30)
    )
    offset = list(
        client.iter_list(
            "ToDo",
            fields=["description"],
            filters=like(marker),
            order_by="creation asc, name asc",
            page_size=30,
        )
    )
    assert all(set(row) == {"description"} for row in keyset)
    assert sorted(r["description"] for r in keyset) == sorted(r["description"] for r in offset)
    assert len(keyset) == ROWS


def test_async_keyset_paging(client: Client, marker: str) -> None:
    make_tied_rows(client, marker)

    async def scenario() -> list[str]:
        async with AsyncClient(URL, token_auth(), **OPTIONS) as live:
            return [
                row["name"]
                async for row in live.iter_list("ToDo", filters=like(marker), page_size=40)
            ]

    names = asyncio.run(scenario())
    assert len(names) == len(set(names)) == ROWS
