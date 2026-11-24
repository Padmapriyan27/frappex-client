"""Rules that need no network: addresses, names, secrets, replies, retries."""

from __future__ import annotations

import json

import pytest

from frappix import (
    APIError,
    AuthenticationError,
    BearerAuth,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    PasswordAuth,
    PermissionDeniedError,
    RateLimitError,
    RetryPolicy,
    Secret,
    ServerError,
    TokenAuth,
    UnexpectedResponseError,
    ValidationError,
)
from frappix._config import normalise_base_url, validate_extra_headers
from frappix._protocol import RawResponse, decode, file_path, method_path, resource_path


def raw(status: int, body: object = None, headers: dict[str, str] | None = None) -> RawResponse:
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return RawResponse(status, headers or {}, content)


class TestBaseUrl:
    def test_https_is_accepted_and_trailing_slash_dropped(self) -> None:
        assert normalise_base_url("https://erp.example.com/", allow_insecure_http=False) == (
            "https://erp.example.com"
        )

    def test_http_is_refused_by_default(self) -> None:
        with pytest.raises(ConfigurationError, match="unencrypted"):
            normalise_base_url("http://erp.example.com", allow_insecure_http=False)

    def test_http_needs_an_explicit_opt_in(self) -> None:
        assert normalise_base_url("http://localhost:8000", allow_insecure_http=True) == (
            "http://localhost:8000"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "erp.example.com",
            "ftp://erp.example.com",
            "https://",
            "https://user:pw@erp.example.com",
            "https://erp.example.com/?a=1",
            "https://erp.example.com/#frag",
        ],
    )
    def test_malformed_or_unsafe_addresses_are_refused(self, url: str) -> None:
        with pytest.raises(ConfigurationError):
            normalise_base_url(url, allow_insecure_http=True)


class TestExtraHeaders:
    @pytest.mark.parametrize("name", ["Authorization", "cookie", "Content-Length"])
    def test_managed_headers_cannot_be_overridden(self, name: str) -> None:
        with pytest.raises(ConfigurationError):
            validate_extra_headers({name: "x"})

    def test_line_breaks_are_refused(self) -> None:
        with pytest.raises(ConfigurationError):
            validate_extra_headers({"X-Site": "a\r\nInjected: 1"})

    def test_ordinary_headers_pass(self) -> None:
        assert validate_extra_headers({"Host": "site1.local"}) == {"Host": "site1.local"}


class TestPaths:
    def test_names_stay_one_segment(self) -> None:
        assert resource_path("Sales Invoice", "SINV/2026/001") == (
            "/api/resource/Sales%20Invoice/SINV%2F2026%2F001"
        )

    def test_query_and_fragment_characters_are_encoded(self) -> None:
        assert resource_path("ToDo", "a?b#c") == "/api/resource/ToDo/a%3Fb%23c"

    @pytest.mark.parametrize("name", ["", ".", ".."])
    def test_empty_and_dot_names_are_refused(self, name: str) -> None:
        with pytest.raises(ConfigurationError):
            resource_path("ToDo", name)
        with pytest.raises(ConfigurationError):
            resource_path(name)

    def test_method_names_must_be_dotted_identifiers(self) -> None:
        assert method_path("frappe.client.get_count") == "/api/method/frappe.client.get_count"
        for bad in ["", "a/b", "../x", "a b", "a.b?c=1", ".a", "a..b", "1a"]:
            with pytest.raises(ConfigurationError):
                method_path(bad)

    def test_file_paths_are_site_relative_only(self) -> None:
        assert file_path("/private/files/my report.pdf") == "/private/files/my%20report.pdf"
        for bad in [
            "https://evil.example/x",
            "//evil.example/x",
            "files/x",
            "/files/../../site_config.json",
            "/files/a?b",
            "/files\\x",
        ]:
            with pytest.raises(ConfigurationError):
                file_path(bad)


class TestSecrets:
    def test_secret_is_masked_everywhere(self) -> None:
        secret = Secret("hunter2")
        assert "hunter2" not in repr(secret)
        assert "hunter2" not in str(secret)
        assert "hunter2" not in f"{secret}"
        assert secret.reveal() == "hunter2"

    def test_auth_reprs_hide_the_secret(self) -> None:
        for auth in (
            TokenAuth("key", "hunter2"),
            BearerAuth("hunter2"),
            PasswordAuth("u", "hunter2"),
        ):
            assert "hunter2" not in repr(auth)

    def test_headers(self) -> None:
        assert TokenAuth("key", "sec").headers() == {"Authorization": "token key:sec"}
        assert BearerAuth("tok").headers() == {"Authorization": "Bearer tok"}
        assert PasswordAuth("u", "p").headers() == {}

    @pytest.mark.parametrize("value", ["", "a\r\nX-Injected: 1", "a\nb"])
    def test_empty_or_multiline_credentials_are_refused(self, value: str) -> None:
        with pytest.raises(ConfigurationError):
            Secret(value)
        with pytest.raises(ConfigurationError):
            TokenAuth("key", value)

    def test_api_key_cannot_smuggle_a_separator(self) -> None:
        with pytest.raises(ConfigurationError):
            TokenAuth("key:other", "secret")


