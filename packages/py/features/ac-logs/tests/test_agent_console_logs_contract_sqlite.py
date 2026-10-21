"""SqliteLogIndex가 색인 계약 테스트 묶음을 통과한다(MemoryLogIndex와 같은 질의 의미)."""

from pathlib import Path

import pytest

from agent_console_logs import LogIndex
from agent_console_logs.sqlite import open_log_index
from agent_console_logs.testing import LogIndexContractTests


class TestSqliteLogIndexFile(LogIndexContractTests):
    @pytest.fixture(autouse=True)
    def _folder(self, tmp_path: Path) -> None:
        self._tmp = tmp_path
        self._n = 0

    def make_index(self) -> LogIndex:
        self._n += 1
        return open_log_index(self._tmp / f"logs{self._n}.sqlite3")


class TestSqliteLogIndexMemory(LogIndexContractTests):
    def make_index(self) -> LogIndex:
        return open_log_index(":memory:")
