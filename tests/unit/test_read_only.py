"""Read-only clients, each test run once sync and once async."""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import pytest

from frappex_client import (
    AsyncClient,
    Client,
    ConfigurationError,
    PasswordAuth,
    ReadOnlyError,
)

from .conftest import API_SECRET, URL, Site

WRITES: dict[str, Callable[[Any], Any]] = {
    "insert": lambda c: c.insert("ToDo", {"description": "x"}),
    "update": lambda c: c.update("ToDo", "T-1", {"status": "Closed"}),
    "delete": lambda c: c.delete("ToDo", "T-1"),
    "submit": lambda c: c.submit("Sales Invoice", "SINV-1"),
    "cancel": lambda c: c.cancel("Sales Invoice", "SINV-1"),
    "rename": lambda c: c.rename("ToDo", "T-1", "T-2"),
    "set_value": lambda c: c.set_value("ToDo", "T-1", {"status": "Closed"}),
    "insert_many": lambda c: c.insert_many("ToDo", [{"description": "x"}]),
    "bulk_update": lambda c: c.bulk_update("ToDo", {"T-1": {"status": "Closed"}}),
    "upload_file": lambda c: c.upload_file("a.txt", b"a"),
    "call by POST": lambda c: c.call("myapp.api.do_something", {"a": 1}),
}

PDF = {"Content-Type": "application/pdf"}


class TestReadOnly:
    @pytest.mark.parametrize("action", list(WRITES.values()), ids=list(WRITES))
    def test_every_write_is_refused_before_sending(
        self, site: Site, action: Callable[[Any], Any]
    ) -> None:
        site.reply(body={"data": {}, "message": {}})
        with pytest.raises(ReadOnlyError, match="read-only"):
            site.run(action, read_only=True)
        assert site.requests == []

    def test_bulk_writes_are_not_wrapped_in_bulk_operation_error(self, site: Site) -> None:
        with pytest.raises(ReadOnlyError) as caught:
            site.run(lambda c: c.insert_many("ToDo", [{}, {}]), read_only=True)
        assert type(caught.value) is ReadOnlyError

    def test_the_message_names_the_request_but_no_secret(self, site: Site) -> None:
        with pytest.raises(ReadOnlyError) as caught:
            site.run(lambda c: c.call("myapp.api.go", {"token": "zzz"}), read_only=True)
        text = str(caught.value)
        assert "POST /api/method/myapp.api.go" in text
        assert "zzz" not in text
        assert API_SECRET not in text

    def test_reads_work(self, site: Site) -> None:
        site.reply(body={"data": {"name": "T-1"}})
        assert site.run(lambda c: c.get_doc("ToDo", "T-1"), read_only=True) == {"name": "T-1"}

    def test_lists_counts_values_and_get_calls_work(self, site: Site) -> None:
        site.reply(body={"data": [{"name": "T-1"}], "message": 3})

        def reads(client: Any) -> Any:
            return (
                client.get_list("ToDo"),
                client.get_count("ToDo"),
                client.call("frappe.client.get_count", {"doctype": "ToDo"}, http_method="GET"),
            )

        def async_reads(client: Any) -> Any:
            async def run() -> Any:
                return (
                    await client.get_list("ToDo"),
                    await client.get_count("ToDo"),
                    await client.call(
                        "frappe.client.get_count", {"doctype": "ToDo"}, http_method="GET"
                    ),
                )

            return run()

        result = site.run(reads if site.kind == "sync" else async_reads, read_only=True)
        assert result == ([{"name": "T-1"}], 3, 3)
        assert {request.method for request in site.requests} == {"GET"}

    def test_reports_and_downloads_work(self, site: Site) -> None:
        site.reply(body={"message": {"columns": ["Name"], "result": [["A"]]}})
        report = site.run(lambda c: c.run_report("Counts"), read_only=True)
        assert report.rows == [{"name": "A"}]

    def test_pdf_and_file_downloads_work(self, site: Site) -> None:
        site.reply(content=b"%PDF-1.4", headers=PDF)
        site.reply(content=b"data")
        target = io.BytesIO()

        def downloads(client: Any) -> Any:
            return client.download_pdf("ToDo", "T-1"), client.download_to("/files/a.txt", target)

        def async_downloads(client: Any) -> Any:
            async def run() -> Any:
                return (
                    await client.download_pdf("ToDo", "T-1"),
                    await client.download_to("/files/a.txt", target),
                )

            return run()

        result = site.run(downloads if site.kind == "sync" else async_downloads, read_only=True)
        assert result == (b"%PDF-1.4", 4)
        assert target.getvalue() == b"data"

    def test_password_login_still_works(self, site: Site) -> None:
        site.reply(body={"message": "Logged In"})
        site.reply(body={"data": {"name": "T-1"}})
        site.reply(body={"message": "ok"})
        result = site.run(
            lambda c: c.get_doc("ToDo", "T-1"),
            auth=PasswordAuth("ann@example.com", "pw"),
            read_only=True,
        )
        assert result == {"name": "T-1"}
        assert [r.url.path for r in site.requests] == [
            "/api/method/login",
            "/api/resource/ToDo/T-1",
            "/api/method/logout",
        ]

    def test_writes_work_by_default(self, site: Site) -> None:
        site.reply(body={"data": {"name": "T-1"}})
        assert site.run(lambda c: c.insert("ToDo", {})) == {"name": "T-1"}


@pytest.mark.parametrize("kind", [Client, AsyncClient])
class TestReadOnlySetting:
    def test_is_reported_by_the_client(self, kind: Any) -> None:
        assert kind(URL, read_only=True).read_only is True
        assert kind(URL).read_only is False

    @pytest.mark.parametrize("value", [1, "yes", None])
    def test_must_be_a_boolean(self, kind: Any, value: Any) -> None:
        with pytest.raises(ConfigurationError, match="read_only"):
            kind(URL, read_only=value)
