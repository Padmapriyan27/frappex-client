"""Behaviour of both clients, each test run once sync and once async."""

from __future__ import annotations

import io
import logging
import ssl
from typing import Any

import httpx
import pytest

from frappix import (
    AsyncClient,
    Client,
    ConfigurationError,
    NotFoundError,
    PasswordAuth,
    PermissionDeniedError,
    RateLimitError,
    RequestTimeoutError,
    ResponseTooLargeError,
    RetryPolicy,
    ServerError,
    TokenAuth,
    TransportError,
    UnexpectedResponseError,
)

from .conftest import API_SECRET, URL, Site


def raw_path(request: httpx.Request) -> str:
    return request.url.raw_path.decode()


class TestRequests:
    def test_credentials_and_user_agent_are_sent(self, site: Site) -> None:
        site.reply(body={"message": "a@example.com"})
        assert site.run(lambda c: c.get_logged_user()) == "a@example.com"
        request = site.requests[0]
        assert request.headers["authorization"] == f"token key:{API_SECRET}"
        assert request.headers["user-agent"].startswith("frappix/")
        assert raw_path(request) == "/api/method/frappe.auth.get_logged_user"

    def test_get_doc_encodes_the_name_into_one_segment(self, site: Site) -> None:
        site.reply(body={"data": {"name": "SINV/1"}})
        assert site.run(lambda c: c.get_doc("Sales Invoice", "SINV/1 x")) == {"name": "SINV/1"}
        assert raw_path(site.requests[0]) == "/api/resource/Sales%20Invoice/SINV%2F1%20x"

    def test_dot_names_send_nothing(self, site: Site) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.delete("ToDo", ".."))
        assert site.requests == []

    def test_get_list_parameters(self, site: Site) -> None:
        site.reply(body={"data": [{"name": "a"}]})
        rows = site.run(
            lambda c: c.get_list(
                "ToDo",
                fields=["name", "status"],
                filters={"status": "Open"},
                order_by="modified desc",
                limit=5,
                offset=10,
            )
        )
        assert rows == [{"name": "a"}]
        params = site.requests[0].url.params
        assert params["fields"] == '["name","status"]'
        assert params["filters"] == '{"status":"Open"}'
        assert params["order_by"] == "modified desc"
        assert (params["limit_page_length"], params["limit_start"]) == ("5", "10")

    def test_fields_given_as_a_string_is_refused(self, site: Site) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.get_list("ToDo", fields="name"))

    def test_iter_list_walks_every_page_in_stable_order(self, site: Site) -> None:
        site.reply(body={"data": [{"name": "1"}, {"name": "2"}]})
        site.reply(body={"data": [{"name": "3"}, {"name": "4"}]})
        site.reply(body={"data": [{"name": "5"}]})
        rows = site.run(lambda c: c.iter_list("ToDo", page_size=2))
        assert [row["name"] for row in rows] == ["1", "2", "3", "4", "5"]
        assert [r.url.params["limit_start"] for r in site.requests] == ["0", "2", "4"]
        assert site.requests[0].url.params["order_by"] == "creation asc, name asc"

    def test_insert_update_delete(self, site: Site) -> None:
        site.reply(body={"data": {"name": "T1", "description": "x"}})
        assert site.run(lambda c: c.insert("ToDo", {"description": "x"}))["name"] == "T1"
        assert (site.requests[-1].method, site.body()) == ("POST", {"description": "x"})

        site.run(lambda c: c.update("ToDo", "T1", {"status": "Closed"}))
        assert (site.requests[-1].method, site.body()) == ("PUT", {"status": "Closed"})
        assert raw_path(site.requests[-1]) == "/api/resource/ToDo/T1"

        assert site.run(lambda c: c.delete("ToDo", "T1")) is None
        assert site.requests[-1].method == "DELETE"

    def test_submit_cancel_rename(self, site: Site) -> None:
        site.reply(body={"message": "NEW"})
        site.run(lambda c: c.submit("Sales Invoice", "S1"))
        assert site.body() == {"run_method": "submit"}
        assert raw_path(site.requests[-1]) == "/api/resource/Sales%20Invoice/S1"

        site.run(lambda c: c.cancel("Sales Invoice", "S1"))
        assert site.body() == {"doctype": "Sales Invoice", "name": "S1"}

        assert site.run(lambda c: c.rename("ToDo", "OLD", "NEW")) == "NEW"
        assert site.body()["merge"] is False

    def test_count_and_values(self, site: Site) -> None:
        site.reply(body={"message": 7})
        assert site.run(lambda c: c.get_count("ToDo", {"status": "Open"})) == 7

        other = Site(site.kind)
        other.reply(body={"message": {"status": "Open"}})
        assert other.run(lambda c: c.get_value("ToDo", "status", "T1")) == {"status": "Open"}
        assert other.requests[0].url.params["filters"] == "T1"

        empty = Site(site.kind)
        empty.reply(body={"message": {}})
        assert empty.run(lambda c: c.get_value("ToDo", "status", {"name": "nope"})) is None

        missing = Site(site.kind)
        missing.reply(body={})
        assert missing.run(lambda c: c.get_value("ToDo", ["status"], {"name": "nope"})) is None

    def test_call_post_sends_json_and_get_sends_query(self, site: Site) -> None:
        site.reply(body={"message": {"ok": True}})
        assert site.run(lambda c: c.call("app.api.run", {"ids": [1, 2]})) == {"ok": True}
        assert (site.requests[-1].method, site.body()) == ("POST", {"ids": [1, 2]})

        site.run(lambda c: c.call("app.api.read", {"ids": [1, 2], "q": "x"}, http_method="GET"))
        params = site.requests[-1].url.params
        assert (site.requests[-1].method, params["ids"], params["q"]) == ("GET", "[1,2]", "x")

    def test_call_rejects_a_path_as_method_name(self, site: Site) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.call("../resource/User"))
        assert site.requests == []

    def test_upload_is_private_by_default(self, site: Site) -> None:
        site.reply(body={"message": {"name": "F1", "file_url": "/private/files/a.txt"}})
        doc = site.run(lambda c: c.upload_file("a.txt", b"hello", doctype="ToDo", docname="T1"))
        assert doc["name"] == "F1"
        request = site.requests[0]
        assert request.headers["content-type"].startswith("multipart/form-data")
        body = request.content
        assert b'name="is_private"\r\n\r\n1' in body
        assert b'filename="a.txt"' in body
        assert b"hello" in body

    def test_upload_filename_cannot_contain_directories(self, site: Site) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.upload_file("../../etc/passwd", b"x"))


