"""로그 묶음 제안(design §UX-P.1 `log_projects`, §5.2R.6 #3): 연결은 하지 않고 제안만 한다."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from agent_console_contracts import Project

__all__ = ["log_paths_from_sessions", "normalize_path", "suggest_log_projects"]

_DRIVE = re.compile(r"^[A-Za-z]:(/|$)")


def normalize_path(path: str) -> str:
    """비교용 경로: 역슬래시 → `/`, 끝 `/` 제거, Windows 드라이브 경로는 소문자(대소문자 무시).

    >>> normalize_path("C:\\\\Work\\\\App\\\\"), normalize_path("/home/me/app/")
    ('c:/work/app', '/home/me/app')
    """
    p = path.strip().replace("\\", "/")
    while len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p.lower() if _DRIVE.match(p) else p


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def log_paths_from_sessions(sessions: Iterable[Mapping[str, Any] | object]) -> dict[str, list[str]]:
    """로그 세션 요약(`LogSessionSummary` 또는 같은 키 dict) → 묶음 id별 경로(cwd·repo_root).

    묶음(`project`)이 없는 세션은 건너뛴다. 순서는 처음 본 순서다.
    """

    def get(obj: Mapping[str, Any] | object, name: str) -> Any:
        return obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name, None)

    out: dict[str, list[str]] = {}
    for s in sessions:
        ref = get(s, "project")
        group = get(ref, "id") if ref is not None else None
        if not isinstance(group, str) or not group:
            continue
        paths = out.setdefault(group, [])
        for name in ("cwd", "repo_root"):
            value = get(s, name)
            if isinstance(value, str) and value and value not in paths:
                paths.append(value)
    return out


def suggest_log_projects(
    project: Project | Mapping[str, Any],
    log_projects: Mapping[str, Iterable[str]],
    *,
    working_directory: str | None = None,
) -> list[str]:
    """프로젝트 작업 폴더와 같은 경로(또는 그 아래)의 로그 묶음 id 제안.

    이미 연결한 묶음(`project.log_projects`)은 빼고, 입력 순서를 지킨다. 묶음 id 자체가 경로인
    경우(묶음 밖 정책 `cwd`)도 맞춰 본다. 자동으로 연결하지 않는다(화면이 제안으로만 보인다).

    Args:
        project: 프로젝트(`Project` 또는 같은 키 dict).
        log_projects: 묶음 id → 그 묶음에서 본 경로들(`log_paths_from_sessions` 결과 등).
        working_directory: 프로젝트에 작업 폴더가 없을 때 쓸 값(예: 서버 설정 작업 폴더).

    Returns:
        제안할 묶음 id 목록(작업 폴더가 없으면 빈 목록).

    >>> suggest_log_projects({"working_directory": "/w/app"},
    ...                      {"app": ["/w/app/sub"], "other": ["/w/other"], "/w/app": []})
    ['app', '/w/app']
    """
    if isinstance(project, Project):
        wd, linked = project.working_directory, list(project.log_projects)
    else:
        raw_wd, raw_linked = project.get("working_directory"), project.get("log_projects")
        wd = raw_wd if isinstance(raw_wd, str) else None
        linked = (
            [x for x in raw_linked if isinstance(x, str)] if isinstance(raw_linked, list) else []
        )
    wd = wd or working_directory
    if not wd:
        return []
    root = normalize_path(wd)
    out: list[str] = []
    for group, paths in log_projects.items():
        if group in linked or group in out:
            continue
        candidates = [group, *paths]
        if any(_within(normalize_path(p), root) for p in candidates if p):
            out.append(group)
    return out
