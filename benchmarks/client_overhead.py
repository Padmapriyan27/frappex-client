"""Measure the time frappex-client itself adds to each call.

The network is replaced by an in-memory site that answers instantly, so the
numbers are the library's own work: building the request, sending it
through httpx, reading and decoding the reply. Run:

    uv run python benchmarks/client_overhead.py [--no-speedups]

``--no-speedups`` decodes with the json module even when orjson is
installed, to compare the two.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from collections.abc import Callable
from typing import Any

import httpx

from frappex_client import AsyncClient, Client, TokenAuth, _protocol

URL = "https://erp.example.com"
DOC = {"name": "SINV-0001", **{f"field_{i}": f"value {i}" * 3 for i in range(40)}}
PAGE = [
    dict(DOC, name=f"SINV-{i:04d}", creation=f"2026-11-28 10:{i // 60:02d}:{i % 60:02d}")
    for i in range(100)
]
DOC_BODY = json.dumps({"data": DOC}).encode()
PAGE_BODY = json.dumps({"data": PAGE}).encode()
SMALL_PAGE_BODY = json.dumps({"data": PAGE[:37]}).encode()
JSON = {"content-type": "application/json"}


def handler(request: httpx.Request) -> httpx.Response:
    """Answer like a Frappe site, instantly."""
    path = request.url.path
    if path == "/api/resource/Sales Invoice":
        if request.method == "POST":
            return httpx.Response(200, content=DOC_BODY, headers=JSON)
        # The second page of an iteration is short, so iter_list stops.
        body = SMALL_PAGE_BODY if "creation" in request.url.params.get("filters", "") else PAGE_BODY
        return httpx.Response(200, content=body, headers=JSON)
    return httpx.Response(200, content=DOC_BODY, headers=JSON)


def measure(name: str, call: Callable[[], Any], repeat: int, rounds: int = 7) -> float:
    """Print and return the best per-call time, in microseconds."""
    call()
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        for _ in range(repeat):
            call()
        samples.append((time.perf_counter() - start) / repeat * 1e6)
    best = min(samples)
    print(f"{name:42} {best:8.1f} µs  (median {statistics.median(samples):7.1f})")
    return best


def main() -> None:
    """Run every measurement."""
    if "--no-speedups" in sys.argv:
        _protocol._orjson = None
    print(f"JSON decoder: {'orjson' if _protocol._orjson else 'json (standard library)'}")
    transport = httpx.MockTransport(handler)
    values = {f"field_{i}": f"value {i}" for i in range(40)}
    with Client(URL, TokenAuth("key", "secret"), transport=transport) as client:
        measure(
            "sync  get_doc (41 fields)", lambda: client.get_doc("Sales Invoice", "SINV-0001"), 2000
        )
        measure(
            "sync  get_list (100 rows)", lambda: client.get_list("Sales Invoice", limit=100), 500
        )
        measure(
            "sync  iter_list (137 rows, 2 pages)",
            lambda: sum(1 for _ in client.iter_list("Sales Invoice", fields=["*"])),
            300,
        )
        measure("sync  insert (40 fields)", lambda: client.insert("Sales Invoice", values), 2000)

    async def run_async() -> None:
        async with AsyncClient(URL, TokenAuth("key", "secret"), transport=transport) as client:
            loop_time: list[float] = []

            async def many(n: int) -> None:
                for _ in range(n):
                    await client.get_doc("Sales Invoice", "SINV-0001")

            await many(50)
            for _ in range(7):
                start = time.perf_counter()
                await many(2000)
                loop_time.append((time.perf_counter() - start) / 2000 * 1e6)
            best, median = min(loop_time), statistics.median(loop_time)
            print(f"{'async get_doc (41 fields)':42} {best:8.1f} µs  (median {median:7.1f})")

    asyncio.run(run_async())


if __name__ == "__main__":
    main()
