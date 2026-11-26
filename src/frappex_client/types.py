"""Public type aliases used in frappex-client signatures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

__all__ = ["BulkUpdateFailure", "Document", "Filters", "HTTPMethod", "ReportResult"]

Document: TypeAlias = dict[str, Any]
"""A Frappe document as returned by the REST API."""

Filters: TypeAlias = Mapping[str, Any] | Sequence[Sequence[Any]]
"""Frappe filters: ``{"status": "Open"}`` or ``[["status", "=", "Open"]]``."""

HTTPMethod: TypeAlias = Literal["GET", "POST", "PUT", "DELETE"]
"""HTTP methods frappex-client sends."""


@dataclass(frozen=True)
class BulkUpdateFailure:
    """One document for which :meth:`~frappex_client.Client.bulk_update` reported an error.

    Frappe raised while saving this document. The save is not rolled back on
    its own, so changes written before the error (for example before an
    ``on_update`` hook failed) can still be committed. Read the document
    again before deciding what to resend.

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


@dataclass(frozen=True)
class ReportResult:
    """The output of a Query, Script or Custom Report.

    Attributes:
        columns: One mapping per column with at least ``fieldname`` and
            ``label``, and ``fieldtype``, ``options`` or ``width`` when the
            report defines them.
        rows: One mapping per row, keyed by column ``fieldname``.
        total_row: The totals row Frappe adds when the report has
            *Add Total Row* switched on, kept out of ``rows``; otherwise ``None``.
        message: A note the report attached for the reader, if any.
        prepared: ``True`` when the report runs in the background (a
            *prepared report*) and the rows come from its last completed run
            with the same filters. They reflect the data at the time that run
            finished, which ``raw["doc"]`` describes.
        raw: The complete reply, for anything else such as ``chart`` or
            ``report_summary``.
    """

    columns: list[Document]
    rows: list[Document]
    total_row: Document | None = None
    message: Any = None
    prepared: bool = False
    raw: Document = field(default_factory=dict, repr=False)
