"""Method calls, files, authentication and the async client against a real site."""

from __future__ import annotations

import asyncio
import io

import pytest

from frappix import (
    AsyncClient,
    AuthenticationError,
    Client,
    FrappixError,
    NotFoundError,
    PasswordAuth,
    PermissionDeniedError,
    ResponseTooLargeError,
    ServerError,
    TokenAuth,
)

from .conftest import KEY, OPTIONS, PASSWORD, URL, USERNAME, token_auth


class TestMethods:
    def test_get_with_arguments(self, client: Client, marker: str) -> None:
        client.insert("ToDo", {"description": f"{marker} call"})
        filters = {"description": ["like", f"%{marker}%"]}
        count = client.call(
            "frappe.client.get_count", {"doctype": "ToDo", "filters": filters}, http_method="GET"
        )
        assert count == 1

    def test_post_with_json_arguments(self, client: Client, marker: str) -> None:
        todo = client.insert("ToDo", {"description": f"{marker} post"})
        saved = client.call(
            "frappe.client.set_value",
            {"doctype": "ToDo", "name": todo["name"], "fieldname": "status", "value": "Closed"},
        )
        assert saved["status"] == "Closed"

    def test_unknown_method_raises(self, client: Client) -> None:
        with pytest.raises(FrappixError):
            client.call("frappix.no_such_module.no_such_method")


class TestFiles:
    def test_private_upload_and_download(self, client: Client, marker: str) -> None:
        todo = client.insert("ToDo", {"description": f"{marker} file"})
        payload = b"frappix payload \x00\xff" * 100
        uploaded = client.upload_file(
            f"{marker}.bin", payload, doctype="ToDo", docname=todo["name"]
        )
        try:
            assert uploaded["is_private"] == 1
            assert uploaded["file_url"].startswith("/private/files/")
            assert uploaded["attached_to_name"] == todo["name"]
            assert client.download(uploaded["file_url"]) == payload

            target = io.BytesIO()
            assert client.download_to(uploaded["file_url"], target) == len(payload)
            assert target.getvalue() == payload

            with pytest.raises(ResponseTooLargeError):
                client.download_to(uploaded["file_url"], io.BytesIO(), max_bytes=10)
        finally:
            client.delete("File", uploaded["name"])

    def test_public_upload_is_opt_in(self, client: Client, marker: str) -> None:
        uploaded = client.upload_file(f"{marker}.txt", b"public", is_private=False)
        try:
            assert uploaded["is_private"] == 0
            assert uploaded["file_url"].startswith("/files/")
            assert client.download(uploaded["file_url"]) == b"public"
        finally:
            client.delete("File", uploaded["name"])

    def test_missing_file_raises(self, client: Client) -> None:
        # A production site (nginx) answers 404. The development server
        # (`bench serve`) answers 500 for a missing static file.
        with pytest.raises((NotFoundError, ServerError)):
            client.download("/files/frappix-no-such-file.bin")


class TestAuthentication:
    def test_wrong_secret(self) -> None:
        with (
            Client(URL, TokenAuth(KEY, "wrong-secret"), **OPTIONS) as bad,
            pytest.raises(AuthenticationError) as caught,
        ):
            bad.get_logged_user()
        assert caught.value.status_code == 401
        assert "wrong-secret" not in str(caught.value)

    def test_private_file_needs_credentials(self, client: Client, marker: str) -> None:
        uploaded = client.upload_file(f"{marker}.txt", b"secret")
        try:
            with (
                Client(URL, TokenAuth(KEY, "wrong-secret"), **OPTIONS) as bad,
                pytest.raises(FrappixError),
            ):
                bad.download(uploaded["file_url"])
        finally:
            client.delete("File", uploaded["name"])

    def test_guest_reaches_only_what_the_site_opens(self, client: Client, marker: str) -> None:
        uploaded = client.upload_file(f"{marker}.txt", b"public", is_private=False)
        try:
            with Client(URL, **OPTIONS) as guest:
                assert guest.ping() == "pong"
                assert guest.get_logged_user() == "Guest"
                assert guest.download(uploaded["file_url"]) == b"public"
                with pytest.raises((PermissionDeniedError, AuthenticationError)):
                    guest.get_list("User")
                with pytest.raises((PermissionDeniedError, AuthenticationError)):
                    guest.insert("ToDo", {"description": f"{marker} guest"})
        finally:
            client.delete("File", uploaded["name"])

    @pytest.mark.skipif(
        not (USERNAME and PASSWORD), reason="FRAPPIX_TEST_USERNAME/PASSWORD are not set"
    )
    def test_password_session(self, marker: str) -> None:
        with Client(URL, PasswordAuth(USERNAME, PASSWORD), **OPTIONS) as session:
            assert session.get_logged_user() == USERNAME
            todo = session.insert("ToDo", {"description": f"{marker} session"})
            assert session.update("ToDo", todo["name"], {"status": "Closed"})["status"] == "Closed"
            session.delete("ToDo", todo["name"])

    @pytest.mark.skipif(
        not (USERNAME and PASSWORD), reason="FRAPPIX_TEST_USERNAME/PASSWORD are not set"
    )
    def test_wrong_password(self) -> None:
        with (
            Client(URL, PasswordAuth(USERNAME, "definitely-wrong"), **OPTIONS) as session,
            pytest.raises(AuthenticationError),
        ):
            session.get_logged_user()


class TestAsyncClient:
    def test_round_trip_pagination_files_and_errors(self, marker: str) -> None:
        async def scenario() -> None:
            async with AsyncClient(URL, token_auth(), **OPTIONS) as live:
                assert await live.ping() == "pong"
                names = set()
                for index in range(5):
                    created = await live.insert("ToDo", {"description": f"{marker} {index}"})
                    names.add(created["name"])

                filters = {"description": ["like", f"%{marker}%"]}
                seen = [
                    row["name"]
                    async for row in live.iter_list("ToDo", filters=filters, page_size=2)
                ]
                assert set(seen) == names
                assert len(seen) == 5
                assert await live.get_count("ToDo", filters) == 5

                first = seen[0]
                assert (await live.update("ToDo", first, {"status": "Closed"}))[
                    "status"
                ] == "Closed"

                uploaded = await live.upload_file(f"{marker}.txt", b"async payload")
                try:
                    assert await live.download(uploaded["file_url"]) == b"async payload"
                finally:
                    await live.delete("File", uploaded["name"])

                await live.delete("ToDo", first)
                with pytest.raises(NotFoundError):
                    await live.get_doc("ToDo", first)

        asyncio.run(scenario())

    def test_concurrent_requests_share_one_client(self, marker: str) -> None:
        async def scenario() -> None:
            async with AsyncClient(URL, token_auth(), **OPTIONS) as live:
                created = await asyncio.gather(
                    *(live.insert("ToDo", {"description": f"{marker} c{i}"}) for i in range(8))
                )
                fetched = await asyncio.gather(*(live.get_doc("ToDo", d["name"]) for d in created))
                assert [d["name"] for d in fetched] == [d["name"] for d in created]

        asyncio.run(scenario())