class TestGuestAccess:
    def test_no_credentials_are_sent(self, site: Site) -> None:
        site.reply(body={"message": "pong"})
        assert site.run(lambda c: c.ping(), auth=None) == "pong"
        request = site.requests[0]
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers

    def test_protected_data_maps_to_permission_error(self, site: Site) -> None:
        site.reply(403, {"exc_type": "PermissionError"})
        with pytest.raises(PermissionDeniedError):
            site.run(lambda c: c.get_list("User"), auth=None)
        assert [r.url.path for r in site.requests] == ["/api/resource/User"]

    def test_guest_can_call_a_method_and_fetch_a_public_file(self, site: Site) -> None:
        site.reply(body={"message": {"open": True}})
        assert site.run(lambda c: c.call("app.api.public_info"), auth=None) == {"open": True}

        files = Site(site.kind)
        files.reply(content=b"logo")
        assert files.run(lambda c: c.download("/files/logo.png"), auth=None) == b"logo"
        assert "authorization" not in files.requests[0].headers


class TestDownloads:
    def test_download_returns_bytes(self, site: Site) -> None:
        site.reply(content=b"PDFDATA")
        assert site.run(lambda c: c.download("/private/files/a b.pdf")) == b"PDFDATA"
        assert raw_path(site.requests[0]) == "/private/files/a%20b.pdf"

    def test_download_refuses_other_hosts(self, site: Site) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.download("https://evil.example/steal"))
        assert site.requests == []

    def test_download_error_maps_to_exception(self, site: Site) -> None:
        site.reply(403, content=b"<html>no</html>")
        with pytest.raises(PermissionDeniedError):
            site.run(lambda c: c.download("/private/files/a.pdf"))

    def test_download_to_honours_max_bytes(self, site: Site) -> None:
        site.reply(content=b"x" * 5000)
        with pytest.raises(ResponseTooLargeError):
            site.run(lambda c: c.download_to("/files/a.bin", io.BytesIO(), max_bytes=100))

    def test_download_to_writes_and_counts(self, site: Site) -> None:
        site.reply(content=b"abc")
        target = io.BytesIO()
        assert site.run(lambda c: c.download_to("/files/a.bin", target)) == 3
        assert target.getvalue() == b"abc"


