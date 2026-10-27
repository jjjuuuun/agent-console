"""색인 열기: 호스트 DB 핸들 / 별도 파일 / 메모리."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent_console_logs import LogIndex
from agent_console_logs.sqlite import SqliteLogIndex, create_log_engine
from agent_console_logs.testing import MemoryLogIndex
from agent_console_store import branch_version_table, upgrade

__all__ = ["LogStorage", "open_log_storage"]


@dataclass(frozen=True)
class LogStorage:
    """열린 색인과 그 출처.

    Attributes:
        index: 질의·쓰기에 쓰는 색인.
        kind: ``"host"``(호스트 DB 공유) · ``"file"``(별도 파일) · ``"memory"``(DB 없음).
        path: ``kind == "file"``일 때 파일 경로.
    """

    index: LogIndex
    kind: Literal["host", "file", "memory"]
    path: Path | None = None

    def close(self) -> None:
        """별도 파일 엔진만 닫는다(호스트 DB는 호스트가 닫는다)."""
        if self.kind == "file" and isinstance(self.index, SqliteLogIndex):
            self.index.engine.dispose()


def open_log_storage(
    database: Any | None, *, index_path: str | Path | None = None, branch: Any | None = None
) -> LogStorage:
    """색인을 연다.

    Args:
        database: 호스트 ``DatabaseHandle``(없으면 None). 호스트가 켜진 모듈의 계보 ``logs``를 이미
            올렸다고 본다(모듈 ``start()``는 마이그레이션을 하지 않는다).
        index_path: 있으면 그 SQLite 파일에 같은 계보를 직접 올리고 쓴다(F-9, 호스트 DB와 분리).
        branch: 계보(기본 ``storage.BRANCH``). 테스트에서 바꿀 수 있다.

    Returns:
        ``LogStorage``. ``index_path`` > ``database`` > 메모리 순으로 고른다.
    """
    if branch is None:
        from . import BRANCH

        branch = BRANCH
    if index_path is not None:
        path = Path(index_path)
        engine = create_log_engine(path)
        upgrade(engine, versions=branch.versions, version_table=branch_version_table(branch.name))
        return LogStorage(SqliteLogIndex(engine, owns_engine=True), "file", path)
    if database is not None:
        return LogStorage(SqliteLogIndex(database.engine), "host")
    return LogStorage(MemoryLogIndex(), "memory")
