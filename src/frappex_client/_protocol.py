"""The Frappe REST wire format, with no network code.

This module knows how to turn names into safe URL paths and how to turn a
raw HTTP reply into either a payload or the right exception. The sync and
async clients both go through it, so the rules live in one place.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from .exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
    ValidationError,
)
from .types import HTTPMethod

__all__ = [
    "RawResponse",
    "Request",
    "decode",
    "file_path",
    "method_path",
    "parse_retry_after",
    "resource_path",
]

_METHOD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
_STATUS_ERRORS: dict[int, type[APIError]] = {
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    429: RateLimitError,
}


@dataclass(frozen=True)
class Request:
    """One HTTP request, described as plain data.

    Attributes:
        method: HTTP method.
        path: Path below the site root, already percent-encoded.
        params: Query-string parameters.
        json: Body to send as JSON, if any.
        form: Form fields for a multipart upload.
        file: ``(filename, content)`` for a multipart upload.
    """

    method: HTTPMethod
    path: str
    params: Mapping[str, str] = field(default_factory=dict)
    json: Any = None
    form: Mapping[str, str] | None = None
    file: tuple[str, bytes] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class RawResponse:
    """The parts of an HTTP reply that decoding needs."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes = field(repr=False)


def _segment(value: str, what: str) -> str:
    """Percent-encode ``value`` so it stays a single URL path segment.

    Encoding ``/`` keeps a document name from addressing another endpoint.
    ``.`` and ``..`` are refused because HTTP clients collapse dot segments,
    which would silently change the target of the request.
    """
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{what} must be a non-empty string.")
    if value in {".", ".."}:
        raise ConfigurationError(f"{what} must not be '.' or '..'.")
    return quote(value, safe="")


def resource_path(doctype: str, name: str | None = None) -> str:
    """Return the ``/api/resource`` path for a DocType or one document."""
    path = f"/api/resource/{_segment(doctype, 'doctype')}"
    return path if name is None else f"{path}/{_segment(name, 'name')}"


def method_path(method: str) -> str:
    """Return the ``/api/method`` path for a dotted method name.

    Raises:
        ConfigurationError: ``method`` is not a dotted Python identifier.
    """
    if not isinstance(method, str) or not _METHOD_NAME.fullmatch(method):
        raise ConfigurationError("method must be a dotted name such as 'frappe.client.get_count'.")
    return f"/api/method/{method}"


def file_path(file_url: str) -> str:
    """Return a safe request path for a file stored on the site.

    Only site-relative locations are accepted, so a file URL taken from a
    document can never send the caller's credentials to another host.

    Raises:
        ConfigurationError: ``file_url`` is absolute, protocol-relative or
            tries to climb out of its directory.
    """
    if not isinstance(file_url, str) or not file_url.startswith("/"):
        raise ConfigurationError("file_url must be a site-relative path starting with '/'.")
    if file_url.startswith("//") or "\\" in file_url or "?" in file_url or "#" in file_url:
        raise ConfigurationError("file_url must be a plain site-relative path.")
    segments = file_url.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise ConfigurationError("file_url must not contain '.' or '..' segments.")
    return "/".join(quote(segment, safe="") for segment in segments)


def parse_retry_after(headers: Mapping[str, str]) -> float | None:
    """Return the ``Retry-After`` header as seconds, if it is a number."""
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _load_json(body: bytes | str) -> Any:
    """Parse JSON, returning ``None`` for anything that is not valid JSON."""
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None


def _server_messages(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Extract the messages Frappe packs into ``_server_messages``.

    The field is a JSON list whose items are themselves JSON objects encoded
    as strings; anything that does not fit that shape is kept verbatim.
    """
    raw = payload.get("_server_messages")
    items = _load_json(raw) if isinstance(raw, str) else raw
    if not isinstance(items, list):
        return ()
    messages: list[str] = []
    for item in items:
        parsed = _load_json(item) if isinstance(item, str) else item
        if isinstance(parsed, Mapping) and isinstance(parsed.get("message"), str):
            messages.append(parsed["message"])
        elif isinstance(item, str):
            messages.append(item)
    return tuple(messages)


def _traceback(payload: Mapping[str, Any]) -> str | None:
    raw = payload.get("exc")
    parsed = _load_json(raw) if isinstance(raw, str) else raw
    if isinstance(parsed, list):
        return "\n".join(str(part) for part in parsed) or None
    return raw if isinstance(raw, str) and raw else None


def _exception_type(payload: Mapping[str, Any]) -> str | None:
    """Return the name of the server-side exception class, when reported.

    Frappe sends it as ``exc_type``. When that is missing, the name is taken
    from ``exception``, the last line of the traceback, such as
    ``frappe.exceptions.MandatoryError: Title``.
    """
    exc_type = payload.get("exc_type")
    if isinstance(exc_type, str) and exc_type:
        return exc_type
    exception = payload.get("exception")
    if isinstance(exception, str):
        name = exception.split(":", 1)[0].strip().rsplit(".", 1)[-1]
        if name.isidentifier():
            return name
    return None


def _error(response: RawResponse) -> APIError:
    status = response.status_code
    loaded = _load_json(response.body)
    payload: Mapping[str, Any] = loaded if isinstance(loaded, Mapping) else {}
    exc_type = _exception_type(payload)
    messages = _server_messages(payload)

    summary = messages[0] if messages else payload.get("message")
    if not isinstance(summary, str) or not summary:
        summary = exc_type or "request failed"
    text = f"HTTP {status}: {summary}"

    details: dict[str, Any] = {
        "status_code": status,
        "exc_type": exc_type,
        "server_messages": messages,
        "traceback": _traceback(payload),
    }
    if status == 429:
        return RateLimitError(text, retry_after=parse_retry_after(response.headers), **details)
    if status >= 500:
        return ServerError(text, **details)
    return _STATUS_ERRORS.get(status, ValidationError)(text, **details)


def decode(response: RawResponse) -> dict[str, Any]:
    """Turn a raw reply into the JSON object Frappe sent.

    Raises:
        APIError: The site reported an error (a subclass matches the status).
        UnexpectedResponseError: The reply is a redirect or is not a JSON
            object, so it did not come from the Frappe API.
    """
    status = response.status_code
    if 300 <= status < 400:
        raise UnexpectedResponseError(
            f"HTTP {status}: the server redirected the request. Redirects are not followed, "
            "so credentials are never sent to another address. Check base_url.",
            status_code=status,
        )
    if status >= 400:
        raise _error(response)
    payload = _load_json(response.body)
    if not isinstance(payload, dict):
        raise UnexpectedResponseError(
            f"HTTP {status}: the reply is not a JSON object. Check that base_url points "
            "at a Frappe site.",
            status_code=status,
        )
    return payload
