"""사용량 출처가 읽는 실행 이벤트 조회(``usage.event_query``): 앱 기록 + 프로젝트 기록 DB.

계정 창(5시간·주간)은 계정 값이라 프로젝트를 나누지 않는다(design §PI.4.6.3 "계정 창은 앱 표본",
화면 "계정 전체"). 프로젝트 실행의 ``usage.rate_limit``은 그 프로젝트 폴더의 기록 DB에만
있으므로(5.7R.33y2), 창별 최신값은 앱 기록과 **모든 등록 프로젝트** 기록 DB를 합쳐 가장 최근
것을 본다.

- ``MergedEventQuery``: 여러 이벤트 조회의 ``latest_by_type``을 ts 내림차순으로 합친다(순수).
- ``project_readers``: 등록 프로젝트(보관 제외, 또는 한 프로젝트) → 기록 DB 저장소. 읽을 수 없는
  공간은 경고 후 건너뛴다.
- ``project_rollup_sources``: 같은 목록 → 토큰 집계 추가 출처(``usage.token_rollups``, 요청 11/08).
- ``project_event_sources``: 등록 프로젝트 목록 + 기록 공간 → 프로젝트별 이벤트 조회. 프로젝트 목록
  이나 기록 공간이 없으면(``mod-projects``·``link-projects-records`` 꺼짐) 빈 목록이다. 읽을 수
  없는 공간(폴더 없음·깨짐·모르는 프로젝트)은 건너뛴다.
"""

from __future__ import annotations

import builtins
import heapq
import logging
from collections.abc import Callable, Iterable, Iterator
from typing import Any, Protocol

from agent_console_contracts import RunEvent
from agent_console_store import RecordsStores, RecordsUnavailable, SqliteStorage

from .rollups import RollupSource

_log = logging.getLogger(__name__)


class LatestEvents(Protocol):
    """``latest_by_type`` 조회(``agent_console_usage.UsageEventQuery``와 같은 모양)."""

    def latest_by_type(
        self,
        type: str,
        *,
        run_id: str | None = None,
        actor: str | None = None,
        limit: int = 1,
    ) -> builtins.list[RunEvent]: ...


class ProjectListing(Protocol):
    """``projects.lookup`` 중 이 연동이 쓰는 부분."""

    def list_projects(self) -> builtins.list[Any]: ...


class MergedEventQuery:
    """기본 조회 + 추가 조회들의 ``latest_by_type``을 합친다(``UsageEventQuery`` 모양).

    Args:
        base: 늘 읽는 조회(앱 기록 ``runs.events``).
        extra: 부를 때마다 추가 조회 목록(예: 프로젝트 기록 DB들). 하나가 실패하면 그것만 건너뛴다.
    """

    def __init__(
        self, base: LatestEvents, extra: Callable[[], Iterable[LatestEvents]] = lambda: ()
    ) -> None:
        self._base = base
        self._extra = extra

    def latest_by_type(
        self,
        type: str,
        *,
        run_id: str | None = None,
        actor: str | None = None,
        limit: int = 1,
    ) -> builtins.list[RunEvent]:
        """그 ``type``의 최근 이벤트 ``limit``개(모든 출처를 합친 ts 내림차순)."""
        found = [self._base.latest_by_type(type, run_id=run_id, actor=actor, limit=limit)]
        for source in self._sources():
            try:
                found.append(source.latest_by_type(type, run_id=run_id, actor=actor, limit=limit))
            except Exception:  # 프로젝트 기록 하나가 깨져도 사용량 화면은 나온다
                _log.warning("프로젝트 기록 이벤트를 읽지 못했습니다", exc_info=True)
        merged = heapq.merge(*found, key=lambda event: event.ts, reverse=True)
        return [event for _, event in zip(range(limit), merged, strict=False)]

    def _sources(self) -> Iterator[LatestEvents]:
        try:
            yield from self._extra()
        except Exception:
            _log.warning("프로젝트 기록 목록을 읽지 못했습니다", exc_info=True)


def project_readers(
    projects: Callable[[], ProjectListing | None],
    stores: RecordsStores[SqliteStorage],
    *,
    only: str | None = None,
) -> Iterator[tuple[str, SqliteStorage]]:
    """등록 프로젝트의 기록 DB 저장소 ``(프로젝트 id, 저장소)``(부를 때마다 목록을 다시 읽는다).

    Args:
        projects: 지금 ``projects.lookup`` 포트(없으면 None → 아무것도 없음).
        stores: ``records.spaces`` 위의 저장소 고르기(포트가 없으면 아무것도 없음).
        only: 주면 그 프로젝트만(보관이어도 읽는다 — 사용자가 고른 프로젝트). None이면 보관 제외
            전부.

    읽을 수 없는 공간(폴더 없음·깨짐)은 경고하고 건너뛴다. 모르는 프로젝트·기록 DB 파일이 아직
    없는 프로젝트는 조용히 건너뛴다.
    """
    listing = projects()
    if listing is None or not stores.available:
        return
    for project in listing.list_projects():
        if only is not None and project.id != only:
            continue
        if only is None and getattr(project, "archived", False):
            continue
        try:
            reader = stores.reader(project.id)
        except RecordsUnavailable as exc:
            _log.warning("프로젝트 기록을 읽을 수 없어 건너뜁니다: %s (%s)", project.id, exc.reason)
            continue
        except LookupError:
            continue  # 목록과 공간 사이에 지워진 프로젝트
        if reader is not None:  # 기록 DB 파일이 아직 없다
            yield project.id, reader


def project_rollup_sources(
    projects: Callable[[], ProjectListing | None],
    stores: RecordsStores[SqliteStorage],
) -> Callable[[str | None], Iterator[RollupSource]]:
    """토큰 집계 추가 출처(``IncrementalTokenRollups(extra=)``): 등록 프로젝트 기록 DB마다 하나.

    키는 ``stores.space_name(id)``(공간 이름 — 프로젝트마다 다르다). ``project_id``가 None이면 보관
    제외 전부, 주면 그 프로젝트만.
    """

    def sources(project_id: str | None) -> Iterator[RollupSource]:
        for pid, reader in project_readers(projects, stores, only=project_id):
            yield RollupSource(stores.space_name(pid), reader.runs, reader.events)

    return sources


def project_event_sources(
    projects: Callable[[], ProjectListing | None],
    stores: RecordsStores[SqliteStorage],
) -> Callable[[], Iterator[LatestEvents]]:
    """등록 프로젝트(보관 제외)의 기록 DB 이벤트 조회들(부를 때마다 목록을 다시 읽는다).

    Args:
        projects: 지금 ``projects.lookup`` 포트(없으면 None → 빈 목록).
        stores: ``records.spaces`` 위의 저장소 고르기(포트가 없으면 빈 목록).
    """

    def sources() -> Iterator[LatestEvents]:
        for _, reader in project_readers(projects, stores):
            yield reader.events

    return sources


__all__ = [
    "LatestEvents",
    "MergedEventQuery",
    "ProjectListing",
    "project_event_sources",
    "project_readers",
    "project_rollup_sources",
]
