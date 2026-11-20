"""5.7R.33n: 열린 공간 캐시는 연 뒤 구성 폴더의 쓰기 가능 여부가 바뀌면 다시 연다.

``config_writable``이 지금 상태를 따르고(복사·위키·SDD의 쓰기 전 검사가 409로 거른다), 다시 열어도
버전 기록은 이어진다.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from agent_console_mod_projects import ProjectSpaceCache


def _cache(folder: Path) -> ProjectSpaceCache:
    return ProjectSpaceCache(lambda _id: str(folder), options=dict)


def _set_writable(folder: Path, writable: bool) -> None:
    for d in (folder, *folder.rglob("*")):
        if d.is_dir():
            mode = d.stat().st_mode
            d.chmod(mode | stat.S_IWUSR if writable else mode & ~stat.S_IWUSR)


def test_cache_returns_same_space_while_writability_is_unchanged(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    assert cache.open("p") is cache.open("p")


@pytest.mark.skipif(os.geteuid() == 0, reason="root는 쓰기 권한 검사를 통과한다")
def test_cache_reopens_when_writability_changes_and_keeps_versions(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    first = cache.open("p")
    assert first.config_writable
    first.definitions.create("agent", {"kind": "agent", "id": "a1", "name": "하나"})
    try:
        _set_writable(tmp_path, False)
        locked = cache.open("p")
        assert locked is not first
        assert not locked.config_writable
        assert cache.open("p") is locked
    finally:
        _set_writable(tmp_path, True)
    again = cache.open("p")
    assert again.config_writable
    current = again.definitions.get("agent", "a1")
    again.definitions.save(
        "agent",
        {"kind": "agent", "id": "a1", "name": "둘"},
        expected_version=current.version_hash,
    )
    assert len(again.definitions.list_versions("agent", "a1")) == 2
