"""이름 → 정의 id(`slug_id`·`unique_id`) — 위키·SDD가 함께 쓰는 규칙."""

import re
from pathlib import Path

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


def test_numbered_rule_is_the_shared_one() -> None:
    """번호 붙이기는 `agent_console_numbered_id` 하나를 다시 내보낸 것이다(사본 없음)."""
    import agent_console_numbered_id
    from agent_console_store import NoFreeId, numbered_id
    from agent_console_store.ids import numbered_id as from_ids

    assert numbered_id is agent_console_numbered_id.numbered_id is from_ids
    assert NoFreeId is agent_console_numbered_id.NoFreeId


def test_backup_names_get_numbers_when_same_second(tmp_path: Path) -> None:
    """같은 초에 두 번 백업하면 두 번째 이름에 `-2`가 붙는다(번호 규칙 공용)."""
    from agent_console_store import open_records_db

    path = tmp_path / "records.sqlite3"
    db = open_records_db(path, backup_dir=tmp_path / "bk", clock=lambda: 0.0)
    db.writable_engine()
    db.close()
    first = open_records_db(path, backup_dir=tmp_path / "bk", clock=lambda: 0.0)
    made = [first._backup({"legacy": "0001"}), first._backup({"legacy": "0001"})]
    first.close()
    assert made[0].name.endswith(".sqlite3")
    assert made[1].name == made[0].name.removesuffix(".sqlite3") + "-2.sqlite3"
