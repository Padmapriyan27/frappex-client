"""Opt-in HTTP/2 against real sites."""

from __future__ import annotations

import logging
import os

import pytest

from frappex_client import Client

from .conftest import OPTIONS, URL, token_auth

# A public Frappe site that serves HTTP/2; only its guest ping is called.
HTTP2_URL = os.environ.get("FRAPPEX_TEST_HTTP2_URL", "")


def test_falls_back_to_http1_where_http2_is_not_offered(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.DEBUG, logger="frappex_client"),
        Client(URL, token_auth(), http2=True, **OPTIONS) as client,
    ):
        assert client.ping() == "pong"
        assert client.get_logged_user()
    assert "(HTTP/1.1)" in caplog.text
    assert "(HTTP/2)" not in caplog.text


@pytest.mark.skipif(not HTTP2_URL, reason="FRAPPEX_TEST_HTTP2_URL is not set")
def test_negotiates_http2_with_a_site_that_offers_it(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.DEBUG, logger="frappex_client"),
        Client(HTTP2_URL, http2=True) as client,
    ):
        assert client.ping() == "pong"
    assert "GET /api/method/ping -> 200 (HTTP/2)" in caplog.text
