"""팀 구성 목록 검증 요약 캐시(design §2R.6).

검증 결과는 그래프만이 아니라 에이전트·리소스(본문 포함)·설정에도 달려 있다. 그래서 캐시 키는
**워크스페이스 개정** = 저장소의 모든 정의 ``(종류, id, version_hash)`` 지문이다. 서버 API로 쓴
변경과 손으로 고친 파일(저장소가 읽을 때 새 해시로 보임)이 모두 개정을 바꾼다. 저장소가 지문 재료
(``kinds``·``summaries``)를 주지 않으면 ``definitions.saved`` 때마다 늘리는 세대 번호를 쓴다.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Iterable
from typing import Any

from agent_console_contracts import GraphValidationSummary


def workspace_revision(store: Any, *, kinds: Iterable[str] | None = None) -> str | None:
    """저장소 정의 전부의 버전 지문(sha256). 지문 재료를 주지 않는 저장소면 None.

    Args:
        store: ``kinds()``·``summaries(kind)``(항목에 ``id``·``version_hash``)를 가진 정의 저장소.
        kinds: 볼 종류(기본 = 저장소의 모든 종류).
    """
    list_kinds = getattr(store, "kinds", None)
    summaries = getattr(store, "summaries", None)
    if not callable(summaries) or (kinds is None and not callable(list_kinds)):
        return None
    rows: list[tuple[str, str, str]] = []
    for kind in sorted(kinds if kinds is not None else list_kinds()):  # type: ignore[misc]
        rows.extend((kind, s.id, s.version_hash) for s in summaries(kind))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


class GraphValidationCache:
    """개정별 그래프 검증 요약 캐시(스레드 안전). 개정이 바뀌면 전부 버린다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._revision: str | None = None
        self._items: dict[str, GraphValidationSummary | None] = {}

    def summaries(
        self,
        revision: str,
        graph_ids: Iterable[str],
        compute: Callable[[str], GraphValidationSummary | None],
    ) -> dict[str, GraphValidationSummary | None]:
        """``graph_ids``의 요약. 이 개정에서 계산한 적 없는 것만 ``compute``로 계산한다."""
        with self._lock:
            if revision != self._revision:
                self._revision, self._items = revision, {}
            known = dict(self._items)
        out: dict[str, GraphValidationSummary | None] = {}
        fresh: dict[str, GraphValidationSummary | None] = {}
        for graph_id in graph_ids:
            if graph_id in known:
                out[graph_id] = known[graph_id]
            else:
                out[graph_id] = fresh[graph_id] = compute(graph_id)
        if fresh:
            with self._lock:
                if self._revision == revision:
                    self._items.update(fresh)
        return out

    def clear(self) -> None:
        with self._lock:
            self._revision, self._items = None, {}


__all__ = ["GraphValidationCache", "workspace_revision"]
