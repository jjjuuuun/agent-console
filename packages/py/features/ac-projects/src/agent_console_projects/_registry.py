"""등록 규칙(design §PI.2 K33-2·K33-3·§PI.8): 폴더 겹침, 프로젝트 상태, 경로 → 프로젝트.

입력 프로젝트는 계약 `Project`·`ProjectRegistration` 또는 같은 키의 dict(옛 `working_directory`도
읽음)다. 폴더 값은 `resolve_folder`로 정규화한다(상대 경로는 `base_dir` 기준, 없으면 폴더 없음).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import (
    ErrorCodes,
    FolderConflict,
    KnownFolderCheckStatuses,
    KnownProjectStatuses,
    Project,
    ProjectFolderConflictDetails,
    ProjectRegistration,
)
from agent_console_local_folders import FileSystem, PathFlavor

from ._paths import PathRules, folder_key, host_flavor, path_relation, resolve_folder

__all__ = [
    "ProjectLike",
    "ProjectStatusResult",
    "RegisteredFolder",
    "conflict_details",
    "conflict_error_code",
    "conflict_status",
    "folder_conflicts",
    "project_for_path",
    "project_status",
    "registered_folders",
    "registry_conflicts",
]

type ProjectLike = Project | ProjectRegistration | Mapping[str, Any]
"""프로젝트 입력: 합친 보기·등록부 모델 또는 같은 키의 dict."""


@dataclass(frozen=True, slots=True)
class RegisteredFolder:
    """등록부 한 줄(규칙에 필요한 값만).

    Attributes:
        id: 등록 id.
        folder: 정규화한 절대 경로. 없거나 쓸 수 없는 값이면 None(`folder_unset`).
        archived: 보관(등록 해제)됨.
    """

    id: str
    folder: str | None
    archived: bool = False


def _get(project: ProjectLike, name: str) -> Any:
    if isinstance(project, Mapping):
        return project.get(name)
    return getattr(project, name, None)


def registered_folders(
    projects: Iterable[ProjectLike | RegisteredFolder],
    *,
    base_dir: str | None = None,
    flavor: PathFlavor | None = None,
) -> list[RegisteredFolder]:
    """프로젝트 목록 → `RegisteredFolder` 목록(입력 순서, id 없는 항목은 뺌).

    >>> [(r.id, r.folder) for r in registered_folders(
    ...     [{"id": "a", "working_directory": "app"}, {"id": "b"}], base_dir="/w", flavor="posix")]
    [('a', '/w/app'), ('b', None)]
    """
    fl = flavor or host_flavor()
    out: list[RegisteredFolder] = []
    for p in projects:
        if isinstance(p, RegisteredFolder):
            out.append(p)
            continue
        pid = _get(p, "id")
        if not isinstance(pid, str) or not pid:
            continue
        raw = _get(p, "folder")
        if raw is None and isinstance(p, Mapping):
            raw = p.get("working_directory")
        out.append(
            RegisteredFolder(
                id=pid,
                folder=resolve_folder(raw, base_dir=base_dir, flavor=fl),
                archived=bool(_get(p, "archived")),
            )
        )
    return out


_RELATION_ORDER = {"same": 0, "parent": 1, "child": 2}


def folder_conflicts(
    projects: Iterable[ProjectLike | RegisteredFolder],
    folder: str,
    *,
    exclude_project_id: str | None = None,
    base_dir: str | None = None,
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
) -> list[FolderConflict]:
    """등록하려는 `folder`와 같거나 겹치는 등록 프로젝트(K33-2).

    - 같은 폴더(`same`)는 보관된 프로젝트도 낸다(`archived=True` → 다시 등록 제안).
    - 겹침(`parent` = 그 프로젝트가 이 폴더를 포함, `child` = 이 폴더 안에 있음)은 보관된 프로젝트를
      뺀다.
    - `exclude_project_id`(경로 다시 지정의 자기 자신, K33-13)는 뺀다. 없는 id면 무시.
    - 순서: same → parent → child, 같은 관계는 등록 순.

    >>> regs = [{"id": "a", "folder": "/w/a"}, {"id": "w", "folder": "/w", "archived": True},
    ...         {"id": "c", "folder": "/w/b/c"}]
    >>> [(c.project_id, c.relation, c.archived)
    ...  for c in folder_conflicts(regs, "/w/b", flavor="posix")]
    [('c', 'child', False)]
    >>> [(c.project_id, c.relation) for c in folder_conflicts(regs, "/W/A/", flavor="windows")]
    []
    """
    fl = flavor or host_flavor()
    found: list[FolderConflict] = []
    for reg in registered_folders(projects, base_dir=base_dir, flavor=fl):
        if reg.folder is None or reg.id == exclude_project_id:
            continue
        relation = path_relation(folder, reg.folder, flavor=fl, rules=rules)
        if relation is None or (reg.archived and relation != "same"):
            continue
        found.append(
            FolderConflict(
                project_id=reg.id, relation=relation, archived=reg.archived, folder=reg.folder
            )
        )
    found.sort(key=lambda c: (_RELATION_ORDER[c.relation], c.archived))
    return found


def conflict_status(conflicts: Iterable[FolderConflict]) -> str | None:
    """충돌 목록 → 폴더 확인 상태(`KnownFolderCheckStatuses`). 충돌이 없으면 None.

    같은 폴더가 등록돼 있으면 `taken`, 보관된 것만 있으면 `taken_archived`, 그다음 `overlap_parent`·
    `overlap_child`.
    """
    items = list(conflicts)
    if any(c.relation == "same" and not c.archived for c in items):
        return KnownFolderCheckStatuses.TAKEN
    if any(c.relation == "same" for c in items):
        return KnownFolderCheckStatuses.TAKEN_ARCHIVED
    if any(c.relation == "parent" for c in items):
        return KnownFolderCheckStatuses.OVERLAP_PARENT
    if any(c.relation == "child" for c in items):
        return KnownFolderCheckStatuses.OVERLAP_CHILD
    return None


def conflict_error_code(conflict: FolderConflict) -> str:
    """등록 요청을 막을 때의 오류 코드(409): 같은 폴더 `folder_taken`, 겹침 `folder_overlaps`."""
    if conflict.relation == "same":
        return ErrorCodes.PROJECT_FOLDER_TAKEN
    return ErrorCodes.PROJECT_FOLDER_OVERLAPS


def conflict_details(conflict: FolderConflict) -> ProjectFolderConflictDetails:
    """409 오류의 `details`."""
    return ProjectFolderConflictDetails(
        project_id=conflict.project_id,
        relation=None if conflict.relation == "same" else conflict.relation,
        archived=conflict.archived,
        folder=conflict.folder,
    )


def registry_conflicts(
    projects: Iterable[ProjectLike | RegisteredFolder],
    *,
    base_dir: str | None = None,
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
) -> dict[str, FolderConflict]:
    """이미 등록된(보관 아님) 프로젝트끼리 같거나 겹치는 것(옛 파일, design §PI.8).

    Returns:
        등록 id → 충돌 상대 하나(관계는 상대가 이 프로젝트에 대해 무엇인가). 두 쪽 모두 들어간다
        (상태 `folder_conflict`).

    >>> sorted((k, v.project_id, v.relation) for k, v in registry_conflicts(
    ...     [{"id": "a", "folder": "/w"}, {"id": "b", "folder": "/w/x"},
    ...      {"id": "c", "folder": "/v"}],
    ...     flavor="posix").items())
    [('a', 'b', 'child'), ('b', 'a', 'parent')]
    """
    fl = flavor or host_flavor()
    live = [
        r
        for r in registered_folders(projects, base_dir=base_dir, flavor=fl)
        if r.folder is not None and not r.archived
    ]
    out: dict[str, FolderConflict] = {}
    for i, a in enumerate(live):
        for b in live[i + 1 :]:
            assert a.folder is not None
            assert b.folder is not None
            rel = path_relation(a.folder, b.folder, flavor=fl, rules=rules)
            if rel is None:
                continue
            back = {"same": "same", "parent": "child", "child": "parent"}[rel]
            out.setdefault(a.id, FolderConflict(project_id=b.id, relation=rel, folder=b.folder))
            out.setdefault(b.id, FolderConflict(project_id=a.id, relation=back, folder=a.folder))
    return out


@dataclass(frozen=True, slots=True)
class ProjectStatusResult:
    """프로젝트 상태(계산 값). `status`는 `KnownProjectStatuses` 값, `detail`은 한 줄 이유."""

    status: str
    detail: str | None = None


def project_status(
    project: ProjectLike | RegisteredFolder,
    *,
    fs: FileSystem,
    conflicts: Mapping[str, FolderConflict] | None = None,
    manifest_invalid: bool = False,
    base_dir: str | None = None,
) -> ProjectStatusResult:
    """프로젝트 상태(K33-3). 폴더 상태만 읽는다(`fs.info`, 목록·내용은 읽지 않음).

    순서: 폴더 없음 값 `folder_unset` → 옛 파일 충돌 `folder_conflict`(`registry_conflicts`) →
    `folder_missing` → `no_access`(상태를 알 수 없음·읽기 권한 없음) → `not_a_directory` →
    `manifest_invalid`(호출자가 매니페스트를 읽어 알려 줌) → `ready`. 시간 상한은 부르는 쪽이 건다.

    >>> from agent_console_local_folders import MemoryFileSystem
    >>> fs = MemoryFileSystem().add_dir("/w").add_dir("/w/app")
    >>> project_status({"id": "a", "folder": "/w/app"}, fs=fs).status
    'ready'
    >>> project_status({"id": "a", "folder": "/w/gone"}, fs=fs).status
    'folder_missing'
    """
    regs = registered_folders([project], base_dir=base_dir, flavor=fs.flavor)
    reg = regs[0] if regs else RegisteredFolder(id="", folder=None)
    if reg.folder is None:
        return ProjectStatusResult(KnownProjectStatuses.FOLDER_UNSET)
    if conflicts and reg.id in conflicts:
        other = conflicts[reg.id]
        return ProjectStatusResult(KnownProjectStatuses.FOLDER_CONFLICT, other.project_id)
    try:
        info = fs.info(reg.folder)
    except OSError as exc:
        return ProjectStatusResult(KnownProjectStatuses.NO_ACCESS, type(exc).__name__)
    if info is None:
        return ProjectStatusResult(KnownProjectStatuses.FOLDER_MISSING, reg.folder)
    if not info.is_dir:
        return ProjectStatusResult(KnownProjectStatuses.NOT_A_DIRECTORY, reg.folder)
    if not info.readable:
        return ProjectStatusResult(KnownProjectStatuses.NO_ACCESS, reg.folder)
    if manifest_invalid:
        return ProjectStatusResult(KnownProjectStatuses.MANIFEST_INVALID)
    return ProjectStatusResult(KnownProjectStatuses.READY)


def project_for_path(
    projects: Iterable[ProjectLike | RegisteredFolder],
    path: str,
    *,
    base_dir: str | None = None,
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
) -> str | None:
    """경로(세션 cwd 등)가 들어 있는 등록(보관 아님) 프로젝트 id. 없으면 None.

    겹침은 등록 때 막지만 옛 파일이 겹치면 가장 깊은 폴더가 이긴다. 하위 폴더도 그 프로젝트다.

    >>> regs = [{"id": "a", "folder": "/w/a"}, {"id": "old", "folder": "/w", "archived": True}]
    >>> project_for_path(regs, "/w/a/src", flavor="posix")
    'a'
    >>> project_for_path(regs, "/w/b", flavor="posix") is None
    True
    """
    fl = flavor or host_flavor()
    target = resolve_folder(path, flavor=fl)
    if target is None:
        return None
    best: tuple[int, str] | None = None
    for reg in registered_folders(projects, base_dir=base_dir, flavor=fl):
        if reg.folder is None or reg.archived:
            continue
        if path_relation(target, reg.folder, flavor=fl, rules=rules) in ("same", "parent"):
            depth = len(folder_key(reg.folder, flavor=fl, rules=rules))
            if best is None or depth > best[0]:
                best = (depth, reg.id)
    return best[1] if best else None
