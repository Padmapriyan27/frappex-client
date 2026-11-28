"""Settings and helpers shared by the sync and async clients."""

from __future__ import annotations

import importlib.util
import logging
import os
import ssl
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

from ._auth import Auth, BearerAuth, PasswordAuth, TokenAuth
from ._config import RetryPolicy, normalise_base_url, validate_extra_headers
from ._protocol import Request
from .exceptions import (
    ConfigurationError,
    ReadOnlyError,
    RequestTimeoutError,
    ResponseTooLargeError,
    TransportError,
    UnexpectedResponseError,
)

logger = logging.getLogger("frappex_client")

# Requests a client keeps in flight at once unless told otherwise: enough to
# overlap network waits, few enough not to swamp a site's worker processes.
DEFAULT_MAX_CONCURRENCY = 10

# HTTP methods a read-only client may send.
_READ_METHODS = frozenset({"GET", "HEAD"})

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
CHUNK_SIZE = 64 * 1024

try:
    _VERSION = version("frappex-client")
except PackageNotFoundError:  # running from a source tree that is not installed
    _VERSION = "0+unknown"


def _tls_setting(verify: ssl.SSLContext | str | os.PathLike[str] | None) -> ssl.SSLContext | bool:
    """Translate ``verify`` into what httpx expects, never disabling checks."""
    if verify is None:
        return True
    if isinstance(verify, bool):
        raise ConfigurationError(
            "verify does not accept a boolean: certificate checks cannot be switched off. "
            "Pass the path of a CA bundle or an ssl.SSLContext for a private certificate."
        )
    if isinstance(verify, ssl.SSLContext):
        return verify
    if not isinstance(verify, str | os.PathLike):
        raise ConfigurationError("verify must be a CA bundle path or an ssl.SSLContext.")
    try:
        return ssl.create_default_context(cafile=os.fspath(verify))
    except (OSError, ssl.SSLError) as exc:
        raise ConfigurationError(f"Cannot load the CA bundle given in verify: {exc}") from exc


