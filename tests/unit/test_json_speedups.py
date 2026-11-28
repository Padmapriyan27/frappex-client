"""The optional orjson decoder must give exactly the standard library's results."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from frappex_client import _protocol

pytestmark = pytest.mark.skipif(_protocol._orjson is None, reason="orjson is not installed")

JSON_VALUES = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.integers(min_value=-(10**30), max_value=10**30)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda inner: st.lists(inner, max_size=5) | st.dictionaries(st.text(), inner, max_size=5),
    max_leaves=40,
)


def stdlib_only(body: bytes | str, monkeypatch: pytest.MonkeyPatch) -> Any:
    with monkeypatch.context() as patch:
        patch.setattr(_protocol, "_orjson", None)
        return _protocol._load_json(body)


def same(a: Any, b: Any) -> bool:
    """Compare decoded values exactly, iteratively (no recursion limit), NaN equal to NaN."""
    pending = [(a, b)]
    while pending:
        x, y = pending.pop()
        if type(x) is not type(y):
            return False
        if isinstance(x, list):
            if len(x) != len(y):
                return False
            pending.extend(zip(x, y, strict=True))
        elif isinstance(x, dict):
            if list(x) != list(y):
                return False
            pending.extend((x[key], y[key]) for key in x)
        elif isinstance(x, float) and math.isnan(x):
            if not math.isnan(y):
                return False
        elif x != y:
            return False
    return True


@settings(max_examples=300, deadline=None)
@given(value=JSON_VALUES)
def test_valid_json_decodes_identically(value: Any) -> None:
    body = json.dumps({"data": value}).encode()
    assert _protocol._load_json(body) == json.loads(body)


@settings(max_examples=500, deadline=None)
@given(body=st.binary(max_size=200) | st.text(max_size=200).map(str.encode))
def test_arbitrary_bytes_give_the_same_result(body: bytes) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        expected = stdlib_only(body, monkeypatch)
    assert same(_protocol._load_json(body), expected)


@pytest.mark.parametrize(
    "body",
    [
        b'{"message": "\\ud800"}',  # lone surrogate: orjson refuses, json accepts
        b'{"n": NaN, "m": Infinity}',  # not JSON, but json accepts it
        b"[" * 5000 + b"]" * 5000,  # deeper than orjson allows
        b'{"n": 123456789012345678901234567890}',  # orjson would round it
        b"[18446744073709551616, -9223372036854775809]",  # just past 64 bits
        b'{"phone": "12345678901234567890123"}',  # long digits in a string
        b"\xff\xfe not json",
        b"",
    ],
)
def test_inputs_orjson_handles_differently(body: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    assert same(_protocol._load_json(body), stdlib_only(body, monkeypatch))
