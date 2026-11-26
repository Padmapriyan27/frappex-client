"""run_report against a real site, using throwaway Query Reports."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Iterator

import pytest

from frappex_client import AsyncClient, Client, NotFoundError, PreparedReportError

from .conftest import OPTIONS, URL, token_auth

# Old-style column labels ("Label:Fieldtype/Options:Width") and list rows,
# which is what Query Reports return.
QUERY = """
select
    name as "ToDo:Link/ToDo:140",
    description as "Description:Data:300",
    1 as "Count:Int:80"
from tabToDo
where description like %(pattern)s
order by creation asc
"""


def make_report(client: Client, *, prepared: bool) -> str:
    name = f"Frappex Report {uuid.uuid4().hex[:8]}"
    client.insert(
        "Report",
        {
            "report_name": name,
            "ref_doctype": "ToDo",
            "report_type": "Query Report",
            "is_standard": "No",
            "module": "Custom",
            "query": QUERY,
            "add_total_row": 1,
            "prepared_report": 1 if prepared else 0,
        },
    )
    return name


@pytest.fixture(scope="module")
def reports(client: Client) -> Iterator[dict[str, str]]:
    created = {
        "plain": make_report(client, prepared=False),
        "prepared": make_report(client, prepared=True),
    }
    try:
        yield created
    finally:
        for name in created.values():
            # Prepared Report rows link to the Report, so they go first.
            for run in client.iter_list("Prepared Report", filters={"report_name": name}):
                with contextlib.suppress(NotFoundError):
                    client.delete("Prepared Report", run["name"])
            with contextlib.suppress(NotFoundError):
                client.delete("Report", name)


def test_columns_rows_and_total_row(client: Client, marker: str, reports: dict[str, str]) -> None:
    names = client.insert_many("ToDo", [{"description": f"{marker} {i}"} for i in range(3)])

    report = client.run_report(reports["plain"], {"pattern": f"%{marker}%"})

    assert [column["fieldname"] for column in report.columns] == ["todo", "description", "count"]
    assert report.columns[0]["fieldtype"] == "Link"
    assert report.columns[0]["options"] == "ToDo"
    # Rows saved in one request can share a creation time, so compare as sets.
    assert {row["todo"] for row in report.rows} == set(names)
    assert {row["description"] for row in report.rows} == {f"{marker} {i}" for i in range(3)}
    assert report.total_row is not None
    assert report.total_row["count"] == 3


def test_no_matching_rows(client: Client, marker: str, reports: dict[str, str]) -> None:
    report = client.run_report(reports["plain"], {"pattern": f"%{marker}-none%"})
    assert report.rows == []
    assert report.total_row is None


MAKE_PREPARED_REPORT = "frappe.core.doctype.prepared_report.prepared_report.make_prepared_report"


def wait_for_prepared_report(client: Client, name: str, timeout: float = 120) -> str:
    deadline = time.monotonic() + timeout
    while True:
        status = (client.get_value("Prepared Report", "status", name) or {}).get("status")
        if status in {"Completed", "Error"} or time.monotonic() > deadline:
            return str(status)
        time.sleep(1)


def test_prepared_report_without_a_completed_run_raises(
    client: Client, marker: str, reports: dict[str, str]
) -> None:
    with pytest.raises(PreparedReportError) as caught:
        client.run_report(reports["prepared"], {"pattern": f"%{marker}%"})
    assert caught.value.report_name == reports["prepared"]
    assert caught.value.error is None


def test_prepared_report_returns_the_rows_of_its_completed_run(
    client: Client, marker: str, reports: dict[str, str]
) -> None:
    names = client.insert_many("ToDo", [{"description": f"{marker} {i}"} for i in range(2)])
    filters = {"pattern": f"%{marker}%"}

    job = client.call(
        MAKE_PREPARED_REPORT, {"report_name": reports["prepared"], "filters": filters}
    )
    assert wait_for_prepared_report(client, job["name"]) == "Completed"

    report = client.run_report(reports["prepared"], filters)

    assert report.prepared is True
    assert {row["todo"] for row in report.rows} == set(names)
    assert report.total_row is not None
    assert report.total_row["count"] == 2


def test_async_run_report(marker: str, reports: dict[str, str]) -> None:
    async def scenario() -> None:
        async with AsyncClient(URL, token_auth(), **OPTIONS) as live:
            await live.insert("ToDo", {"description": f"{marker} async"})
            report = await live.run_report(reports["plain"], {"pattern": f"%{marker}%"})
            assert [row["description"] for row in report.rows] == [f"{marker} async"]

    asyncio.run(scenario())
