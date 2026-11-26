"""Bulk insert and update against a real site."""

from __future__ import annotations

import asyncio

import pytest

from frappex_client import AsyncClient, BulkOperationError, Client, ValidationError

from .conftest import OPTIONS, URL, token_auth


def like(marker: str) -> dict[str, list[str]]:
    return {"description": ["like", f"%{marker}%"]}


def test_insert_many_in_batches(client: Client, marker: str) -> None:
    docs = [{"description": f"{marker} {index}"} for index in range(5)]
    names = client.insert_many("ToDo", docs, batch_size=2)

    assert len(names) == len(set(names)) == 5
    saved = {client.get_doc("ToDo", name)["description"] for name in names}
    assert saved == {doc["description"] for doc in docs}


def test_a_failed_batch_saves_nothing_from_that_batch(client: Client, marker: str) -> None:
    docs = [
        {"description": f"{marker} good"},
        {"description": f"{marker} first batch"},
        {"description": f"{marker} valid"},
        {"description": f"{marker} invalid", "status": "Not A Status"},
    ]
    with pytest.raises(BulkOperationError) as caught:
        client.insert_many("ToDo", docs, batch_size=2)

    error = caught.value
    assert len(error.completed) == 2
    assert error.failed_at == 2
    assert isinstance(error.error, ValidationError)
    # Frappe rolls the whole failing request back, so only batch one is saved.
    assert client.get_count("ToDo", like(marker)) == 2


def test_bulk_update_reports_the_documents_it_could_not_save(client: Client, marker: str) -> None:
    names = client.insert_many("ToDo", [{"description": f"{marker} {i}"} for i in range(3)])

    failures = client.bulk_update(
        "ToDo",
        {
            names[0]: {"status": "Closed"},
            names[1]: {"status": "Not A Status"},
            names[2]: {"priority": "High"},
        },
    )

    assert [failure.name for failure in failures] == [names[1]]
    assert "Not A Status" in failures[0].message
    assert client.get_value("ToDo", "status", names[0]) == {"status": "Closed"}
    assert client.get_value("ToDo", "status", names[1]) == {"status": "Open"}
    assert client.get_value("ToDo", "priority", names[2]) == {"priority": "High"}


def test_async_bulk_insert_and_update(marker: str) -> None:
    async def scenario() -> None:
        async with AsyncClient(URL, token_auth(), **OPTIONS) as live:
            names = await live.insert_many(
                "ToDo", [{"description": f"{marker} {i}"} for i in range(3)], batch_size=2
            )
            assert len(names) == 3
            failures = await live.bulk_update(
                "ToDo", {name: {"status": "Closed"} for name in names}, batch_size=2
            )
            assert failures == []
            closed = await live.get_count("ToDo", {**like(marker), "status": "Closed"})
            assert closed == 3

    asyncio.run(scenario())
