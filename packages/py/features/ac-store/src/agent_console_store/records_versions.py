"""기록 DB 위의 정의 버전 기록소(`RecordsVersionRepository`, design §PI.4.2·§PI.4.6.1).

프로젝트 사본의 버전은 그 폴더의 기록 DB(`records.sqlite3`)의 `definition_versions`·`content_blobs`
(legacy 표)에 남는다. 이 기록소는 `RecordsHandle`(기록 DB 핸들)을 **부를 때마다** 받아(핸들을 오래
들지 않는다) 읽기는 `read_engine()`(파일이 없으면 빈 결과), 쓰기는 `writable_engine()`(처음 쓸 때
파일을 만들고 계보를 올림, 못 쓰면 `RecordsUnavailable` 409)으로 한다.

`ensure_writable()`(`VersionWriteCheck`)은 정의 파일을 쓰기 **전에** 기록 DB를 쓸 수 있는지
확인한다. 버전이 갈 곳이 없는데 정의 파일만 바뀌는 일을 막으려고 저장소의 쓰기 전 검사
(`WriteGuard`)가 부른다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from typing import Any, Protocol

from sqlalchemy import Engine

from agent_console_contracts import DefinitionVersion

from .sqlite import SqliteVersionRepository


class RecordsEngines(Protocol):
    """버전 기록소가 쓰는 기록 DB 부분(`RecordsHandle`·`RecordsDb`가 만족)."""

    def read_engine(self) -> Engine | None:
        """읽기용 엔진. 파일이 없으면 None."""
        ...

    def writable_engine(self) -> Engine:
        """쓰기용 엔진(없으면 만들고 계보를 올린다). 못 쓰면 `RecordsUnavailable`."""
        ...


class RecordsVersionRepository:
    """`VersionRepository` + `VersionWriteCheck`: 기록 DB 핸들의 legacy 버전 표.

    Args:
        handle: 지금 기록 DB 핸들(`RecordsHandle`·`RecordsDb`, 부를 때마다 — 공간 캐시가 핸들을
            바꿔도 따라간다).
    """

    def __init__(self, handle: Callable[[], RecordsEngines]) -> None:
        self._handle = handle

    def _reader(self) -> SqliteVersionRepository | None:
        engine = self._handle().read_engine()
        return None if engine is None else SqliteVersionRepository(engine)

    def _writer(self) -> SqliteVersionRepository:
        return SqliteVersionRepository(self._handle().writable_engine())

    def ensure_writable(self) -> None:
        """기록 DB를 쓸 수 있게 연다(없으면 만들고 계보를 올린다). 못 쓰면 `RecordsUnavailable`."""
        self._handle().writable_engine()

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
        self._writer().record(
            kind, id, version_hash, content, saved_at=saved_at, message=message, files=files
        )

    def saved_at(self, kind: str, id: str, version_hash: str) -> float | None:
        reader = self._reader()
        return None if reader is None else reader.saved_at(kind, id, version_hash)

    def list(self, kind: str, id: str) -> list[DefinitionVersion]:
        reader = self._reader()
        return [] if reader is None else reader.list(kind, id)

    def get(self, kind: str, id: str, version_hash: str) -> DefinitionVersion | None:
        reader = self._reader()
        return None if reader is None else reader.get(kind, id, version_hash)

    def files(self, kind: str, id: str, version_hash: str) -> dict[str, str] | None:
        reader = self._reader()
        return None if reader is None else reader.files(kind, id, version_hash)

    def blob_size(self, sha256: str) -> int | None:
        reader = self._reader()
        return None if reader is None else reader.blob_size(sha256)

    def read_blob(self, sha256: str) -> bytes | None:
        reader = self._reader()
        return None if reader is None else reader.read_blob(sha256)

    def trim(self, kind: str, id: str, *, keep: int, protect: Collection[str] = ()) -> int:
        """보존 개수 정리. 기록 DB가 아직 없으면 0(파일을 만들지 않는다)."""
        if self._handle().read_engine() is None:
            return 0
        return self._writer().trim(kind, id, keep=keep, protect=protect)

    def prune_blobs(self) -> int:
        """쓰지 않는 blob 정리. 기록 DB가 아직 없으면 0."""
        if self._handle().read_engine() is None:
            return 0
        return self._writer().prune_blobs()


__all__ = ["RecordsEngines", "RecordsVersionRepository"]
