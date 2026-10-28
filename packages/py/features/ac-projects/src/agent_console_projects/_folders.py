"""등록된 프로젝트 → 로컬 폴더(design §PI.5). 기능은 앱에 등록된 프로젝트 폴더에 대해서만 동작한다.

로그 수집 범위처럼 "어느 폴더가 앱의 프로젝트인가"를 묻는 곳이 이 함수 하나를 쓴다. 결과는 등록
(보관 아님) 프로젝트 전체 + id다(`entries`). 5.7R.33e부터 서버 작업 폴더를 프로젝트 폴더로 대신 쓰지
않는다(폴더 없는 옛 프로젝트는 빠진다 — 상태 `folder_unset`).

`current`는 옛 로그 범위 `project_scope: current`용 호환 값이다(서버 작업 폴더와 같은 등록 폴더).
`working_directory=`를 줄 때만 채운다. 로그 범위가 "등록 전체" 하나로 바뀌면(33i) 지운다.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from agent_console_local_folders import PathFlavor

from ._paths import PathRules, folder_key, host_flavor
from ._registry import ProjectLike, RegisteredFolder, project_for_path, registered_folders

__all__ = ["ProjectFolder", "ProjectFolderSet", "project_folders"]


@dataclass(frozen=True, slots=True)
class ProjectFolder:
    """등록된 프로젝트 폴더 하나.

    Attributes:
        id: 등록 id(실행·대화·로그 기록의 `project_id`).
        folder: 정규화한 절대 경로.
    """

    id: str
    folder: Path


@dataclass(frozen=True)
class ProjectFolderSet:
    """등록된 프로젝트 폴더 묶음.

    Attributes:
        entries: 등록(보관 아님) 프로젝트 폴더 전체(id 포함, 겹침 없음, 등록 순).
        current: (deprecated, 33i 뒤 삭제) 서버 작업 폴더와 같은 등록 폴더(0개 또는 1개).
        flavor: 경로 방식(`project_for` 비교용).
        rules: 경로 비교 규칙.
    """

    entries: tuple[ProjectFolder, ...] = ()
    current: tuple[Path, ...] = ()
    flavor: PathFlavor | None = None
    rules: PathRules | None = None

    @property
    def registered(self) -> tuple[Path, ...]:
        """등록 폴더 경로만(등록 순)."""
        return tuple(e.folder for e in self.entries)

    def project_for(self, path: str | Path) -> str | None:
        """경로가 들어 있는 등록 프로젝트 id(하위 폴더 포함). 없으면 None."""
        return project_for_path(
            [RegisteredFolder(e.id, str(e.folder)) for e in self.entries],
            str(path),
            flavor=self.flavor,
            rules=self.rules,
        )


def project_folders(
    projects: Iterable[ProjectLike | RegisteredFolder],
    *,
    base_dir: Path | str | None = None,
    working_directory: Path | None = None,
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
) -> ProjectFolderSet:
    """등록된 프로젝트 → 폴더 묶음(보관·폴더 없음 제외, 같은 폴더는 처음 것만).

    Args:
        projects: 등록부(`Project`·`ProjectRegistration`·dict).
        base_dir: 옛 파일의 상대 경로 기준(설정 파일 폴더). 없으면 상대 경로 프로젝트는 빠진다.
        working_directory: (deprecated) 주면 `current`를 채운다(옛 로그 범위 `current`용).
        flavor: 경로 방식(기본 = 이 프로세스).
        rules: 경로 비교 규칙.

    >>> sets = project_folders(
    ...     [{"id": "a", "folder": "/w/a"}, {"id": "old"}, {"id": "b", "folder": "b"},
    ...      {"id": "z", "folder": "/w/z", "archived": True}],
    ...     base_dir="/w", flavor="posix")
    >>> [(e.id, e.folder.as_posix()) for e in sets.entries], sets.project_for("/w/b/src")
    ([('a', '/w/a'), ('b', '/w/b')], 'b')
    >>> project_folders([]).entries
    ()
    """
    fl = flavor or host_flavor()
    base = str(base_dir) if base_dir is not None else None
    entries: list[ProjectFolder] = []
    seen: set[str] = set()
    for reg in registered_folders(projects, base_dir=base, flavor=fl):
        if reg.folder is None or reg.archived:
            continue
        key = folder_key(reg.folder, flavor=fl, rules=rules)
        if key in seen:
            continue
        seen.add(key)
        entries.append(ProjectFolder(id=reg.id, folder=Path(reg.folder)))
    current: tuple[Path, ...] = ()
    if working_directory is not None:
        here = folder_key(str(working_directory), flavor=fl, rules=rules)
        current = tuple(
            e.folder for e in entries if folder_key(str(e.folder), flavor=fl, rules=rules) == here
        )[:1]
    return ProjectFolderSet(entries=tuple(entries), current=current, flavor=fl, rules=rules)
