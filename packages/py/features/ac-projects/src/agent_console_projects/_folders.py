"""등록된 프로젝트 → 로컬 폴더(design §PI.5). 기능은 앱에 등록된 프로젝트 폴더에 대해서만 동작한다.

로그 수집 범위처럼 "어느 폴더가 앱의 프로젝트인가"를 묻는 곳이 이 함수 하나를 쓴다. 결과는 등록
(보관 아님) 프로젝트 전체 + id다(`entries`). 5.7R.33e부터 서버 작업 폴더를 프로젝트 폴더로 대신 쓰지
않는다(폴더 없는 옛 프로젝트는 빠진다 — 상태 `folder_unset`). 5.7R.33i에서 옛 로그 범위
`current`용 호환 값(`current`, `working_directory=`)을 지웠다. 보관된 프로젝트 폴더는 `archived`에
따로 둔다(로그는 보관 프로젝트를 새로 읽지 않지만 색인은 남긴다, design §PI.5).
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
        archived: 보관된 프로젝트 폴더(id 포함, `entries`와 같은 폴더는 빠짐, 등록 순).
            기능은 이 폴더를 새로 읽지 않는다. 이미 만든 색인·기록을 지우지 않을 때만 쓴다.
        flavor: 경로 방식(`project_for` 비교용).
        rules: 경로 비교 규칙.
    """

    entries: tuple[ProjectFolder, ...] = ()
    archived: tuple[ProjectFolder, ...] = ()
    flavor: PathFlavor | None = None
    rules: PathRules | None = None

    @property
    def registered(self) -> tuple[Path, ...]:
        """등록 폴더 경로만(등록 순)."""
        return tuple(e.folder for e in self.entries)

    @property
    def archived_folders(self) -> tuple[Path, ...]:
        """보관된 프로젝트 폴더 경로만(등록 순)."""
        return tuple(e.folder for e in self.archived)

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
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
) -> ProjectFolderSet:
    """등록된 프로젝트 → 폴더 묶음(폴더 없음 제외, 같은 폴더는 처음 것만, 보관은 `archived`로).

    Args:
        projects: 등록부(`Project`·`ProjectRegistration`·dict).
        base_dir: 옛 파일의 상대 경로 기준(설정 파일 폴더). 없으면 상대 경로 프로젝트는 빠진다.
        flavor: 경로 방식(기본 = 이 프로세스).
        rules: 경로 비교 규칙.

    >>> sets = project_folders(
    ...     [{"id": "a", "folder": "/w/a"}, {"id": "old"}, {"id": "b", "folder": "b"},
    ...      {"id": "z", "folder": "/w/z", "archived": True}],
    ...     base_dir="/w", flavor="posix")
    >>> [(e.id, e.folder.as_posix()) for e in sets.entries], sets.project_for("/w/b/src")
    ([('a', '/w/a'), ('b', '/w/b')], 'b')
    >>> [e.id for e in sets.archived], sets.project_for("/w/z") is None
    (['z'], True)
    >>> project_folders([]).entries
    ()
    """
    fl = flavor or host_flavor()
    base = str(base_dir) if base_dir is not None else None
    entries: list[ProjectFolder] = []
    archived: list[ProjectFolder] = []
    seen: set[str] = set()
    regs = registered_folders(projects, base_dir=base, flavor=fl)
    # 보관 아님을 먼저 본다: 같은 폴더가 보관·등록 둘 다 있으면 등록 쪽이 이긴다.
    for reg in sorted(regs, key=lambda r: r.archived):
        if reg.folder is None:
            continue
        key = folder_key(reg.folder, flavor=fl, rules=rules)
        if key in seen:
            continue
        seen.add(key)
        item = ProjectFolder(id=reg.id, folder=Path(reg.folder))
        (archived if reg.archived else entries).append(item)
    return ProjectFolderSet(
        entries=tuple(entries), archived=tuple(archived), flavor=fl, rules=rules
    )
