"""작업 실행 기록 읽기: 라벨 질의 페이지를 끝까지(상한까지) 모은다(design §6R.1.5, 6R.12).

``runs.reader.page``는 공간 기록 DB(``project_id``가 있고 기록 공간이 있는 조립) 또는 호스트 DB를
읽는다. 앱 DB에 남은 옛 기록까지 보려고 공간 이름이 있으면 호스트 DB도 같은 라벨로 한 번 더 읽고
``project_id``가 같은 것만 더한다(같은 id는 한 번만). 공간 이름 없는 스펙(단독 루트)은
``project_id``가 없는 Run만 본다(같은 스펙 id를 쓰는 프로젝트 실행과 섞이지 않게).
"""

from __future__ import annotations

from collections.abc import Mapping

from agent_console_contracts import Run

from .ports import RunReader


def _pages(
    reader: RunReader,
    *,
    project_id: str | None,
    labels: Mapping[str, str],
    limit: int,
    page_size: int,
) -> list[Run]:
    found: list[Run] = []
    cursor: str | None = None
    while len(found) < limit:
        items, cursor = reader.page(
            cursor=cursor,
            limit=min(page_size, limit - len(found)),
            project_id=project_id,
            root_only=True,
            labels=dict(labels),
        )
        found.extend(items)
        if cursor is None or not items:
            break
    return found


def labeled_runs(
    reader: RunReader,
    *,
    project_id: str | None,
    labels: Mapping[str, str],
    limit: int,
    page_size: int,
) -> list[Run]:
    """라벨이 모두 맞는 루트 Run(최근 순, 최대 ``limit``개).

    Args:
        reader: ``runs.reader``.
        project_id: 공간 이름(= 프로젝트 등록 id). None = 프로젝트 없는 Run만.
        labels: 라벨 키 → 값(AND).
        limit: 모을 Run 수 상한.
        page_size: 한 쪽 크기.
    """
    out: dict[str, Run] = {}
    for run in _pages(
        reader, project_id=project_id, labels=labels, limit=limit, page_size=page_size
    ):
        # 공간 질의 결과는 그 공간 것이다. 공간 없는 질의(호스트 DB 전체)만 거른다.
        if project_id is not None or run.project_id is None:
            out.setdefault(run.id, run)
    if project_id is not None and len(out) < limit:
        for run in _pages(reader, project_id=None, labels=labels, limit=limit, page_size=page_size):
            if run.project_id == project_id:
                out.setdefault(run.id, run)
    runs = sorted(out.values(), key=lambda r: (r.created_at, r.id), reverse=True)
    return runs[:limit]


def run_time(run: Run) -> float:
    """실행 시각(끝난 시각 → 시작 → 만든 시각)."""
    return run.ended_at or run.started_at or run.created_at


__all__ = ["labeled_runs", "run_time"]
