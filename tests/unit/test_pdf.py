"""Print-format PDFs, each test run once sync and once async."""

from __future__ import annotations

import io
from typing import Any

import httpx
import pytest

from frappex_client import (
    ConfigurationError,
    NotFoundError,
    RateLimitError,
    ResponseTooLargeError,
    TransportError,
    UnexpectedResponseError,
)

from .conftest import Site

PDF = b"%PDF-1.4\n" + b"x" * 100 + b"\n%%EOF"
PDF_HEADERS = {"Content-Type": "application/pdf"}


class TestDownloadPdf:
    def test_requests_the_print_endpoint_and_returns_bytes(self, site: Site) -> None:
        site.reply(content=PDF, headers=PDF_HEADERS)
        assert site.run(lambda c: c.download_pdf("Sales Invoice", "SINV/0001")) == PDF
        request = site.requests[0]
        assert request.method == "GET"
        assert request.url.path == "/api/method/frappe.utils.print_format.download_pdf"
        assert dict(request.url.params) == {
            "doctype": "Sales Invoice",
            "name": "SINV/0001",
            "no_letterhead": "0",
        }

    def test_passes_print_options(self, site: Site) -> None:
        site.reply(content=PDF, headers=PDF_HEADERS)
        site.run(
            lambda c: c.download_pdf(
                "Sales Invoice", "SINV-1", print_format="Detailed", letterhead="Acme", language="de"
            )
        )
        params = site.requests[0].url.params
        assert params["format"] == "Detailed"
        assert params["letterhead"] == "Acme"
        assert params["language"] == "de"
        assert params["no_letterhead"] == "0"

    def test_no_letterhead(self, site: Site) -> None:
        site.reply(content=PDF, headers=PDF_HEADERS)
        site.run(lambda c: c.download_pdf("ToDo", "T-1", no_letterhead=True))
        assert site.requests[0].url.params["no_letterhead"] == "1"

    def test_content_type_parameters_are_accepted(self, site: Site) -> None:
        site.reply(content=PDF, headers={"Content-Type": "Application/PDF; charset=binary"})
        assert site.run(lambda c: c.download_pdf("ToDo", "T-1")) == PDF

    def test_a_reply_that_is_not_a_pdf_is_refused(self, site: Site) -> None:
        target = io.BytesIO()
        site.reply(content=b"<html>Login</html>", headers={"Content-Type": "text/html"})
        with pytest.raises(UnexpectedResponseError, match="text/html"):
            site.run(lambda c: c.download_pdf_to("ToDo", "T-1", target))
        assert target.getvalue() == b""

    def test_download_pdf_to_streams_into_a_file(self, site: Site) -> None:
        target = io.BytesIO()
        site.reply(content=PDF, headers=PDF_HEADERS)
        assert site.run(lambda c: c.download_pdf_to("ToDo", "T-1", target)) == len(PDF)
        assert target.getvalue() == PDF

    def test_download_pdf_to_honours_max_bytes(self, site: Site) -> None:
        site.reply(content=PDF, headers=PDF_HEADERS)
        with pytest.raises(ResponseTooLargeError):
            site.run(lambda c: c.download_pdf_to("ToDo", "T-1", io.BytesIO(), max_bytes=10))

    def test_download_pdf_is_capped_by_max_response_bytes(self, site: Site) -> None:
        site.reply(content=PDF, headers=PDF_HEADERS)
        with pytest.raises(ResponseTooLargeError):
            site.run(lambda c: c.download_pdf("ToDo", "T-1"), max_response_bytes=10)

    def test_errors_map_to_exceptions(self, site: Site) -> None:
        site.reply(404, {"exc_type": "DoesNotExistError"})
        with pytest.raises(NotFoundError):
            site.run(lambda c: c.download_pdf("ToDo", "missing"))

    def test_rate_limit_is_reported_not_waited_out(self, site: Site) -> None:
        site.reply(429, {}, headers={"Retry-After": "0"})
        with pytest.raises(RateLimitError):
            site.run(lambda c: c.download_pdf("ToDo", "T-1"))
        assert len(site.requests) == 1

    def test_is_not_retried_after_a_network_error(self, site: Site) -> None:
        site.fail(httpx.ReadError("boom"))
        with pytest.raises(TransportError):
            site.run(lambda c: c.download_pdf("ToDo", "T-1"))
        assert len(site.requests) == 1

    @pytest.mark.parametrize(
        ("doctype", "name", "options"),
        [
            ("", "T-1", {}),
            ("ToDo", "", {}),
            ("ToDo", None, {}),
            ("ToDo", "T-1", {"letterhead": "Acme", "no_letterhead": True}),
        ],
    )
    def test_arguments_are_checked_before_sending(
        self, site: Site, doctype: str, name: Any, options: dict[str, Any]
    ) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.download_pdf(doctype, name, **options))
        assert site.requests == []
