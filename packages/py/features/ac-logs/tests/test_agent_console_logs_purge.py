"""색인 비우기(M-3): 메모리·SQLite 구현이 같은 의미를 지킨다(`testing.PurgeContractTests`)."""

import sqlite3
from pathlib import Path

import pytest

from agent_console_logs import LogIndex, PurgeResult, purge_index, reset_index
from agent_console_logs.sqlite import open_existing_log_index, open_log_index
from agent_console_logs.testing import MemoryLogIndex, PurgeContractTests


class TestMemoryPurge(PurgeContractTests):
    def make_index(self) -> LogIndex:
        return MemoryLogIndex()


class TestSqlitePurgeMemory(PurgeContractTests):
    def make_index(self) -> LogIndex:
        return open_log_index(":memory:")


class TestSqlitePurgeFile(PurgeContractTests):
    @pytest.fixture(autouse=True)
    def _folder(self, tmp_path: Path) -> None:
        self._tmp = tmp_path
        self._n = 0

    def make_index(self) -> LogIndex:
        self._n += 1
        return open_log_index(self._tmp / f"logs{self._n}.sqlite3")


def test_rejects_index_without_purge() -> None:
    with pytest.raises(TypeError, match="purge"):
        purge_index(object())
    with pytest.raises(TypeError, match="purge"):
        reset_index(object(), dry_run=True)


def test_empty_index() -> None:
    assert reset_index(MemoryLogIndex()) == PurgeResult(dry_run=False)


def test_open_existing_does_not_create(tmp_path: Path) -> None:
    missing = tmp_path / "none.sqlite3"
    with pytest.raises(FileNotFoundError):
        open_existing_log_index(missing)
    assert not missing.exists()
    other = tmp_path / "other.sqlite3"
    sqlite3.connect(other).close()
    with pytest.raises(LookupError, match="log_events"):
        open_existing_log_index(other)
    made = tmp_path / "idx.sqlite3"
    open_log_index(made).close()
    index = open_existing_log_index(made)
    try:
        assert purge_index(index, dry_run=True) == PurgeResult(dry_run=True)
    finally:
        index.close()
