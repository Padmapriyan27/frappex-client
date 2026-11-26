"""run_report, each test run once sync and once async."""

from __future__ import annotations

import json
from typing import Any

import pytest

from frappex_client import (
    ConfigurationError,
    PreparedReportError,
    ReportResult,
    UnexpectedResponseError,
)

from .conftest import Site


def report_reply(**result: Any) -> dict[str, Any]:
    return {"message": {"columns": [], "result": [], **result}}


class TestRunReport:
    def test_sends_a_get_with_json_filters(self, site: Site) -> None:
        site.reply(body=report_reply())
        site.run(lambda c: c.run_report("General Ledger", {"company": "Acme", "group_by": None}))
        request = site.requests[0]
        assert request.method == "GET"
        assert request.url.path == "/api/method/frappe.desk.query_report.run"
        params = request.url.params
        assert params["report_name"] == "General Ledger"
        assert json.loads(params["filters"]) == {"company": "Acme", "group_by": None}
        assert params["are_default_filters"] == "0"

    def test_without_filters_the_reports_own_defaults_apply(self, site: Site) -> None:
        site.reply(body=report_reply())
        site.run(lambda c: c.run_report("Stock Balance"))
        params = site.requests[0].url.params
        assert params["filters"] == "{}"
        assert "are_default_filters" not in params

    def test_dict_columns_and_rows(self, site: Site) -> None:
        columns = [
            {"fieldname": "account", "label": "Account", "fieldtype": "Link", "options": "Account"},
            {"label": "Debit Amount", "fieldtype": "Currency"},
        ]
        rows = [{"account": "Cash", "debit_amount": 10}]
        site.reply(body=report_reply(columns=columns, result=rows, message="Note"))
        report = site.run(lambda c: c.run_report("General Ledger"))
        assert isinstance(report, ReportResult)
        assert report.columns[1]["fieldname"] == "debit_amount"
        assert report.rows == rows
        assert report.total_row is None
        assert report.message == "Note"
        assert report.raw["message"] == "Note"

    def test_string_columns_and_list_rows(self, site: Site) -> None:
        columns = ["ToDo:Link/ToDo:120", "Status:Data", "Owner Name", "Amount:Currency::"]
        site.reply(body=report_reply(columns=columns, result=[["T-1", "Open", "Ann", 5, "extra"]]))
        report = site.run(lambda c: c.run_report("Open ToDos"))
        assert report.columns[0] == {
            "label": "ToDo",
            "fieldname": "todo",
            "fieldtype": "Link",
            "options": "ToDo",
            "width": "120",
        }
        assert report.columns[2] == {"label": "Owner Name", "fieldname": "owner_name"}
        assert report.columns[3] == {
            "label": "Amount",
            "fieldname": "amount",
            "fieldtype": "Currency",
        }
        assert report.rows == [{"todo": "T-1", "status": "Open", "owner_name": "Ann", "amount": 5}]

    def test_total_row_is_kept_apart(self, site: Site) -> None:
        rows = [["A", 1], ["B", 2], ["Total", 3]]
        site.reply(body=report_reply(columns=["Name", "Count:Int"], result=rows, add_total_row=1))
        report = site.run(lambda c: c.run_report("Counts"))
        assert [row["name"] for row in report.rows] == ["A", "B"]
        assert report.total_row == {"name": "Total", "count": 3}

    def test_total_row_flag_with_no_rows(self, site: Site) -> None:
        site.reply(body=report_reply(columns=["Name"], add_total_row=True))
        report = site.run(lambda c: c.run_report("Counts"))
        assert report.rows == []
        assert report.total_row is None

    def test_missing_columns_or_rows_mean_empty(self, site: Site) -> None:
        site.reply(body={"message": {"columns": None, "result": None}})
        report = site.run(lambda c: c.run_report("Empty"))
        assert (report.columns, report.rows) == ([], [])

    def test_prepared_report_without_a_completed_run_raises(self, site: Site) -> None:
        site.reply(body={"message": {"prepared_report": True, "doc": None}})
        with pytest.raises(PreparedReportError, match="no completed background run") as caught:
            site.run(lambda c: c.run_report("Stock Ledger"))
        assert caught.value.report_name == "Stock Ledger"
        assert caught.value.error is None

    def test_prepared_report_whose_last_run_failed_raises_with_the_reason(self, site: Site) -> None:
        reply = {"prepared_report": True, "doc": {"name": "PR-1"}, "error": "Division by zero"}
        site.reply(body={"message": reply})
        with pytest.raises(PreparedReportError, match="Division by zero") as caught:
            site.run(lambda c: c.run_report("Stock Ledger"))
        assert caught.value.error == "Division by zero"

    def test_prepared_report_with_a_completed_run_returns_its_rows(self, site: Site) -> None:
        reply = {
            "prepared_report": True,
            "doc": {"name": "PR-1", "status": "Completed"},
            "columns": [{"fieldname": "item", "label": "Item"}],
            "result": [{"item": "Bolt"}, {"item": "Total"}],
            "add_total_row": True,
        }
        site.reply(body={"message": reply})
        report = site.run(lambda c: c.run_report("Stock Ledger", {"company": "Acme"}))
        assert report.prepared is True
        assert report.rows == [{"item": "Bolt"}]
        assert report.total_row == {"item": "Total"}
        assert report.raw["doc"]["name"] == "PR-1"

    def test_an_ordinary_report_is_not_marked_prepared(self, site: Site) -> None:
        site.reply(body=report_reply(columns=["Name"], result=[["A"]]))
        assert site.run(lambda c: c.run_report("Counts")).prepared is False

    def test_is_retried_as_a_read(self, site: Site) -> None:
        site.reply(503, {})
        site.reply(body=report_reply(columns=["Name"], result=[["A"]]))
        report = site.run(lambda c: c.run_report("Counts"))
        assert report.rows == [{"name": "A"}]
        assert len(site.requests) == 2

    @pytest.mark.parametrize(
        "reply",
        [
            {"message": None},
            {"message": {"columns": "x", "result": []}},
            {"message": {"columns": [1], "result": []}},
            {"message": {"columns": ["Name"], "result": ["A"]}},
        ],
    )
    def test_malformed_replies_are_rejected(self, site: Site, reply: Any) -> None:
        site.reply(body=reply)
        with pytest.raises(UnexpectedResponseError):
            site.run(lambda c: c.run_report("Counts"))

    @pytest.mark.parametrize(
        ("report_name", "filters"), [("", None), ("  ", None), ("Counts", [["a", "=", 1]])]
    )
    def test_arguments_are_checked_before_sending(
        self, site: Site, report_name: str, filters: Any
    ) -> None:
        with pytest.raises(ConfigurationError):
            site.run(lambda c: c.run_report(report_name, filters))
        assert site.requests == []
