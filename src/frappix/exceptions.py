"""Exceptions raised by frappix.

Every exception derives from :class:`FrappixError`, so callers can catch the
whole family with one clause or pick a specific failure.
"""

from __future__ import annotations

__all__ = [
    "APIError",
    "AuthenticationError",
    "ConfigurationError",
    "ConflictError",
    "FrappixError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "RequestTimeoutError",
    "ResponseTooLargeError",
    "ServerError",
    "TransportError",
    "UnexpectedResponseError",
    "ValidationError",
]


class FrappixError(Exception):
    """Base class for every error raised by frappix."""


class ConfigurationError(FrappixError, ValueError):
    """The client or a call was given an unusable or unsafe argument."""


class TransportError(FrappixError):
    """The request never produced an HTTP response (DNS, TLS, connection)."""


class RequestTimeoutError(TransportError):
    """The request exceeded its timeout."""


class ResponseTooLargeError(FrappixError):
    """The response body exceeded the configured size limit."""


class UnexpectedResponseError(FrappixError):
    """The server answered with something that is not a Frappe API reply.

    Typical causes are a redirect (never followed, so credentials stay on the
    configured host), an HTML page from a proxy, or a wrong base URL.
    """

    def __init__(self, message: str, *, status_code: int) -> None:
        """Store the HTTP status alongside the message."""
        super().__init__(message)
        self.status_code = status_code


class APIError(FrappixError):
    """The Frappe site rejected the request.

    Attributes:
        status_code: HTTP status of the response.
        exc_type: Name of the server-side exception class, when reported.
        server_messages: Human-readable messages the server attached.
        traceback: Server traceback, when the site exposes one. It is kept
            off ``str(error)`` on purpose so it does not leak into logs.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        exc_type: str | None = None,
        server_messages: tuple[str, ...] = (),
        traceback: str | None = None,
    ) -> None:
        """Build the error from the decoded response."""
        super().__init__(message)
        self.status_code = status_code
        self.exc_type = exc_type
        self.server_messages = server_messages
        self.traceback = traceback


class AuthenticationError(APIError):
    """Credentials are missing, wrong or expired (HTTP 401)."""


class PermissionDeniedError(APIError):
    """The authenticated user may not perform the action (HTTP 403)."""


class NotFoundError(APIError):
    """The document, DocType or method does not exist (HTTP 404)."""


class ConflictError(APIError):
    """The write clashes with existing data, such as a duplicate (HTTP 409)."""


class ValidationError(APIError):
    """The site refused the data as invalid (HTTP 417 and other 4xx)."""


class RateLimitError(APIError):
    """The site is rate limiting the caller (HTTP 429).

    Attributes:
        retry_after: Seconds the server asked the caller to wait, if stated.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        exc_type: str | None = None,
        server_messages: tuple[str, ...] = (),
        traceback: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Build the error and record the advised wait."""
        super().__init__(
            message,
            status_code=status_code,
            exc_type=exc_type,
            server_messages=server_messages,
            traceback=traceback,
        )
        self.retry_after = retry_after


class ServerError(APIError):
    """The site failed while handling the request (HTTP 5xx)."""
