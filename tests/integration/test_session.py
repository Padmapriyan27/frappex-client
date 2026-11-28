"""Password sessions against a real site."""

from __future__ import annotations

import asyncio

import pytest

from frappex_client import AsyncClient, Client, PasswordAuth

from .conftest import OPTIONS, PASSWORD, URL, USERNAME

pytestmark = pytest.mark.skipif(
    not (USERNAME and PASSWORD), reason="FRAPPEX_TEST_USERNAME/PASSWORD are not set"
)


def test_a_session_the_site_no_longer_knows_is_renewed(marker: str) -> None:
    with Client(URL, PasswordAuth(USERNAME, PASSWORD), **OPTIONS) as client:
        assert client.get_logged_user() == USERNAME
        # The site now sees a guest, exactly as after its session timeout.
        client._http.cookies.clear()
        assert client.get_logged_user() == USERNAME
        created = client.insert("ToDo", {"description": f"{marker} after renewal"})
        client._http.cookies.clear()
        assert client.get_doc("ToDo", created["name"])["description"] == f"{marker} after renewal"


def test_async_session_renewal(marker: str) -> None:
    async def scenario() -> list[str]:
        async with AsyncClient(URL, PasswordAuth(USERNAME, PASSWORD), **OPTIONS) as client:
            await client.get_logged_user()
            client._http.cookies.clear()
            return list(await asyncio.gather(*(client.get_logged_user() for _ in range(5))))

    assert asyncio.run(scenario()) == [USERNAME] * 5
