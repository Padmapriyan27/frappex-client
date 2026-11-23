"""Argument checks and reply parsing of the operation builders."""

from __future__ import annotations

import pytest

from frappix import ConfigurationError, UnexpectedResponseError
from frappix import _operations as ops


class TestArguments:
    def test_limit_and_offset_bounds(self) -> None:
        with pytest.raises(ConfigurationError):
            ops.get_list("ToDo", limit=0)
        with pytest.raises(ConfigurationError):
            ops.get_list("ToDo", offset=-1)

    def test_optional_list_parameters(self) -> None:
        request = ops.get_list(
            "Sales Invoice Item", or_filters=[["qty", ">", 1]], parent="Sales Invoice"
        ).request
        assert request.params["or_filters"] == '[["qty",">",1]]'
        assert request.params["parent"] == "Sales Invoice"
        assert "fields" not in request.params

    def test_call_rejects_other_http_methods(self) -> None:
        with pytest.raises(ConfigurationError):
            ops.call("frappe.ping", None, "DELETE")  # type: ignore[arg-type]

    def test_call_get_drops_none_arguments(self) -> None:
        request = ops.call("frappe.ping", {"a": None, "b": 1}, "GET").request
        assert request.params == {"b": "1"}

    def test_upload_content_must_be_bytes(self) -> None:
        with pytest.raises(ConfigurationError):
            ops.upload_file(
                "a.txt",
                "text",  # type: ignore[arg-type]
                is_private=True,
                doctype=None,
                docname=None,
                fieldname=None,
                folder=None,
            )

    def test_upload_optional_fields(self) -> None:
        request = ops.upload_file(
            "a.txt",
            b"x",
            is_private=False,
            doctype="ToDo",
            docname="T1",
            fieldname="attachment",
            folder="Home/Attachments",
        ).request
        assert request.form == {
            "is_private": "0",
            "doctype": "ToDo",
            "docname": "T1",
            "fieldname": "attachment",
            "folder": "Home/Attachments",
        }
        assert request.file == ("a.txt", b"x")

    @pytest.mark.parametrize("filename", ["", "a/b.txt", "a\\b.txt"])
    def test_upload_filename_must_be_bare(self, filename: str) -> None:
        with pytest.raises(ConfigurationError):
            ops.upload_file(
                filename,
                b"x",
                is_private=True,
                doctype=None,
                docname=None,
                fieldname=None,
                folder=None,
            )


class TestReplyParsing:
    def test_document_calls_reject_a_non_document(self) -> None:
        for operation in (
            ops.get_doc("ToDo", "T1"),
            ops.insert("ToDo", {}),
            ops.update("ToDo", "T1", {}),
        ):
            with pytest.raises(UnexpectedResponseError):
                operation.parse({"data": "not a document"})
        with pytest.raises(UnexpectedResponseError):
            ops.set_value("ToDo", "T1", {"status": "Open"}).parse({"message": None})

    def test_list_rejects_a_non_list(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            ops.get_list("ToDo").parse({"data": {"name": "T1"}})

    @pytest.mark.parametrize("value", [None, "7", 7.5, True])
    def test_count_rejects_a_non_integer(self, value: object) -> None:
        with pytest.raises(UnexpectedResponseError):
            ops.get_count("ToDo", None).parse({"message": value})

    def test_simple_results(self) -> None:
        assert ops.ping().parse({"message": "pong"}) == "pong"
        assert ops.get_count("ToDo", None).parse({"message": 0}) == 0
        assert ops.rename("ToDo", "a", "b", merge=True).parse({"message": "b"}) == "b"
        assert ops.delete("ToDo", "T1").parse({"message": "ok"}) is None
        assert ops.call("frappe.ping", None, "POST").parse({}) is None