class ClientCore:
    """State and pure helpers common to both clients.

    Subclasses add the transport: how a :class:`Request` is sent and how the
    process waits between retries.
    """

    def __init__(
        self,
        base_url: str,
        auth: Auth | None,
        *,
        timeout: float | httpx.Timeout,
        retry: RetryPolicy | None,
        verify: ssl.SSLContext | str | os.PathLike[str] | None,
        allow_insecure_http: bool,
        max_response_bytes: int,
        headers: Mapping[str, str] | None,
        read_only: bool = False,
        max_concurrency: int | None = DEFAULT_MAX_CONCURRENCY,
        http2: bool = False,
    ) -> None:
        """Validate every setting before any connection is made."""
        if not isinstance(http2, bool):
            raise ConfigurationError("http2 must be True or False.")
        if http2 and importlib.util.find_spec("h2") is None:
            raise ConfigurationError(
                'http2=True needs the h2 package: pip install "frappex-client[http2]"'
            )
        if max_concurrency is not None and (
            isinstance(max_concurrency, bool)
            or not isinstance(max_concurrency, int)
            or max_concurrency < 1
        ):
            raise ConfigurationError("max_concurrency must be a positive integer or None.")
        if not isinstance(read_only, bool):
            raise ConfigurationError("read_only must be True or False.")
        if auth is not None and not isinstance(auth, TokenAuth | BearerAuth | PasswordAuth):
            raise ConfigurationError(
                "auth must be a TokenAuth, BearerAuth or PasswordAuth, or None for guest access."
            )
        if max_response_bytes < 1:
            raise ConfigurationError("max_response_bytes must be positive.")
        if not isinstance(timeout, httpx.Timeout) and timeout <= 0:
            raise ConfigurationError("timeout must be positive.")
        self._base_url = normalise_base_url(base_url, allow_insecure_http=allow_insecure_http)
        self._auth = auth
        self._retry = retry if retry is not None else RetryPolicy()
        self._max_response_bytes = max_response_bytes
        self._read_only = read_only
        self._max_concurrency = max_concurrency
        self._http2 = http2
        self._logged_in = False
        self._http_arguments: dict[str, Any] = {
            "base_url": self._base_url,
            "headers": {
                "Accept": "application/json",
                "User-Agent": f"frappex-client/{_VERSION}",
                **validate_extra_headers(headers),
                **(auth.headers() if auth is not None else {}),
            },
            "timeout": timeout,
            "verify": _tls_setting(verify),
            # Never follow redirects: a redirect to another host would carry
            # the Authorization header or session cookie with it.
            "follow_redirects": False,
            # Negotiated per connection (ALPN); falls back to HTTP/1.1.
            "http2": http2,
        }
        if max_concurrency is not None:
            # As many pooled connections as requests may be in flight, so a
            # request that got a slot never waits for a connection.
            self._http_arguments["limits"] = httpx.Limits(
                max_connections=max_concurrency, max_keepalive_connections=max_concurrency
            )

    @property
    def base_url(self) -> str:
        """Address of the Frappe site this client talks to."""
        return self._base_url

    @property
    def http2(self) -> bool:
        """Whether the client offers HTTP/2 to the site."""
        return self._http2

    @property
    def max_concurrency(self) -> int | None:
        """Most requests this client sends at once; ``None`` means no limit."""
        return self._max_concurrency

    @property
    def read_only(self) -> bool:
        """Whether the client refuses every request that could change data."""
        return self._read_only

    def _refuse_writes(self, request: Request) -> None:
        """Stop a request that could change data when the client is read-only.

        Only GET and HEAD pass: Frappe reads use them, while every write, and
        any whitelisted method called by POST, uses another method.
        """
        if self._read_only and request.method not in _READ_METHODS:
            raise ReadOnlyError(
                f"This client is read-only, so {request.method} {request.path} was not "
                "sent. Create the client without read_only=True to change data."
            )

    def __repr__(self) -> str:
        """Describe the client without revealing credentials."""
        auth = "guest" if self._auth is None else type(self._auth).__name__
        return f"{type(self).__name__}(base_url={self._base_url!r}, auth={auth})"

    @property
    def _needs_login(self) -> bool:
        return isinstance(self._auth, PasswordAuth) and not self._logged_in

    @staticmethod
    def _request_arguments(request: Request) -> dict[str, Any]:
        """Translate a :class:`Request` into ``httpx`` keyword arguments."""
        arguments: dict[str, Any] = {}
        if request.params:
            arguments["params"] = dict(request.params)
        if request.file is not None:
            arguments["files"] = {"file": request.file}
            arguments["data"] = dict(request.form or {})
        elif request.json is not None:
            arguments["json"] = request.json
        return arguments

    @staticmethod
    def _check_declared_length(headers: Mapping[str, str], limit: int | None) -> None:
        """Refuse a body whose ``Content-Length`` already exceeds ``limit``."""
        declared = headers.get("content-length")
        if limit is not None and declared is not None and declared.isdigit():
            ResponseSize(limit).add(int(declared))

    @staticmethod
    def _check_content_type(headers: Mapping[str, str], expected: str | None) -> None:
        """Refuse a successful reply whose ``Content-Type`` is not ``expected``.

        A proxy or login page can answer 200 with HTML; writing that into a
        ``.pdf`` file would hide the problem.
        """
        if expected is None:
            return
        actual = headers.get("content-type", "").split(";")[0].strip().lower()
        if actual != expected:
            raise UnexpectedResponseError(
                f"Expected {expected}, but the site answered with {actual or 'no content type'}.",
                status_code=200,
            )

    @staticmethod
    def _transport_error(request: Request, exc: httpx.HTTPError) -> TransportError:
        """Describe a failed exchange without echoing headers or query data."""
        kind = RequestTimeoutError if isinstance(exc, httpx.TimeoutException) else TransportError
        return kind(f"{request.method} {request.path} failed: {type(exc).__name__}")


class ResponseSize:
    """Running total of body bytes, checked against a limit."""

    def __init__(self, limit: int | None) -> None:
        """Start counting towards ``limit``; ``None`` means unlimited."""
        self._limit = limit
        self.total = 0

    def add(self, count: int) -> None:
        """Record ``count`` more bytes.

        Raises:
            ResponseTooLargeError: The total passed the limit.
        """
        self.total += count
        if self._limit is not None and self.total > self._limit:
            raise ResponseTooLargeError(
                f"The response is larger than the {self._limit}-byte limit."
            )
