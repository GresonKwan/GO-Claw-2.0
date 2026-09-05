from __future__ import annotations

import pytest

from qwenpaw.app.routers.deliverables import _range


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("bytes=0-9", (0, 9)),
        ("bytes=5-", (5, 99)),
        ("bytes=-10", (90, 99)),
        ("bytes=90-200", (90, 99)),
    ],
)
def test_single_range_contract(header, expected) -> None:
    assert _range(header, 100) == expected


@pytest.mark.parametrize(
    "header",
    ["bytes=", "bytes=2-1", "bytes=100-", "bytes=0-1,4-5", "items=0-1"],
)
def test_invalid_or_multi_range_is_rejected(header: str) -> None:
    with pytest.raises(ValueError):
        _range(header, 100)