class TestFailures:
    def test_not_found(self, site: Site) -> None:
        site.reply(404, {"exc_type": "DoesNotExistError"})
        with pytest.raises(NotFoundError) as caught:
            site.run(lambda c: c.get_doc("ToDo", "nope"))
        assert caught.value.exc_type == "DoesNotExistError"

    def test_redirect_is_not_followed(self, site: Site) -> None:
        site.reply(302, headers={"Location": "https://evil.example/api"}, content=b"")
        with pytest.raises(UnexpectedResponseError):
            site.run(lambda c: c.get_doc("ToDo", "T1"))
        assert len(site.requests) == 1
        assert site.requests[0].url.host == "erp.example.com"

    def test_oversized_reply_is_refused_and_not_retried(self, site: Site) -> None:
        site.reply(content=b'{"data": "' + b"x" * 500 + b'"}')
        with pytest.raises(ResponseTooLargeError):
            site.run(lambda c: c.get_doc("ToDo", "T1"), max_response_bytes=64)
        assert len(site.requests) == 1


class TestRetries:
    def test_read_is_retried_after_gateway_error(self, site: Site) -> None:
        site.reply(503, {})
        site.reply(body={"data": {"name": "T1"}})
        assert site.run(lambda c: c.get_doc("ToDo", "T1")) == {"name": "T1"}
        assert len(site.requests) == 2

    def test_write_is_never_retried_after_gateway_error(self, site: Site) -> None:
        site.reply(503, {})
        with pytest.raises(ServerError):
            site.run(lambda c: c.insert("ToDo", {"description": "x"}))
        assert len(site.requests) == 1

    def test_read_is_retried_after_connection_failure(self, site: Site) -> None:
        site.fail(httpx.ConnectError("boom"))
        site.reply(body={"data": {"name": "T1"}})
        assert site.run(lambda c: c.get_doc("ToDo", "T1")) == {"name": "T1"}

    def test_write_is_never_retried_after_connection_failure(self, site: Site) -> None:
        site.fail(httpx.ReadError("boom"))
        with pytest.raises(TransportError):
            site.run(lambda c: c.insert("ToDo", {"description": "x"}))
        assert len(site.requests) == 1

    def test_timeout_has_its_own_exception(self, site: Site) -> None:
        site.fail(httpx.ReadTimeout("slow"))
        with pytest.raises(RequestTimeoutError):
            site.run(lambda c: c.get_doc("ToDo", "T1"), retry=RetryPolicy(max_attempts=1))

    def test_rate_limited_write_is_retried(self, site: Site) -> None:
        site.reply(429, {}, headers={"Retry-After": "0"})
        site.reply(body={"data": {"name": "T1"}})
        assert site.run(lambda c: c.insert("ToDo", {"description": "x"}))["name"] == "T1"
        assert len(site.requests) == 2

    def test_long_rate_limit_raises_instead_of_blocking(self, site: Site) -> None:
        site.reply(429, {}, headers={"Retry-After": "3600"})
        with pytest.raises(RateLimitError) as caught:
            site.run(lambda c: c.get_doc("ToDo", "T1"))
        assert caught.value.retry_after == 3600
        assert len(site.requests) == 1

    def test_retries_stop_at_max_attempts(self, site: Site) -> None:
        site.reply(503, {})
        with pytest.raises(ServerError):
            site.run(lambda c: c.get_doc("ToDo", "T1"), retry=RetryPolicy(3, backoff_base=0))
        assert len(site.requests) == 3


