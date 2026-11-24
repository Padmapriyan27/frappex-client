"""Fixtures for tests that talk to a real Frappe site.

The whole directory is skipped unless FRAPPEX_TEST_URL, FRAPPEX_TEST_API_KEY
and FRAPPEX_TEST_API_SECRET are set. Point them at a development site, never
production. The API user needs the System Manager role, because one fixture
creates (and afterwards deletes) a custom DocType.

Everything the tests write carries a unique marker and is removed again.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from frappex_client import Client, NotFoundError, TokenAuth

URL = os.environ.get("FRAPPEX_TEST_URL", "")
KEY = os.environ.get("FRAPPEX_TEST_API_KEY", "")
SECRET = os.environ.get("FRAPPEX_TEST_API_SECRET", "")
HOST = os.environ.get("FRAPPEX_TEST_HOST_HEADER", "")
USERNAME = os.environ.get("FRAPPEX_TEST_USERNAME", "")
PASSWORD = os.environ.get("FRAPPEX_TEST_PASSWORD", "")

CONFIGURED = bool(URL and KEY and SECRET)

OPTIONS: dict[str, Any] = {
    "allow_insecure_http": URL.startswith("http://"),
    "headers": {"Host": HOST} if HOST else None,
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test here as ``integration`` and skip them when unconfigured."""
    skip = pytest.mark.skip(reason="live-site settings are not configured")
    for item in items:
        if "tests/integration" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
            if not CONFIGURED:
                item.add_marker(skip)


def token_auth() -> TokenAuth:
    return TokenAuth(KEY, SECRET)


@pytest.fixture(scope="session")
def client() -> Iterator[Client]:
    with Client(URL, token_auth(), **OPTIONS) as live:
        yield live


@pytest.fixture
def marker(client: Client) -> Iterator[str]:
    """A unique tag; every ToDo whose description contains it is deleted."""
    tag = f"frappex-test-{uuid.uuid4().hex}"
    yield tag
    for row in client.iter_list("ToDo", filters={"description": ["like", f"%{tag}%"]}):
        client.delete("ToDo", row["name"])


@pytest.fixture(scope="session")
def doctype(client: Client) -> Iterator[str]:
    """A throwaway submittable DocType whose documents are named by the caller."""
    name = f"Frappex Test {uuid.uuid4().hex[:8]}"
    client.insert(
        "DocType",
        {
            "name": name,
            "module": "Custom",
            "custom": 1,
            "is_submittable": 1,
            "autoname": "prompt",
            "allow_rename": 1,
            "fields": [
                {"fieldname": "title", "label": "Title", "fieldtype": "Data", "reqd": 1},
                {"fieldname": "amount", "label": "Amount", "fieldtype": "Int"},
            ],
            "permissions": [
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1,
                    "submit": 1,
                    "cancel": 1,
                }
            ],
        },
    )
    try:
        yield name
    finally:
        for row in client.iter_list(name, fields=["name", "docstatus"]):
            if row["docstatus"] == 1:
                client.cancel(name, row["name"])
            with contextlib.suppress(NotFoundError):
                client.delete(name, row["name"])
        client.delete("DocType", name)
