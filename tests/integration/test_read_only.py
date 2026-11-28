"""Read-only clients against a real site."""

from __future__ import annotations

import asyncio

import pytest

from frappex_client import AsyncClient, Client, ReadOnlyError

from .conftest import OPTIONS, URL, token_auth


def like(marker: str) -> dict[str, list[str]]:
    return {"description": ["like", f"%{marker}%"]}


def test_reads_work_and_writes_never_reach_the_site(client: Client, marker: str) -> None:
    name = client.insert("ToDo", {"description": f"{marker} existing"})["name"]

    with Client(URL, token_auth(), read_only=True, **OPTIONS) as reader:
        assert reader.get_doc("ToDo", name)["description"] == f"{marker} existing"
        assert reader.get_count("ToDo", like(marker)) == 1
        assert [row["name"] for row in reader.iter_list("ToDo", filters=like(marker))] == [name]
        assert reader.call("frappe.auth.get_logged_user", http_method="GET")
        assert reader.download_pdf("ToDo", name).startswith(b"%PDF-")

        with pytest.raises(ReadOnlyError):
            reader.insert("ToDo", {"description": f"{marker} new"})
        with pytest.raises(ReadOnlyError):
            reader.insert_many("ToDo", [{"description": f"{marker} bulk"}])
        with pytest.raises(ReadOnlyError):
            reader.set_value("ToDo", name, {"status": "Closed"})
        with pytest.raises(ReadOnlyError):
            reader.delete("ToDo", name)

    # Checked with the ordinary client: nothing was created, changed or deleted.
    assert client.get_count("ToDo", like(marker)) == 1
    assert client.get_value("ToDo", "status", name) == {"status": "Open"}


def test_async_read_only(marker: str, client: Client) -> None:
    client.insert("ToDo", {"description": f"{marker} async"})

    async def scenario() -> None:
        async with AsyncClient(URL, token_auth(), read_only=True, **OPTIONS) as reader:
            assert await reader.get_count("ToDo", like(marker)) == 1
            with pytest.raises(ReadOnlyError):
                await reader.update("ToDo", "anything", {"status": "Closed"})

    asyncio.run(scenario())
    assert client.get_count("ToDo", like(marker)) == 1
