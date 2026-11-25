"""``numbered_id``: 겹치면 ``-2``부터 빈 번호, 자르기·상한."""

from __future__ import annotations

import pytest

from agent_console_numbered_id import NoFreeId, numbered_id


def test_free_base_is_returned_unchanged_even_if_too_long() -> None:
    assert numbered_id("abcdef", lambda _c: False, max_length=3) == "abcdef"


def test_first_free_number_from_two() -> None:
    taken = {"a", "a-2", "a-3"}
    assert numbered_id("a", taken.__contains__) == "a-4"
    assert numbered_id("a-2", taken.__contains__) == "a-2-2"


def test_truncates_head_to_fit_max_length() -> None:
    base = "x" * 128
    found = numbered_id(base, {base}.__contains__, max_length=128)
    assert found == "x" * 126 + "-2"
    assert len(found) == 128


def test_comparison_is_callers_choice() -> None:
    folded = {"app"}
    assert numbered_id("APP", lambda c: c.casefold() in folded) == "APP-2"
    assert numbered_id("APP", folded.__contains__) == "APP"


def test_limit_raises_lookup_error() -> None:
    with pytest.raises(NoFreeId) as caught:
        numbered_id("a", lambda _c: True, limit=5)
    assert isinstance(caught.value, LookupError)
    seen: list[str] = []

    def taken(name: str) -> bool:
        seen.append(name)
        return True

    with pytest.raises(NoFreeId):
        numbered_id("a", taken, limit=4)
    assert seen == ["a", "a-2", "a-3"]
