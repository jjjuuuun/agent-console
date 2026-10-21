"""정의 저장소 조립: 정의 종류(그래프 해시 = ``graph_hash``)·버전 기록소·저장/삭제 알림.

- 버전 기록소: 호스트 DB 핸들(``BaseServices.database``)이 있으면 그 엔진의 SQLite 버전 기록
  (``definition_versions``·``content_blobs``, legacy 계보), 없으면 메모리(단독 실행·테스트).
  처음 쓸 때 만든다(조립 때 DB를 열지 않는다). ``LazyVersionRepository``·``versions_for``는
  ac-store가 제공하고 여기서 다시 내보낸다(5.2R.33, 프로젝트 모듈과 같은 구현).
- 저장 알림: 버전이 기록될 때마다(만들기·저장·본문 쓰기·되돌리기) ``on_saved(kind, id, hash)``.
- 삭제 알림: 삭제가 성공하면 ``on_deleted(kind, id)``(버전이 기록되지 않으므로 따로 알린다).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from agent_console_contracts import Graph
from agent_console_graph import graph_hash
from agent_console_store import (
    AGENT_KIND,
    DEFAULT_MAX_CONTENT_BYTES,
    GRAPH_KIND,
    RESOURCE_KIND,
    SETTINGS_KIND,
    DefinitionKind,
    FileDefinitionStore,
    LazyVersionRepository,
    ObservedVersionRepository,
    VersionRecorded,
    VersionRepository,
    versions_for,
)

_log = logging.getLogger("agent_console_mod_definitions")

type DefinitionDeleted = Callable[[str, str], None]
"""``(kind, id)``: 정의 하나가 지워졌다."""


def graph_kind_hash(document: Mapping[str, Any]) -> str:
    """그래프 문서의 버전 해시 = ac-graph ``graph_hash``(레이아웃 좌표·키 순서 무관)."""
    return graph_hash(Graph.model_validate(document))


def definition_kinds() -> list[DefinitionKind]:
    """다루는 정의 종류: 그래프(해시 = ``graph_hash``)·에이전트·공통 설정·리소스."""
    return [
        dataclasses.replace(GRAPH_KIND, hash_fn=graph_kind_hash),
        AGENT_KIND,
        SETTINGS_KIND,
        RESOURCE_KIND,
    ]


class DefinitionFileStore(FileDefinitionStore):
    """``FileDefinitionStore`` + 삭제 알림(``on_deleted``, 저장소 쓰기 잠금 안에서 부른다)."""

    def __init__(
        self,
        root: str | Path,
        kinds: Iterable[DefinitionKind],
        *,
        versions: VersionRepository,
        max_content_bytes: int | None = DEFAULT_MAX_CONTENT_BYTES,
        on_deleted: DefinitionDeleted | None = None,
    ) -> None:
        super().__init__(root, kinds, versions=versions, max_content_bytes=max_content_bytes)
        self._on_deleted = on_deleted

    def delete(self, kind: str, id: str, *, expected_version: str | None = None) -> None:
        super().delete(kind, id, expected_version=expected_version)
        if self._on_deleted is not None:
            try:
                self._on_deleted(kind, id)
            except Exception:
                _log.exception("정의 삭제 알림 실패: %s/%s", kind, id)


def build_store(
    root: Path,
    *,
    versions: VersionRepository,
    on_saved: VersionRecorded,
    on_deleted: DefinitionDeleted | None = None,
    max_content_bytes: int | None = DEFAULT_MAX_CONTENT_BYTES,
    kinds: Iterable[DefinitionKind] | None = None,
) -> DefinitionFileStore:
    """워크스페이스 폴더의 정의 저장소(저장 알림은 버전 기록 감싸개로 건다).

    ``on_saved`` 예외는 기록하고 저장은 그대로 둔다(알림 실패가 저장을 막지 않는다).
    """

    def saved(kind: str, item_id: str, version_hash: str) -> None:
        try:
            on_saved(kind, item_id, version_hash)
        except Exception:
            _log.exception("정의 저장 알림 실패: %s/%s", kind, item_id)

    return DefinitionFileStore(
        root,
        list(kinds) if kinds is not None else definition_kinds(),
        versions=ObservedVersionRepository(versions, saved),
        max_content_bytes=max_content_bytes,
        on_deleted=on_deleted,
    )


__all__ = [
    "DefinitionDeleted",
    "DefinitionFileStore",
    "LazyVersionRepository",
    "build_store",
    "definition_kinds",
    "graph_kind_hash",
    "versions_for",
]
