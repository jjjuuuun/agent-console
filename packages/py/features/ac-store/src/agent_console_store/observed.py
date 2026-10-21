"""버전 기록 알림: 버전 기록소를 감싸 기록마다 콜백을 부른다(저장 알림, design §3R.1.5).

정의 저장소는 저장(만들기·덮어쓰기·본문 쓰기·되돌리기)마다 버전 기록소의 ``record``를 부른다.
그래서 이 감싸개를 저장소의 ``versions``로 넘기면 저장소 코드를 고치지 않고 "정의 저장됨"
알림(서버의 모듈 이벤트 ``definitions.saved`` 등)을 낼 수 있다. 콜백 예외는 저장을 되돌리지 않는다
(기록이 끝난 뒤에 부르고, 예외는 그대로 올라간다 — 호출자가 격리한다).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from typing import Any

from agent_console_contracts import DefinitionVersion

from .interfaces import VersionRepository

type VersionRecorded = Callable[[str, str, str], None]
"""``(kind, id, version_hash)``: 버전 하나가 기록됐다."""


class ObservedVersionRepository:
    """``VersionRepository`` 감싸개. ``record`` 뒤에 ``on_record(kind, id, version_hash)``.

    Args:
        inner: 실제 버전 기록소(SQLite·메모리).
        on_record: 기록 뒤에 부를 함수. 버전 정리(``trim``)에는 부르지 않는다.
    """

    def __init__(self, inner: VersionRepository, on_record: VersionRecorded) -> None:
        self.inner = inner
        self._on_record = on_record

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
        self._on_record(kind, id, version_hash)

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


__all__ = ["ObservedVersionRepository", "VersionRecorded"]
