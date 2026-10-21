"""테스트·예제 도우미(공개, 운영 코드에서 쓰지 않는다).

- `MemoryCatalog`: `ExportCatalog`의 메모리 구현. 정의 저장소 없이 `ExportService`·형식을
  돌려 볼 때 쓴다.
- `MemoryDependency`: `DependencyLike` 값 객체.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryDependency:
    """함께 쓰이는 정의 하나(`DependencyLike`)."""

    kind: str
    id: str
    node_id: str | None = None
    shared: bool = False
    mode: str = "add"
    config_override: Mapping[str, Any] | None = None


@dataclass
class MemoryCatalog:
    """`ExportCatalog` 메모리 구현.

    Attributes:
        documents: ``(kind, id)`` → 정의 원문.
        bodies: ``(kind, id)`` → 본문 파일(경로 → 내용).
        deps: ``(kind, id)`` → 이 정의가 쓰는 정의.
    """

    documents: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    bodies: dict[tuple[str, str], dict[str, bytes]] = field(default_factory=dict)
    deps: dict[tuple[str, str], list[MemoryDependency]] = field(default_factory=dict)

    def add(
        self,
        kind: str,
        document: Mapping[str, Any],
        *,
        files: Mapping[str, bytes] | None = None,
        uses: Sequence[MemoryDependency] = (),
    ) -> MemoryCatalog:
        """정의 하나를 넣는다(``document["id"]``가 id). 이어 부를 수 있게 자신을 돌려준다."""
        key = (kind, str(document["id"]))
        self.documents[key] = {"kind": kind, **document}
        if files is not None:
            self.bodies[key] = dict(files)
        if uses:
            self.deps[key] = list(uses)
        return self

    def document(self, kind: str, id: str) -> Mapping[str, Any] | None:
        """정의 원문(없으면 None)."""
        return self.documents.get((kind, id))

    def files(self, kind: str, id: str) -> Mapping[str, bytes]:
        """본문 파일들(없으면 빈 매핑)."""
        return self.bodies.get((kind, id), {})

    def dependencies(self, kind: str, id: str) -> Sequence[MemoryDependency]:
        """이 정의가 쓰는 정의."""
        return self.deps.get((kind, id), [])


__all__ = ["MemoryCatalog", "MemoryDependency"]
