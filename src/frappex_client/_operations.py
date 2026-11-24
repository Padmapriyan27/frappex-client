"""Every API call frappex-client can make, described as data.

Each function returns an :class:`Operation`: the request to send and a
function that picks the result out of the decoded reply. Nothing here
touches the network, which is what lets the sync and async clients share one
implementation of the Frappe API.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from ._protocol import Request, method_path, resource_path
from .exceptions import ConfigurationError, UnexpectedResponseError
from .types import Document, Filters

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 100
STABLE_ORDER = "creation asc, name asc"


@dataclass(frozen=True)
class Operation(Generic[T]):
    """A request paired with the parser for its reply."""

    request: Request
    parse: Callable[[dict[str, Any]], T]


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def _data(payload: dict[str, Any]) -> Any:
    return payload.get("data")


def _message(payload: dict[str, Any]) -> Any:
    return payload.get("message")


def _nothing(payload: dict[str, Any]) -> None:
    return None


def _document(source: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Document]:
    def parse(payload: dict[str, Any]) -> Document:
        value = source(payload)
        if not isinstance(value, dict):
            raise UnexpectedResponseError("The reply does not contain a document.", status_code=200)
        return value

    return parse


def _documents(payload: dict[str, Any]) -> list[Document]:
    value = _data(payload)
    if not isinstance(value, list):
        raise UnexpectedResponseError("The reply does not contain a list.", status_code=200)
    return value


def ping() -> Operation[str]:
    """Check that the site answers; needs no permissions."""
    return Operation(Request("GET", method_path("ping")), lambda p: str(_message(p)))


def get_logged_user() -> Operation[str]:
    """Return the user the credentials belong to."""
    return Operation(
        Request("GET", method_path("frappe.auth.get_logged_user")), lambda p: str(_message(p))
    )


def login(username: str, password: str) -> Operation[None]:
    """Open a cookie session."""
    return Operation(
        Request("POST", method_path("login"), json={"usr": username, "pwd": password}), _nothing
    )


def logout() -> Operation[None]:
    """Close the cookie session."""
    return Operation(Request("POST", method_path("logout")), _nothing)


def get_list(
    doctype: str,
    *,
    fields: Sequence[str] | None = None,
    filters: Filters | None = None,
    or_filters: Filters | None = None,
    order_by: str | None = None,
    limit: int = 20,
    offset: int = 0,
    parent: str | None = None,
) -> Operation[list[Document]]:
    """List documents of ``doctype``."""
    if limit < 1:
        raise ConfigurationError("limit must be at least 1; use iter_list to read every row.")
    if offset < 0:
        raise ConfigurationError("offset must not be negative.")
    params = {"limit_page_length": str(limit), "limit_start": str(offset)}
    if fields is not None:
        if isinstance(fields, str):
            raise ConfigurationError("fields must be a list of field names, not a string.")
        params["fields"] = _dumps(list(fields))
    if filters is not None:
        params["filters"] = _dumps(filters)
    if or_filters is not None:
        params["or_filters"] = _dumps(or_filters)
    if order_by is not None:
        params["order_by"] = order_by
    if parent is not None:
        params["parent"] = parent
    return Operation(Request("GET", resource_path(doctype), params=params), _documents)


def get_doc(doctype: str, name: str) -> Operation[Document]:
    """Fetch one document."""
    return Operation(Request("GET", resource_path(doctype, name)), _document(_data))


def insert(doctype: str, values: Mapping[str, Any]) -> Operation[Document]:
    """Create a document."""
    return Operation(Request("POST", resource_path(doctype), json=dict(values)), _document(_data))


def update(doctype: str, name: str, values: Mapping[str, Any]) -> Operation[Document]:
    """Change fields of a document."""
    return Operation(
        Request("PUT", resource_path(doctype, name), json=dict(values)), _document(_data)
    )


def delete(doctype: str, name: str) -> Operation[None]:
    """Delete a document."""
    return Operation(Request("DELETE", resource_path(doctype, name)), _nothing)


def submit(doctype: str, name: str) -> Operation[None]:
    """Submit a document through its whitelisted ``submit`` method."""
    return Operation(
        Request("POST", resource_path(doctype, name), json={"run_method": "submit"}), _nothing
    )


def cancel(doctype: str, name: str) -> Operation[None]:
    """Cancel a submitted document."""
    return Operation(
        Request(
            "POST", method_path("frappe.client.cancel"), json={"doctype": doctype, "name": name}
        ),
        _nothing,
    )


def rename(doctype: str, old_name: str, new_name: str, *, merge: bool) -> Operation[str]:
    """Rename a document and return its new name."""
    body = {"doctype": doctype, "old_name": old_name, "new_name": new_name, "merge": merge}
    return Operation(
        Request("POST", method_path("frappe.client.rename_doc"), json=body),
        lambda p: str(_message(p)),
    )


def get_count(doctype: str, filters: Filters | None) -> Operation[int]:
    """Count documents matching ``filters``."""
    params = {"doctype": doctype}
    if filters is not None:
        params["filters"] = _dumps(filters)

    def parse(payload: dict[str, Any]) -> int:
        value = _message(payload)
        if isinstance(value, bool) or not isinstance(value, int):
            raise UnexpectedResponseError("The reply does not contain a count.", status_code=200)
        return value

    return Operation(Request("GET", method_path("frappe.client.get_count"), params=params), parse)


def get_value(
    doctype: str, fieldname: str | Sequence[str], filters: Filters | str | None
) -> Operation[Document | None]:
    """Read one or more fields of the first matching document."""
    params = {
        "doctype": doctype,
        "fieldname": fieldname if isinstance(fieldname, str) else _dumps(list(fieldname)),
    }
    if filters is not None:
        params["filters"] = filters if isinstance(filters, str) else _dumps(filters)

    def parse(payload: dict[str, Any]) -> Document | None:
        value = _message(payload)
        # Frappe answers with an empty object when no document matches.
        return value if isinstance(value, dict) and value else None

    return Operation(Request("GET", method_path("frappe.client.get_value"), params=params), parse)


def set_value(doctype: str, name: str, values: Mapping[str, Any]) -> Operation[Document]:
    """Set fields on a document and return the saved document."""
    body = {"doctype": doctype, "name": name, "fieldname": dict(values)}
    return Operation(
        Request("POST", method_path("frappe.client.set_value"), json=body), _document(_message)
    )


def call(
    method: str, params: Mapping[str, Any] | None, http_method: Literal["GET", "POST"]
) -> Operation[Any]:
    """Call a whitelisted server method."""
    if http_method not in ("GET", "POST"):
        raise ConfigurationError("http_method must be 'GET' or 'POST'.")
    arguments = dict(params or {})
    if http_method == "POST":
        return Operation(Request("POST", method_path(method), json=arguments), _message)
    query = {
        key: value if isinstance(value, str) else _dumps(value)
        for key, value in arguments.items()
        if value is not None
    }
    return Operation(Request("GET", method_path(method), params=query), _message)


def upload_file(
    filename: str,
    content: bytes,
    *,
    is_private: bool,
    doctype: str | None,
    docname: str | None,
    fieldname: str | None,
    folder: str | None,
) -> Operation[Document]:
    """Upload a file, optionally attached to a document."""
    if not isinstance(filename, str) or not filename or "/" in filename or "\\" in filename:
        raise ConfigurationError("filename must be a bare file name without directories.")
    if not isinstance(content, bytes | bytearray):
        raise ConfigurationError("content must be bytes.")
    form = {"is_private": "1" if is_private else "0"}
    optional = {"doctype": doctype, "docname": docname, "fieldname": fieldname, "folder": folder}
    form.update({key: value for key, value in optional.items() if value is not None})
    return Operation(
        Request("POST", method_path("upload_file"), form=form, file=(filename, bytes(content))),
        _document(_message),
    )
