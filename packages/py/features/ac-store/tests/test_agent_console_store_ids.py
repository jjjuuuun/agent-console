"""이름 → 정의 id(`slug_id`·`unique_id`) — 위키·SDD가 함께 쓰는 규칙."""

import re

import pytest

from agent_console_store import SLUG_MAX_CHARS, slug_id, unique_id

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Project Notes", "project-notes"),
        ("  --Hello__World--  ", "hello__world"),
        ("Crème brûlée", "creme-brulee"),
        ("a/b\\c.d", "a-b-c-d"),
        ("프로젝트 노트", "fb"),
        ("", "fb"),
        ("___", "fb"),
    ],
)
def test_slug_id(name: str, expected: str) -> None:
    assert slug_id(name, fallback="fb") == expected


def test_long_name_leaves_room_for_suffix() -> None:
    base = slug_id("x" * 300, fallback="fb")
    assert len(base) == SLUG_MAX_CHARS
    taken = [base, *(f"{base}-{n}" for n in range(2, 12))]
    got = unique_id("x" * 300, taken, fallback="fb")
    assert got == f"{base}-12"
    assert _ID.fullmatch(got)


def test_cut_does_not_end_with_dash() -> None:
    name = "a" * (SLUG_MAX_CHARS - 1) + " b"
    assert slug_id(name, fallback="fb") == "a" * (SLUG_MAX_CHARS - 1)


def test_unique_id_case_insensitive() -> None:
    assert unique_id("Notes", ["NOTES"], fallback="fb") == "notes-2"
    assert unique_id("Notes", ["notes", "Notes-2"], fallback="fb") == "notes-3"
    assert unique_id("Notes", [], fallback="fb") == "notes"


def test_fallback_is_also_deduplicated() -> None:
    assert unique_id("노트", ["wiki"], fallback="wiki") == "wiki-2"
