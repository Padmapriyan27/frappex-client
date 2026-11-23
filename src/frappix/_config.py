"""Client settings: where to connect, how long to wait, when to retry.

Everything here is pure data and pure functions, so the safety rules (HTTPS
only, no credentials in the URL, bounded retries) are tested without a
network.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .exceptions import ConfigurationError

__all__ = ["RetryPolicy", "normalise_base_url", "validate_extra_headers"]

_IDEMPOTENT_METHODS = frozenset({"GET"})
_FORBIDDEN_HEADERS = frozenset({"authorization", "cookie", "content-length", "transfer-encoding"})


def normalise_base_url(base_url: str, *, allow_insecure_http: bool) -> str:
    """Validate the site address and return it without a trailing slash.

    Args:
        base_url: Root address of the Frappe site, such as
            ``https://erp.example.com``.
        allow_insecure_http: Permit ``http://``. Credentials then travel in
            clear text, so enable it only for a local development site.

    Raises:
        ConfigurationError: The address is malformed or unsafe.
    """
    if not isinstance(base_url, str) or not base_url.strip():
        raise ConfigurationError("base_url must be a non-empty string.")
    parts = urlsplit(base_url.strip())
    scheme = parts.scheme.lower()
    if scheme not in {"https", "http"}:
        raise ConfigurationError("base_url must start with https://.")
    if scheme == "http" and not allow_insecure_http:
        raise ConfigurationError(
            "Refusing plain http://: credentials would be sent unencrypted. "
            "Use https://, or pass allow_insecure_http=True for a local development site."
        )
    if not parts.hostname:
        raise ConfigurationError("base_url has no host name.")
    if parts.username or parts.password:
        raise ConfigurationError("Put credentials in the auth argument, never in base_url.")
    if parts.query or parts.fragment:
        raise ConfigurationError("base_url must not contain a query string or fragment.")
    return f"{scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def validate_extra_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Return a copy of caller-supplied headers, rejecting unsafe ones.

    Raises:
        ConfigurationError: A header would override authentication or framing,
            or contains a line break.
    """
    checked: dict[str, str] = {}
    for name, value in (headers or {}).items():
        if name.lower() in _FORBIDDEN_HEADERS:
            raise ConfigurationError(f"The {name!r} header is managed by frappix.")
        if any(ch in f"{name}{value}" for ch in "\r\n\x00"):
            raise ConfigurationError(f"The {name!r} header contains control characters.")
        checked[name] = value
    return checked


@dataclass(frozen=True)
class RetryPolicy:
    """When and how long to wait before repeating a failed request.

    Only requests that are safe to repeat are retried:

    * ``GET`` requests after a connection failure, timeout or 502/503/504.
    * Any request after HTTP 429, because Frappe rejects a rate-limited
      request before running it.

    A write (``POST``/``PUT``/``DELETE``) is never repeated after a network
    failure or 5xx, since the first attempt may have been applied.

    Attributes:
        max_attempts: Total tries including the first. ``1`` disables retries.
        backoff_base: First delay in seconds; it doubles on each attempt.
        backoff_max: Upper bound for a computed delay, in seconds.
        max_retry_after: Longest server-requested wait that will be honoured.
            A longer ``Retry-After`` raises instead of blocking the caller.
    """

    max_attempts: int = 3
    backoff_base: float = 0.5
    backoff_max: float = 8.0
    max_retry_after: float = 30.0
    retry_statuses: frozenset[int] = field(default_factory=lambda: frozenset({502, 503, 504}))

    def __post_init__(self) -> None:
        """Reject settings that could loop forever or sleep negatively."""
        if self.max_attempts < 1:
            raise ConfigurationError("max_attempts must be at least 1.")
        if min(self.backoff_base, self.backoff_max, self.max_retry_after) < 0:
            raise ConfigurationError("Retry delays must not be negative.")

    def _backoff(self, attempt: int) -> float:
        ceiling = min(self.backoff_max, self.backoff_base * (2 ** (attempt - 1)))
        # Jitter spreads retries out; it is not used for anything secret.
        return random.uniform(0, ceiling)  # noqa: S311

    def delay_after_failure(self, method: str, attempt: int) -> float | None:
        """Return the wait before retrying a request that got no response.

        Args:
            method: HTTP method of the failed request.
            attempt: Number of the attempt that just failed, starting at 1.

        Returns:
            Seconds to sleep, or ``None`` when the request must not be retried.
        """
        if attempt >= self.max_attempts or method not in _IDEMPOTENT_METHODS:
            return None
        return self._backoff(attempt)

    def delay_after_response(
        self, method: str, attempt: int, status_code: int, retry_after: float | None
    ) -> float | None:
        """Return the wait before retrying a request that got ``status_code``.

        Args:
            method: HTTP method of the request.
            attempt: Number of the attempt that just completed, starting at 1.
            status_code: HTTP status received.
            retry_after: Parsed ``Retry-After`` header in seconds, if present.

        Returns:
            Seconds to sleep, or ``None`` when the response is final.
        """
        if attempt >= self.max_attempts:
            return None
        if status_code == 429:
            if retry_after is None:
                return self._backoff(attempt)
            return retry_after if retry_after <= self.max_retry_after else None
        if status_code in self.retry_statuses and method in _IDEMPOTENT_METHODS:
            return self._backoff(attempt)
        return None
