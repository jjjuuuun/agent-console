"""공용 재료: 색인 둘(메모리·SQLite)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_console_logs import LogIndex
from agent_console_logs.sqlite import open_log_index
from agent_console_logs.testing import MemoryLogIndex


@pytest.fixture(params=["memory", "sqlite"])
def index(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[LogIndex]:
    if request.param == "memory":
        yield MemoryLogIndex()
        return
    found = open_log_index(tmp_path / "logs.sqlite3")
    try:
        yield found
    finally:
        found.close()
