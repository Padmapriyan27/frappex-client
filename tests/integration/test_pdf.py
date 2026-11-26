"""Print-format PDFs against a real site.

Frappe renders PDFs with wkhtmltopdf, which CI installs on the runner.
"""

from __future__ import annotations

import asyncio
import io

import pytest

from frappex_client import AsyncClient, Client, NotFoundError

from .conftest import OPTIONS, URL, token_auth


def test_download_pdf(client: Client, marker: str) -> None:
    name = client.insert("ToDo", {"description": f"{marker} print me"})["name"]

    pdf = client.download_pdf("ToDo", name, no_letterhead=True)

    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")


def test_download_pdf_to_a_file(client: Client, marker: str) -> None:
    name = client.insert("ToDo", {"description": f"{marker} print me"})["name"]
    target = io.BytesIO()

    written = client.download_pdf_to("ToDo", name, target, print_format="Standard")

    assert written == len(target.getvalue()) > 0
    assert target.getvalue().startswith(b"%PDF-")


def test_missing_document(client: Client, marker: str) -> None:
    with pytest.raises(NotFoundError):
        client.download_pdf("ToDo", f"{marker}-missing")


def test_async_download_pdf(marker: str) -> None:
    async def scenario() -> None:
        async with AsyncClient(URL, token_auth(), **OPTIONS) as live:
            created = await live.insert("ToDo", {"description": f"{marker} async print"})
            pdf = await live.download_pdf("ToDo", created["name"])
            assert pdf.startswith(b"%PDF-")

    asyncio.run(scenario())
