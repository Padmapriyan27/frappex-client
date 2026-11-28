"""frappex-client: a typed sync and async REST client for Frappe and ERPNext sites.

Quick start::

    from frappex_client import Client, TokenAuth

    with Client("https://erp.example.com", TokenAuth(api_key, api_secret)) as client:
        open_todos = client.get_list("ToDo", filters={"status": "Open"})

:class:`AsyncClient` offers the same methods for ``asyncio`` programs.
"""

from ._async_client import AsyncClient
from ._auth import Auth, BearerAuth, PasswordAuth, Secret, TokenAuth
from ._client import Client
from ._config import RetryPolicy
from .exceptions import (
    APIError,
    AuthenticationError,
    BulkOperationError,
    ConfigurationError,
    ConflictError,
    FrappexError,
    NotFoundError,
    PermissionDeniedError,
    PreparedReportError,
    RateLimitError,
    ReadOnlyError,
    RequestTimeoutError,
    ResponseTooLargeError,
    ServerError,
    TransportError,
    UnexpectedResponseError,
    ValidationError,
)
from .types import BulkUpdateFailure, Document, Filters, ReportResult

__all__ = [
    "APIError",
    "AsyncClient",
    "Auth",
    "AuthenticationError",
    "BearerAuth",
    "BulkOperationError",
    "BulkUpdateFailure",
    "Client",
    "ConfigurationError",
    "ConflictError",
    "Document",
    "Filters",
    "FrappexError",
    "NotFoundError",
    "PasswordAuth",
    "PermissionDeniedError",
    "PreparedReportError",
    "RateLimitError",
    "ReadOnlyError",
    "ReportResult",
    "RequestTimeoutError",
    "ResponseTooLargeError",
    "RetryPolicy",
    "Secret",
    "ServerError",
    "TokenAuth",
    "TransportError",
    "UnexpectedResponseError",
    "ValidationError",
]
