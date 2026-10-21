"""정의 저장소 → 범위 판단 입력(``ScopedDefinition`` 목록)과 짧은 캐시.

정의 종류 이름을 모른다: 읽기 포트가 아는 모든 종류를 읽고, 문서에 문자열 ``id``가 있는 것만
범위 대상으로 본다(싱글턴 공통 설정 등은 빠진다, design §UX-P.6). 저장 전 검사는 정의마다 불릴 수
있어(평문 점검 등) 읽은 목록을 ``ttl``초 동안 다시 쓴다. ``definitions.saved``·옮기기 때 버린다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Collection, Iterable, Mapping
from typing import Any

from agent_console_projects import References, ScopedDefinition
from agent_console_store import StoreError

from .ports import DefinitionReader

type ReferenceSource = Callable[[str, Mapping[str, Any]], Iterable[tuple[str, str]]]


def read_definitions(
    reader: DefinitionReader, *, skip_kinds: Collection[str] = ()
) -> list[ScopedDefinition]:
    """읽기 포트의 모든 정의(문서 포함). 읽을 수 없는 파일·id 없는 문서는 뺀다."""
    out: list[ScopedDefinition] = []
    for kind in reader.kinds():
        if kind in skip_kinds:
            continue
        for def_id in reader.list_ids(kind):
            try:
                document = reader.get(kind, def_id).document
                out.append(ScopedDefinition.from_document(kind, document))
            except (StoreError, ValueError):
                continue
    return out


def combine_references(sources: Iterable[ReferenceSource]) -> References | None:
    """여러 참조 추출 제공자를 하나로(없으면 None). 제공자 예외는 그 제공자만 건너뛴다."""
    items = list(sources)
    if not items:
        return None

    def references(kind: str, document: Mapping[str, Any]) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for source in items:
            try:
                found.extend(source(kind, document))
            except Exception:  # 제공자 하나의 실패가 검사 전체를 막지 않게
                continue
        return found

    return references


class DefinitionSnapshot:
    """정의 목록 캐시(스레드 안전).

    Args:
        reader: 지금 읽기 포트(없으면 None — 부를 때마다 다시 본다).
        ttl: 캐시를 다시 쓰는 시간(초). 0이면 매번 읽는다.
        clock: 단조 시각(초).
        skip_kinds: 범위 대상에서 뺄 종류(같은 저장소에 프로젝트 종류가 있으면).
    """

    def __init__(
        self,
        reader: Callable[[], DefinitionReader | None],
        *,
        ttl: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        skip_kinds: Collection[str] = (),
    ) -> None:
        self._reader = reader
        self._ttl = ttl
        self._clock = clock
        self._skip = frozenset(skip_kinds)
        self._lock = threading.Lock()
        self._cached: tuple[float, int, list[ScopedDefinition]] | None = None
        self._generation = 0

    def available(self) -> bool:
        """읽기 포트가 있는지."""
        return self._reader() is not None

    def get(self) -> list[ScopedDefinition] | None:
        """정의 목록(복사본). 읽기 포트가 없으면 None."""
        reader = self._reader()
        if reader is None:
            return None
        now = self._clock()
        with self._lock:
            cached = self._cached
            if cached is not None and cached[1] == id(reader) and now - cached[0] < self._ttl:
                return list(cached[2])
            generation = self._generation
        items = read_definitions(reader, skip_kinds=self._skip)
        with self._lock:
            if generation == self._generation:  # 읽는 동안 버려졌으면 담지 않는다
                self._cached = (now, id(reader), items)
        return list(items)

    def invalidate(self) -> None:
        """캐시를 버린다."""
        with self._lock:
            self._cached = None
            self._generation += 1


__all__ = ["DefinitionSnapshot", "ReferenceSource", "combine_references", "read_definitions"]