class TestDecode:
    def test_success_returns_the_object(self) -> None:
        assert decode(raw(200, {"data": {"name": "x"}})) == {"data": {"name": "x"}}

    @pytest.mark.parametrize(
        ("status", "kind"),
        [
            (401, AuthenticationError),
            (403, PermissionDeniedError),
            (404, NotFoundError),
            (409, ConflictError),
            (417, ValidationError),
            (400, ValidationError),
            (429, RateLimitError),
            (500, ServerError),
            (503, ServerError),
        ],
    )
    def test_status_maps_to_exception(self, status: int, kind: type[APIError]) -> None:
        with pytest.raises(kind) as caught:
            decode(raw(status, {"exc_type": "SomeError"}))
        assert caught.value.status_code == status
        assert caught.value.exc_type == "SomeError"

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"exc_type": "MandatoryError"}, "MandatoryError"),
            ({"exception": "frappe.exceptions.MandatoryError: Title"}, "MandatoryError"),
            ({"exception": "ValueError: bad"}, "ValueError"),
            ({"exc_type": "A", "exception": "pkg.B: x"}, "A"),
            ({"exception": "not an exception line"}, None),
            ({"exception": 5}, None),
            ({}, None),
        ],
    )
    def test_exception_type_is_read_from_either_field(
        self, payload: dict[str, object], expected: str | None
    ) -> None:
        with pytest.raises(ValidationError) as caught:
            decode(raw(417, payload))
        assert caught.value.exc_type == expected

    def test_server_messages_are_unpacked(self) -> None:
        body = {
            "exc_type": "ValidationError",
            "_server_messages": json.dumps([json.dumps({"message": "Name is required"})]),
        }
        with pytest.raises(ValidationError, match="Name is required") as caught:
            decode(raw(417, body))
        assert caught.value.server_messages == ("Name is required",)

    def test_traceback_is_kept_off_the_message(self) -> None:
        body = {"exc_type": "TypeError", "exc": json.dumps(["Traceback: /srv/secret/path.py"])}
        with pytest.raises(ServerError) as caught:
            decode(raw(500, body))
        assert "secret/path" not in str(caught.value)
        assert caught.value.traceback == "Traceback: /srv/secret/path.py"

    def test_rate_limit_carries_retry_after(self) -> None:
        with pytest.raises(RateLimitError) as caught:
            decode(raw(429, {}, {"Retry-After": "12"}))
        assert caught.value.retry_after == 12

    def test_html_error_page_still_maps(self) -> None:
        with pytest.raises(PermissionDeniedError):
            decode(raw(403, b"<html>Forbidden</html>"))

    @pytest.mark.parametrize("status", [301, 302, 307])
    def test_redirects_are_refused(self, status: int) -> None:
        with pytest.raises(UnexpectedResponseError, match="redirect"):
            decode(raw(status, b""))

    @pytest.mark.parametrize("body", [b"<html>login</html>", b"[1, 2]", b""])
    def test_non_object_success_is_refused(self, body: bytes) -> None:
        with pytest.raises(UnexpectedResponseError):
            decode(raw(200, body))


class TestRetryPolicy:
    policy = RetryPolicy(max_attempts=3, backoff_base=0)

    def test_reads_retry_after_network_failure(self) -> None:
        assert self.policy.delay_after_failure("GET", 1) == 0

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_writes_never_retry_after_network_failure(self, method: str) -> None:
        assert self.policy.delay_after_failure(method, 1) is None

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_writes_never_retry_after_5xx(self, method: str) -> None:
        assert self.policy.delay_after_response(method, 1, 503, None) is None

    def test_reads_retry_after_gateway_errors_only(self) -> None:
        assert self.policy.delay_after_response("GET", 1, 503, None) == 0
        assert self.policy.delay_after_response("GET", 1, 500, None) is None
        assert self.policy.delay_after_response("GET", 1, 404, None) is None

    def test_rate_limit_retries_any_method_and_honours_the_header(self) -> None:
        assert self.policy.delay_after_response("POST", 1, 429, 2.0) == 2.0

    def test_long_retry_after_is_not_waited_out(self) -> None:
        assert self.policy.delay_after_response("GET", 1, 429, 3600.0) is None

    def test_attempts_are_bounded(self) -> None:
        assert self.policy.delay_after_failure("GET", 3) is None
        assert self.policy.delay_after_response("GET", 3, 429, 1.0) is None

    def test_backoff_stays_under_its_ceiling(self) -> None:
        policy = RetryPolicy(max_attempts=10, backoff_base=1, backoff_max=4)
        for attempt in range(1, 9):
            delay = policy.delay_after_failure("GET", attempt)
            assert delay is not None
            assert 0 <= delay <= min(4, 2 ** (attempt - 1))

    def test_invalid_settings_are_refused(self) -> None:
        with pytest.raises(ConfigurationError):
            RetryPolicy(max_attempts=0)
        with pytest.raises(ConfigurationError):
            RetryPolicy(backoff_base=-1)
