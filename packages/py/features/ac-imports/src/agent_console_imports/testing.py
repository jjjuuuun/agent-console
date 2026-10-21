"""테스트·예제 도우미(공개, 운영 코드에서 쓰지 않는다).

- `MemoryDefinitionWriter`: `DefinitionWriter`의 메모리 구현. 정의 저장소(`ac-store`) 없이
  `ImportService`를 돌려 볼 때 쓴다. 버전은 쓸 때마다 `v1`, `v2`…로 바뀌고, 기대 버전이 다르면
  `ValueError`, 없는 정의는 `KeyError`를 낸다(가져오기는 예외 타입 이름만 결과에 남긴다).
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryStored:
    """저장 결과(`StoredLike`)."""

    version_hash: str


@dataclass(frozen=True, slots=True)
class MemoryFile:
    """여러 파일 본문의 파일 하나(`FileLike`)."""

    path: str


@dataclass
class MemoryDefinitionWriter:
    """`DefinitionWriter` 메모리 구현.

    Attributes:
        documents: ``(kind, id)`` → 마지막으로 쓴 문서.
        contents: ``(kind, id)`` → 한 파일 본문.
        files: ``(kind, id)`` → 여러 파일 본문(경로 → 내용).
        messages: 쓴 순서대로 ``(kind, id, message)``.
    """

    documents: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    contents: dict[tuple[str, str], bytes] = field(default_factory=dict)
    files: dict[tuple[str, str], dict[str, bytes]] = field(default_factory=dict)
    messages: builtins.list[tuple[str, str, str]] = field(default_factory=list)
    _versions: dict[tuple[str, str], int] = field(default_factory=dict, repr=False)

    def _bump(self, kind: str, id: str, message: str) -> MemoryStored:
        n = self._versions.get((kind, id), 0) + 1
        self._versions[(kind, id)] = n
        self.messages.append((kind, id, message))
        return MemoryStored(f"v{n}")

    def _check(self, kind: str, id: str, expected_version: str | None) -> None:
        if (kind, id) not in self.documents:
            raise KeyError(f"{kind}/{id}")
        if expected_version is not None and expected_version != self.get(kind, id).version_hash:
            raise ValueError(f"버전이 다릅니다: {kind}/{id}")

    def list_ids(self, kind: str) -> builtins.list[str]:
        """종류의 id 목록(오름차순)."""
        return sorted(i for k, i in self.documents if k == kind)

    def get(self, kind: str, id: str) -> MemoryStored:
        """지금 버전. 없으면 `KeyError`."""
        if (kind, id) not in self.documents:
            raise KeyError(f"{kind}/{id}")
        return MemoryStored(f"v{self._versions[(kind, id)]}")

    def create(self, kind: str, document: Mapping[str, Any], *, message: str = "") -> MemoryStored:
        """새 정의. 같은 id가 있으면 `ValueError`."""
        id = str(document["id"])
        if (kind, id) in self.documents:
            raise ValueError(f"이미 있습니다: {kind}/{id}")
        self.documents[(kind, id)] = dict(document)
        return self._bump(kind, id, message)

    def save(
        self,
        kind: str,
        document: Mapping[str, Any],
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> MemoryStored:
        """있는 정의를 덮어쓴다(기대 버전 검사)."""
        id = str(document["id"])
        self._check(kind, id, expected_version)
        self.documents[(kind, id)] = dict(document)
        return self._bump(kind, id, message)

    def write_content(
        self,
        kind: str,
        id: str,
        data: bytes,
        *,
        file: str | None = None,
        media_type: str | None = None,
        expected_version: str | None = None,
        message: str = "본문 수정",
    ) -> MemoryStored:
        """한 파일 본문을 쓴다(`file`·`media_type`은 기록하지 않는다)."""
        self._check(kind, id, expected_version)
        self.contents[(kind, id)] = bytes(data)
        return self._bump(kind, id, message)

    def list_files(self, kind: str, id: str) -> builtins.list[MemoryFile]:
        """여러 파일 본문의 경로 목록(오름차순)."""
        return [MemoryFile(p) for p in sorted(self.files.get((kind, id), {}))]

    def write_files(
        self,
        kind: str,
        id: str,
        changes: Mapping[str, bytes | None],
        *,
        expected_version: str | None = None,
        message: str = "파일 수정",
    ) -> MemoryStored:
        """여러 파일 본문을 한 버전으로 바꾼다(값이 None이면 지운다)."""
        self._check(kind, id, expected_version)
        current = self.files.setdefault((kind, id), {})
        for path, data in changes.items():
            if data is None:
                current.pop(path, None)
            else:
                current[path] = bytes(data)
        return self._bump(kind, id, message)


__all__ = ["MemoryDefinitionWriter", "MemoryFile", "MemoryStored"]
