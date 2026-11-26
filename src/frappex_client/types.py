"""Public type aliases used in frappex-client signatures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

__all__ = ["BulkUpdateFailure", "Document", "Filters", "HTTPMethod"]

Document: TypeAlias = dict[str, Any]
"""A Frappe document as returned by the REST API."""

Filters: TypeAlias = Mapping[str, Any] | Sequence[Sequence[Any]]
"""Frappe filters: ``{"status": "Open"}`` or ``[["status", "=", "Open"]]``."""

HTTPMethod: TypeAlias = Literal["GET", "POST", "PUT", "DELETE"]
"""HTTP methods frappex-client sends."""


@dataclass(frozen=True)
class BulkUpdateFailure:
    """One document that :meth:`~frappex_client.Client.bulk_update` could not save.

    Attributes:
        name: Name of the document.
        message: The last line of the server's error, such as
            ``"frappe.exceptions.ValidationError: Value missing for Status"``.
        traceback: The full server traceback. It is kept out of ``repr`` so
            it does not end up in logs by accident.
    """

    name: str
    message: str
    traceback: str = field(default="", repr=False)
