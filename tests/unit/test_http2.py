"""Opt-in HTTP/2."""

from __future__ import annotations

import importlib.util
import logging
from typing import Any

import httpx
import pytest

from frappex_client import AsyncClient, Client, ConfigurationError

URL = "https://erp.example.com"


@pytest.mark.parametrize("kind", [Client, AsyncClient])
class TestHttp2Setting:
    def test_off_by_default(self, kind: Any) -> None:
        client = kind(URL)
        assert client.http2 is False
        assert client._http._transport._pool._http2 is False

    def test_offered_when_asked(self, kind: Any) -> None:
        client = kind(URL, http2=True)
        assert client.http2 is True
        assert client._http._transport._pool._http2 is True

    def test_needs_the_h2_package(self, kind: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        real = importlib.util.find_spec
        monkeypatch.setattr(
            importlib.util, "find_spec", lambda name, *a: None if name == "h2" else real(name, *a)
        )
        with pytest.raises(ConfigurationError, match=r"frappex-client\[http2\]"):
            kind(URL, http2=True)
        assert kind(URL).http2 is False  # unaffected when not asked for

    @pytest.mark.parametrize("value", [1, "yes", None])
    def test_must_be_a_boolean(self, kind: Any, value: Any) -> None:
        with pytest.raises(ConfigurationError, match="http2"):
            kind(URL, http2=value)


def test_the_protocol_used_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "pong"}, extensions={"http_version": b"HTTP/2"})

    with (
        caplog.at_level(logging.DEBUG, logger="frappex_client"),
        Client(URL, transport=httpx.MockTransport(handler)) as client,
    ):
        assert client.ping() == "pong"
    assert "GET /api/method/ping -> 200 (HTTP/2)" in caplog.text
