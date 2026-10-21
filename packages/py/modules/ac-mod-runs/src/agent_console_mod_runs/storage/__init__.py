"""실행 기록 저장소 고르기와 마이그레이션 계보(design §3R.1.7·§5R.10).

``runs``·``node_runs``·``run_events``·``interactions``는 legacy(0001~0003)가 만들었고, 소유는 이
모듈의 계보 ``runs``(``BRANCH``, 버전 테이블 ``alembic_version_runs``)다. 저장소 구현 코드는
``agent_console_store``에 그대로 있다. 계보: ``runs_0001`` = 빈 기준점, ``runs_0002`` = 계보 새 열.
모듈이 꺼지면 계보를 올리지 않는다.

호스트 DB 핸들(``BaseServices.database``)이 있으면 그 엔진 위의 SQLite 저장소를, 없으면 메모리
저장소를 쓴다(재시작하면 기록이 사라진다 — ``runs.storage_memory`` 경고).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import Issue
from agent_console_modkit import DatabaseHandle, MigrationBranch
from agent_console_store import InMemoryStorage, SqliteStorage

BRANCH = MigrationBranch("runs", Path(__file__).parent / "migrations" / "versions")
"""모듈 서술자 ``migrations``에 넣는 계보."""

STORAGE_MEMORY = "runs.storage_memory"
"""경고 코드: DB가 없어 실행 기록을 메모리에만 둔다."""


def open_recorder(database: DatabaseHandle | None) -> tuple[Any, bool]:
    """(저장 묶음 ``runs``·``events``·``interactions``, 메모리인지)."""
    if database is None:
        return InMemoryStorage(), True
    return SqliteStorage(database.engine), False


def memory_storage_warning() -> Issue:
    return Issue(
        severity="warning",
        code=STORAGE_MEMORY,
        message="DB가 없어 실행 기록을 메모리에만 둡니다(재시작하면 사라집니다)",
    )


__all__ = ["BRANCH", "STORAGE_MEMORY", "memory_storage_warning", "open_recorder"]
