"""frappix: a typed sync and async REST client for Frappe and ERPNext sites.

Quick start::

    from frappix import Client, TokenAuth

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
    ConfigurationError,
    ConflictError,
    FrappixError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RequestTimeoutError,
    ResponseTooLargeError,
    ServerError,
    TransportError,
    UnexpectedResponseError,
    ValidationError,
)
from .types import Document, Filters

__all__ = [
    "APIError",
    "AsyncClient",
    "Auth",
    "AuthenticationError",
    "BearerAuth",
    "Client",
    "ConfigurationError",
    "ConflictError",
    "Document",
    "Filters",
    "FrappixError",
    "NotFoundError",
    "PasswordAuth",
    "PermissionDeniedError",
    "RateLimitError",
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
