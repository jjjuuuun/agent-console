"""처음 쓸 때 만드는 버전 기록소(`LazyVersionRepository`)와 DB 핸들 → 기록소(`versions_for`).

같은 워크스페이스의 정의를 여러 저장소 인스턴스가 나눠 맡을 때(예: 정의 모듈과 프로젝트 모듈) 같은
버전 기록소를 쓰게 하려고 둔다. 조립 때 DB를 열지 않고 처음 기록·조회할 때 연다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Collection, Mapping
from typing import Any

from agent_console_contracts import DefinitionVersion

from .interfaces import VersionRepository
from .memory import InMemoryVersionRepository
from .sqlite import SqliteStorage

_log = logging.getLogger("agent_console_store")


def versions_for(database: Any | None) -> VersionRepository:
    """DB 핸들(``.engine`` 속성) → SQLite 버전 기록소. 핸들이 없으면 메모리(경고 로그).

    Args:
        database: ``engine``(SQLAlchemy 엔진)을 가진 객체 또는 None.
    """
    engine = getattr(database, "engine", None) if database is not None else None
    if engine is None:
        _log.warning("DB 핸들이 없어 정의 버전 기록을 메모리에 둡니다(재시작하면 사라짐)")
        return InMemoryVersionRepository()
    return SqliteStorage(engine).versions


class LazyVersionRepository:
    """처음 쓸 때 ``factory()``로 실제 기록소를 만드는 ``VersionRepository``(스레드 안전).

    >>> repo = LazyVersionRepository(InMemoryVersionRepository)
    >>> repo.list("agent", "a")
    []
    """

    def __init__(self, factory: Callable[[], VersionRepository]) -> None:
        self._factory = factory
        self._inner: VersionRepository | None = None
        self._lock = threading.Lock()

    @property
    def inner(self) -> VersionRepository:
        """실제 기록소(없으면 지금 만든다)."""
        if self._inner is None:
            with self._lock:
                if self._inner is None:
                    self._inner = self._factory()
        return self._inner

    def record(
        self,
        kind: str,
        id: str,
        version_hash: str,
        content: Mapping[str, Any],
        *,
        saved_at: float,
        message: str = "",
        files: Mapping[str, bytes] | None = None,
    ) -> None:
        self.inner.record(
            kind, id, version_hash, content, saved_at=saved_at, message=message, files=files
        )

    def saved_at(self, kind: str, id: str, version_hash: str) -> float | None:
        return self.inner.saved_at(kind, id, version_hash)

    def list(self, kind: str, id: str) -> list[DefinitionVersion]:
        return self.inner.list(kind, id)

    def get(self, kind: str, id: str, version_hash: str) -> DefinitionVersion | None:
        return self.inner.get(kind, id, version_hash)

    def files(self, kind: str, id: str, version_hash: str) -> dict[str, str] | None:
        return self.inner.files(kind, id, version_hash)

    def blob_size(self, sha256: str) -> int | None:
        return self.inner.blob_size(sha256)

    def read_blob(self, sha256: str) -> bytes | None:
        return self.inner.read_blob(sha256)

    def trim(self, kind: str, id: str, *, keep: int, protect: Collection[str] = ()) -> int:
        return self.inner.trim(kind, id, keep=keep, protect=protect)

    def prune_blobs(self) -> int:
        return self.inner.prune_blobs()


__all__ = ["LazyVersionRepository", "versions_for"]
