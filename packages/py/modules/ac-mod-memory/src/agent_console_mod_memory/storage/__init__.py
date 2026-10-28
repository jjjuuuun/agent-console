"""mod-memory의 저장 계층: 마이그레이션 계보 ``memory``와 저장소 열기(design §5.7R.6).

- ``BRANCH``: 이 모듈의 마이그레이션 계보(``memory``, 패키지 데이터 ``migrations/versions``).
  버전 테이블은 ``alembic_version_memory``. 모듈이 켜질 때만 호스트가 올린다(build 직전).
  ``MODULE_OWNED_TABLES``에는 넣지 않는다(F-2): 표는 처음부터 이 계보가 만든다.
- ``open_memory_storage``: 별도 파일(``store_path``) > 호스트 DB 파일 > 메모리 순으로 저장소를 연다.

표 정의와 저장소 구현은 ``agent_console_memory.sqlite``에 있다(이 계보는 그 표 정의와 같은 모양을
지킨다 — 테스트가 ``compare_metadata``로 확인).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from agent_console_contracts import Issue
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_memory import InMemoryMemoryStore, MemoryPolicy, MemoryStore
from agent_console_memory.sqlite import SqliteMemoryStore, open_sqlite_memory_store
from agent_console_modkit import MigrationBranch
from agent_console_store import branch_version_table, create_sqlite_engine, upgrade

BRANCH = MigrationBranch("memory", Path(__file__).parent / "migrations" / "versions")
"""모듈 서술자 ``migrations``에 넣는 계보."""

StorageKind = Literal["host", "file", "memory"]


@dataclass
class MemoryStorage:
    """열린 저장소와 그 출처.

    Attributes:
        store: 메모리 저장소(``MemoryStore``).
        kind: ``"host"``(호스트 DB 파일 공유) · ``"file"``(별도 파일) · ``"memory"``(DB 없음).
        path: SQLite 파일 경로(``memory``면 None).
    """

    store: MemoryStore
    kind: StorageKind
    path: Path | None = None
    _closed: bool = field(default=False, repr=False)

    def warnings(self) -> list[Issue]:
        """서버 경고.

        메모리 저장(``memory.storage_memory``), 전문 검색 폴백(``memory.search_fallback``).
        """
        out: list[Issue] = []
        if self.kind == "memory":
            out.append(storage_memory_warning())
        if isinstance(self.store, SqliteMemoryStore):
            out.extend(self.store.warnings())
        return out

    def close(self) -> None:
        """SQLite 저장소의 자기 엔진을 닫는다(호스트 DB 핸들은 호스트가 닫는다)."""
        if not self._closed and isinstance(self.store, SqliteMemoryStore):
            self.store.close()
        self._closed = True


def storage_memory_warning() -> Issue:
    """DB가 없어 메모리를 프로세스 메모리에만 둔다는 경고."""
    return Issue(
        severity="warning",
        code=KnownIssueCodes.MEMORY_STORAGE_MEMORY,
        message="DB가 없어 메모리 기록을 프로세스 메모리에만 둡니다(재시작하면 사라집니다)",
    )


def host_database_file(database: Any | None) -> Path | None:
    """호스트 DB 핸들이 가리키는 SQLite 파일(없거나 메모리 DB면 None)."""
    if database is None:
        return None
    engine = getattr(database, "engine", None)
    url = getattr(engine, "url", None)
    if url is None or not str(getattr(url, "drivername", "")).startswith("sqlite"):
        return None
    name = getattr(url, "database", None)
    if not name or name == ":memory:" or str(name).startswith("file::memory:"):
        return None
    return Path(str(name))


def _migrate_file(path: Path, branch: MigrationBranch) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(path)
    try:
        upgrade(engine, versions=branch.versions, version_table=branch_version_table(branch.name))
    finally:
        engine.dispose()


def open_memory_storage(
    database: Any | None,
    *,
    store_path: str | Path | None = None,
    policy: MemoryPolicy | None = None,
    use_fts: bool = True,
    busy_timeout_seconds: float = 10.0,
    clock: Callable[[], float] = time.time,
    branch: MigrationBranch | None = None,
) -> MemoryStorage:
    """저장소를 연다.

    Args:
        database: 호스트 ``DatabaseHandle``(없으면 None). 호스트가 켜진 모듈의 계보 ``memory``를
            이미 올렸다고 본다. 저장소는 그 파일에 자기 엔진으로 붙는다(전문 검색 가상 표는 열 때
            만든다).
        store_path: 있으면 그 SQLite 파일에 같은 계보를 직접 올리고 쓴다(호스트 DB와 분리).
        policy: 쓰기 정책(설정이 바뀌면 저장소 ``policy``를 바꿔 끼운다).
        use_fts: False면 전문 검색을 쓰지 않는다(포함 검색, 경고).
        busy_timeout_seconds: 쓰기 잠금 대기 시간.
        clock: 시각(Unix epoch 초).
        branch: 계보(기본 ``BRANCH``, 테스트에서 바꿀 수 있다).

    Returns:
        ``MemoryStorage``. ``store_path`` > 호스트 DB 파일 > 메모리 순으로 고른다.
    """
    chosen = branch if branch is not None else BRANCH
    fts: bool | None = None if use_fts else False
    if store_path is not None:
        path = Path(store_path).expanduser()
        _migrate_file(path, chosen)
        store = open_sqlite_memory_store(
            path,
            policy=policy,
            clock=clock,
            use_fts=fts,
            busy_timeout_seconds=busy_timeout_seconds,
        )
        return MemoryStorage(store, "file", path)
    host = host_database_file(database)
    if host is not None:
        store = open_sqlite_memory_store(
            host,
            policy=policy,
            clock=clock,
            use_fts=fts,
            busy_timeout_seconds=busy_timeout_seconds,
        )
        return MemoryStorage(store, "host", host)
    return MemoryStorage(InMemoryMemoryStore(policy=policy, clock=clock), "memory")


__all__ = [
    "BRANCH",
    "MemoryStorage",
    "StorageKind",
    "host_database_file",
    "open_memory_storage",
    "storage_memory_warning",
]
