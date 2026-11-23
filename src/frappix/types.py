"""Public type aliases used in frappix signatures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypeAlias

__all__ = ["Document", "Filters", "HTTPMethod"]

Document: TypeAlias = dict[str, Any]
"""A Frappe document as returned by the REST API."""

Filters: TypeAlias = Mapping[str, Any] | Sequence[Sequence[Any]]
"""Frappe filters: ``{"status": "Open"}`` or ``[["status", "=", "Open"]]``."""

HTTPMethod: TypeAlias = Literal["GET", "POST", "PUT", "DELETE"]
"""HTTP methods frappix sends."""