class TestPasswordSession:
    def test_logs_in_once_and_logs_out_on_close(self, site: Site) -> None:
        site.reply(body={"message": "Logged In"}, headers={"Set-Cookie": "sid=abc; Path=/"})
        site.reply(body={"data": {"name": "T1"}})
        site.reply(body={"data": {"name": "T2"}})
        site.reply(body={})

        def two_reads(client: Any) -> Any:
            if site.kind == "sync":
                client.get_doc("ToDo", "T1")
                return client.get_doc("ToDo", "T2")

            async def both() -> Any:
                await client.get_doc("ToDo", "T1")
                return await client.get_doc("ToDo", "T2")

            return both()

        site.run(two_reads, auth=PasswordAuth("admin", "pw-value"))
        paths = [raw_path(r) for r in site.requests]
        assert paths == [
            "/api/method/login",
            "/api/resource/ToDo/T1",
            "/api/resource/ToDo/T2",
            "/api/method/logout",
        ]
        assert site.body(0) == {"usr": "admin", "pwd": "pw-value"}
        assert "authorization" not in site.requests[1].headers
        assert site.requests[1].headers["cookie"] == "sid=abc"


class TestSecrecy:
    def test_secret_never_reaches_logs_or_repr(
        self, site: Site, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        site.reply(404, {"exc_type": "DoesNotExistError"})
        with pytest.raises(NotFoundError) as caught:
            site.run(lambda c: c.get_doc("ToDo", "nope"))
        assert API_SECRET not in caplog.text
        assert API_SECRET not in str(caught.value)
        assert API_SECRET not in repr(caught.value)

    def test_transport_error_message_hides_query_and_headers(self, site: Site) -> None:
        site.fail(httpx.ConnectError(f"cannot reach host with {API_SECRET}"))
        with pytest.raises(TransportError) as caught:
            site.run(
                lambda c: c.get_list("ToDo", filters={"owner": "private@example.com"}),
                retry=RetryPolicy(max_attempts=1),
            )
        assert API_SECRET not in str(caught.value)
        assert "private@example.com" not in str(caught.value)


@pytest.mark.parametrize("kind", [Client, AsyncClient])
class TestConstruction:
    auth = TokenAuth("key", API_SECRET)

    def test_http_is_refused(self, kind: Any) -> None:
        with pytest.raises(ConfigurationError):
            kind("http://erp.example.com", self.auth)

    @pytest.mark.parametrize("verify", [False, True])
    def test_verify_cannot_be_a_boolean(self, kind: Any, verify: bool) -> None:
        with pytest.raises(ConfigurationError, match="cannot be switched off"):
            kind(URL, self.auth, verify=verify)

    def test_verify_accepts_a_context(self, kind: Any) -> None:
        assert kind(URL, self.auth, verify=ssl.create_default_context()).base_url == URL

    def test_missing_ca_bundle_is_reported(self, kind: Any) -> None:
        with pytest.raises(ConfigurationError, match="CA bundle"):
            kind(URL, self.auth, verify="/nonexistent/ca.pem")

    def test_auth_must_be_an_auth_object(self, kind: Any) -> None:
        with pytest.raises(ConfigurationError):
            kind(URL, ("key", "secret"))

    def test_authorization_header_cannot_be_injected(self, kind: Any) -> None:
        with pytest.raises(ConfigurationError):
            kind(URL, self.auth, headers={"Authorization": "token other:other"})

    def test_auth_is_optional(self, kind: Any) -> None:
        client = kind(URL)
        assert client.base_url == URL
        assert repr(client) == f"{kind.__name__}(base_url={URL!r}, auth=guest)"
        assert "authorization" not in client._http.headers

    def test_repr_hides_credentials(self, kind: Any) -> None:
        assert API_SECRET not in repr(kind(URL, self.auth))

    def test_redirects_are_disabled_on_the_http_client(self, kind: Any) -> None:
        assert kind(URL, self.auth)._http.follow_redirects is False
