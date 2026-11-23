"""Document calls against a real site."""

from __future__ import annotations

import pytest

from frappix import Client, ConflictError, NotFoundError, ValidationError


def like(marker: str) -> dict[str, list[str]]:
    return {"description": ["like", f"%{marker}%"]}


def test_ping_and_identity(client: Client) -> None:
    assert client.ping() == "pong"
    assert client.get_logged_user()


def test_round_trip(client: Client, marker: str) -> None:
    created = client.insert("ToDo", {"description": f"{marker} one"})
    name = created["name"]

    assert client.get_doc("ToDo", name)["description"] == f"{marker} one"
    assert client.update("ToDo", name, {"status": "Closed"})["status"] == "Closed"
    assert client.get_value("ToDo", "status", name) == {"status": "Closed"}
    assert client.get_value("ToDo", ["status", "name"], {"name": name}) == {
        "status": "Closed",
        "name": name,
    }
    assert client.set_value("ToDo", name, {"status": "Open"})["status"] == "Open"
    assert client.get_count("ToDo", like(marker)) == 1

    client.delete("ToDo", name)
    with pytest.raises(NotFoundError) as caught:
        client.get_doc("ToDo", name)
    assert caught.value.status_code == 404
    assert caught.value.exc_type == "DoesNotExistError"


def test_get_value_returns_none_when_nothing_matches(client: Client, marker: str) -> None:
    assert client.get_value("ToDo", "status", {"description": marker}) is None


def test_list_fields_filters_order_and_paging(client: Client, marker: str) -> None:
    for index in range(3):
        status = "Closed" if index == 2 else "Open"
        client.insert("ToDo", {"description": f"{marker} {index}", "status": status})

    rows = client.get_list(
        "ToDo",
        fields=["name", "description", "status"],
        filters=like(marker),
        order_by="description asc",
    )
    assert [row["description"][-1] for row in rows] == ["0", "1", "2"]
    assert set(rows[0]) == {"name", "description", "status"}

    array_filters = [["description", "like", f"%{marker}%"], ["status", "=", "Closed"]]
    assert len(client.get_list("ToDo", filters=array_filters)) == 1

    either = {"description": f"{marker} 0", "status": "Closed"}
    assert len(client.get_list("ToDo", filters=like(marker), or_filters=either)) == 2

    page = client.get_list(
        "ToDo", filters=like(marker), order_by="description asc", limit=1, offset=1
    )
    assert len(page) == 1
    assert client.get_doc("ToDo", page[0]["name"])["description"].endswith("1")


def test_iter_list_returns_every_row_once(client: Client, marker: str) -> None:
    names = {client.insert("ToDo", {"description": f"{marker} {i}"})["name"] for i in range(7)}
    seen = [row["name"] for row in client.iter_list("ToDo", filters=like(marker), page_size=3)]
    assert len(seen) == 7
    assert set(seen) == names


@pytest.mark.parametrize(
    "name",
    [
        "INV/2026/0001",
        "name with spaces",
        "100% & more",
        "question?mark#hash",
        "ünïcödé-名前",
        "a+b=c",
    ],
)
def test_awkward_names_address_the_right_document(client: Client, doctype: str, name: str) -> None:
    created = client.insert(doctype, {"name": name, "title": "awkward"})
    assert created["name"] == name
    try:
        assert client.get_doc(doctype, name)["name"] == name
        assert client.update(doctype, name, {"amount": 5})["amount"] == 5
        assert client.get_count(doctype, {"name": name}) == 1
    finally:
        client.delete(doctype, name)
    with pytest.raises(NotFoundError):
        client.get_doc(doctype, name)


def test_submit_and_cancel(client: Client, doctype: str) -> None:
    client.insert(doctype, {"name": "SUBMIT-1", "title": "to submit"})
    assert client.get_doc(doctype, "SUBMIT-1")["docstatus"] == 0

    client.submit(doctype, "SUBMIT-1")
    assert client.get_doc(doctype, "SUBMIT-1")["docstatus"] == 1

    client.cancel(doctype, "SUBMIT-1")
    assert client.get_doc(doctype, "SUBMIT-1")["docstatus"] == 2
    client.delete(doctype, "SUBMIT-1")


def test_rename(client: Client, doctype: str) -> None:
    client.insert(doctype, {"name": "RENAME-OLD", "title": "rename me"})
    try:
        assert client.rename(doctype, "RENAME-OLD", "RENAME/NEW") == "RENAME/NEW"
        assert client.get_doc(doctype, "RENAME/NEW")["title"] == "rename me"
        with pytest.raises(NotFoundError):
            client.get_doc(doctype, "RENAME-OLD")
    finally:
        client.delete(doctype, "RENAME/NEW")


def test_duplicate_name_is_a_conflict(client: Client, doctype: str) -> None:
    client.insert(doctype, {"name": "DUP-1", "title": "first"})
    try:
        with pytest.raises(ConflictError) as caught:
            client.insert(doctype, {"name": "DUP-1", "title": "second"})
        assert caught.value.status_code == 409
    finally:
        client.delete(doctype, "DUP-1")


def test_missing_mandatory_field_is_a_validation_error(client: Client, doctype: str) -> None:
    with pytest.raises(ValidationError) as caught:
        client.insert(doctype, {"name": "INVALID-1"})
    assert caught.value.status_code == 417
    assert caught.value.exc_type == "MandatoryError"
    assert caught.value.server_messages
    assert "Traceback" not in str(caught.value)


def test_unknown_doctype_is_not_found(client: Client) -> None:
    with pytest.raises(NotFoundError):
        client.get_list("No Such DocType Frappix")
