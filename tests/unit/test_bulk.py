"""Bulk insert and update, each test run once sync and once async."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from frappex_client import (
    BulkOperationError,
    BulkUpdateFailure,
    ConfigurationError,
    PermissionDeniedError,
    TransportError,
    UnexpectedResponseError,
    ValidationError,
)

from .conftest import Site

TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "apps/frappe/frappe/client.py", line 320, in bulk_update\n'
    "frappe.exceptions.ValidationError: Value missing for Status\n"
)


def sent_docs(site: Site, index: int = -1) -> list[dict[str, Any]]:
    docs = site.body(index)["docs"]
    parsed: list[dict[str, Any]] = json.loads(docs) if isinstance(docs, str) else docs
    return parsed


class TestInsertMany:
    def test_sends_one_request_and_returns_names_in_order(self, site: Site) -> None:
        site.reply(body={"message": ["T-1", "T-2"]})
        names = site.run(
            lambda c: c.insert_many("ToDo", [{"description": "a"}, {"description": "b"}])
        )
        assert names == ["T-1", "T-2"]
        request = site.requests[0]
        assert request.method == "POST"
        assert request.url.path == "/api/method/frappe.client.insert_many"
        assert sent_docs(site) == [
            {"description": "a", "doctype": "ToDo"},
            {"description": "b", "doctype": "ToDo"},
        ]

    def test_splits_into_batches(self, site: Site) -> None:
        site.reply(body={"message": ["T-1", "T-2"]})
        site.reply(body={"message": ["T-3"]})
        docs = [{"description": str(i)} for i in range(3)]
        names = site.run(lambda c: c.insert_many("ToDo", docs, batch_size=2))
        assert names == ["T-1", "T-2", "T-3"]
        assert [len(sent_docs(site, i)) for i in range(2)] == [2, 1]

    def test_accepts_a_generator_and_integer_names(self, site: Site) -> None:
        site.reply(body={"message": [7, 8]})
        docs = ({"description": str(i)} for i in range(2))
        assert site.run(lambda c: c.insert_many("ToDo", docs)) == ["7", "8"]

    def test_nothing_to_insert_sends_nothing(self, site: Site) -> None:
        assert site.run(lambda c: c.insert_many("ToDo", [])) == []
        assert site.requests == []

    def test_does_not_change_the_callers_documents(self, site: Site) -> None:
        site.reply(body={"message": ["T-1"]})
        doc = {"description": "a"}
        site.run(lambda c: c.insert_many("ToDo", [doc]))
        assert doc == {"description": "a"}

    @pytest.mark.parametrize("batch_size", [0, 201, -1, True])
    def test_batch_size_must_be_within_frappes_limit(self, site: Site, batch_size: int) -> None:
        with pytest.raises(ConfigurationError, match="batch_size"):
            site.run(lambda c: c.insert_many("ToDo", [{}], batch_size=batch_size))
        assert site.requests == []

    def test_documents_of_another_doctype_are_refused(self, site: Site) -> None:
        with pytest.raises(ConfigurationError, match=r"docs\[1\]"):
            site.run(lambda c: c.insert_many("ToDo", [{}, {"doctype": "User"}]))
        assert site.requests == []

    @pytest.mark.parametrize("docs", [{"description": "a"}, "abc", [["description", "a"]]])
    def test_docs_must_be_a_list_of_mappings(self, site: Site, docs: Any) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.insert_many("ToDo", docs))

    def test_doctype_is_required(self, site: Site) -> None:
        with pytest.raises(ConfigurationError, match="doctype"):
            site.run(lambda c: c.insert_many(" ", [{}]))

    def test_failed_batch_reports_progress_and_cause(self, site: Site) -> None:
        site.reply(body={"message": ["T-1", "T-2"]})
        site.reply(417, {"exc_type": "ValidationError", "_server_messages": "[]"})
        docs = [{"description": str(i)} for i in range(4)]
        with pytest.raises(BulkOperationError) as caught:
            site.run(lambda c: c.insert_many("ToDo", docs, batch_size=2))
        error = caught.value
        assert error.completed == ["T-1", "T-2"]
        assert error.failed_at == 2
        assert error.failures == []
        assert isinstance(error.error, ValidationError)
        assert error.__cause__ is error.error
        assert "item 2" in str(error)

    def test_a_dropped_connection_is_not_retried(self, site: Site) -> None:
        site.fail(httpx.ReadError("boom"))
        with pytest.raises(BulkOperationError) as caught:
            site.run(lambda c: c.insert_many("ToDo", [{}]))
        assert isinstance(caught.value.error, TransportError)
        assert caught.value.completed == []
        assert len(site.requests) == 1

    def test_a_reply_without_one_name_per_document_is_rejected(self, site: Site) -> None:
        site.reply(body={"message": ["T-1"]})
        with pytest.raises(BulkOperationError) as caught:
            site.run(lambda c: c.insert_many("ToDo", [{}, {}]))
        assert isinstance(caught.value.error, UnexpectedResponseError)


class TestBulkUpdate:
    def test_sends_docs_as_a_json_string_with_names(self, site: Site) -> None:
        site.reply(body={"message": {"failed_docs": []}})
        failures = site.run(
            lambda c: c.bulk_update(
                "ToDo", {"T-1": {"status": "Closed"}, "T-2": {"priority": "Low"}}
            )
        )
        assert failures == []
        request = site.requests[0]
        assert request.method == "POST"
        assert request.url.path == "/api/method/frappe.client.bulk_update"
        assert isinstance(site.body()["docs"], str)
        assert sent_docs(site) == [
            {"status": "Closed", "doctype": "ToDo", "docname": "T-1"},
            {"priority": "Low", "doctype": "ToDo", "docname": "T-2"},
        ]

    def test_reports_documents_that_were_not_saved(self, site: Site) -> None:
        failed = [{"doc": {"doctype": "ToDo", "docname": "T-2"}, "exc": TRACEBACK}]
        site.reply(body={"message": {"failed_docs": failed}})
        failures = site.run(lambda c: c.bulk_update("ToDo", {"T-1": {"a": 1}, "T-2": {"a": 2}}))
        assert failures == [
            BulkUpdateFailure(
                name="T-2",
                message="frappe.exceptions.ValidationError: Value missing for Status",
                traceback=TRACEBACK,
            )
        ]
        assert "Traceback" not in repr(failures[0])

    def test_failure_without_a_traceback_still_has_a_message(self, site: Site) -> None:
        site.reply(body={"message": {"failed_docs": [{"doc": {"docname": "T-1"}, "exc": ""}]}})
        [failure] = site.run(lambda c: c.bulk_update("ToDo", {"T-1": {"a": 1}}))
        assert failure.message

    def test_failed_batch_keeps_earlier_results(self, site: Site) -> None:
        failed = [{"doc": {"docname": "T-2"}, "exc": TRACEBACK}]
        site.reply(body={"message": {"failed_docs": failed}})
        site.reply(403, {"exc_type": "PermissionError"})
        updates = {f"T-{i}": {"a": i} for i in range(1, 5)}
        with pytest.raises(BulkOperationError) as caught:
            site.run(lambda c: c.bulk_update("ToDo", updates, batch_size=2))
        error = caught.value
        assert error.completed == ["T-1"]
        assert [f.name for f in error.failures] == ["T-2"]
        assert error.failed_at == 2
        assert isinstance(error.error, PermissionDeniedError)
        assert len(site.requests) == 2

    @pytest.mark.parametrize("key", ["name", "doctype", "docname"])
    def test_values_cannot_retarget_the_document(self, site: Site, key: str) -> None:
        with pytest.raises(ConfigurationError, match=key):
            site.run(lambda c: c.bulk_update("ToDo", {"T-1": {key: "x"}}))
        assert site.requests == []

    @pytest.mark.parametrize(
        "updates", [[("T-1", {"a": 1})], {"": {"a": 1}}, {"T-1": ["a", 1]}, {1: {"a": 1}}]
    )
    def test_updates_must_map_names_to_values(self, site: Site, updates: Any) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.bulk_update("ToDo", updates))

    @pytest.mark.parametrize("reply", [{"message": None}, {"message": {"failed_docs": [1]}}])
    def test_an_unexpected_reply_is_rejected(self, site: Site, reply: Any) -> None:
        site.reply(body=reply)
        with pytest.raises(BulkOperationError) as caught:
            site.run(lambda c: c.bulk_update("ToDo", {"T-1": {"a": 1}}))
        assert isinstance(caught.value.error, UnexpectedResponseError)
