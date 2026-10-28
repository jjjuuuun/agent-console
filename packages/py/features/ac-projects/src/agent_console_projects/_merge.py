"""등록부 + 매니페스트 → 합친 보기 `Project`(design §PI.2 K33-1·§PI.8).

- 등록부(`ProjectRegistration`, 앱): `id`·`folder`·`archived`·`archived_at`·`labels`.
- 매니페스트(`ProjectManifest`, 폴더): `name`·`description`·`settings`·`attributes`(+ 폴더 id).
- 매니페스트가 없는 옛 등록(0.11 이하)은 등록부에 남아 있는 `name`·`description`·`settings`·
  `attributes`를 읽어 쓴다(읽을 때 해석, K33-9). 첫 저장 때 매니페스트로 옮길 값은
  `legacy_manifest_values`, 등록부에 남길 값은 `split_project`.
- 버전 해시(`If-Match`)는 두 파일 버전을 합친 값(`combined_version`) — 둘 중 하나가 바뀌면 바뀐다.
"""

from __future__ import annotations

import copy
import hashlib
import string
from collections.abc import Mapping
from typing import Any, Final

from agent_console_contracts import (
    Issue,
    KnownIssueCodes,
    Project,
    ProjectManifest,
    ProjectRegistration,
    ignored_project_keys,
)
from agent_console_local_folders import PathFlavor, path_module

from ._paths import host_flavor

__all__ = [
    "MANIFEST_KEYS",
    "REGISTRATION_KEYS",
    "combined_version",
    "ignored_key_issues",
    "initial_manifest",
    "legacy_manifest_values",
    "merge_project",
    "split_project",
]

REGISTRATION_KEYS: Final = frozenset(ProjectRegistration.model_fields)
"""등록부에 남는 키(계약 모델 필드에서 계산 — 코드에 필드 목록을 두지 않는다)."""

MANIFEST_KEYS: Final = frozenset(ProjectManifest.model_fields) - {"format", "id"}
"""매니페스트에 쓰는 사용자 값 키(형식 번호·폴더 id 제외)."""


def _doc(
    value: ProjectRegistration | ProjectManifest | Project | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    return value.model_dump(mode="json", exclude_unset=False)


def legacy_manifest_values(
    registration: ProjectRegistration | Mapping[str, Any],
) -> dict[str, Any]:
    """옛 등록부 파일에 남아 있는 매니페스트 값(`name`·`description`·`settings`·`attributes`).

    새 등록부에는 이 키가 없으므로 빈 dict다.

    >>> legacy_manifest_values({"id": "a", "folder": "/w/a", "name": "A", "labels": []})
    {'name': 'A'}
    """
    doc = _doc(registration)
    return {k: doc[k] for k in sorted(MANIFEST_KEYS) if k in doc and doc[k] is not None}


def _fallback_name(reg: ProjectRegistration, flavor: PathFlavor | None) -> str:
    if reg.folder:
        pm = path_module(flavor or host_flavor())
        name: str = pm.basename(pm.normpath(reg.folder))
        if name:
            return name
    return reg.id


def merge_project(
    registration: ProjectRegistration | Mapping[str, Any],
    manifest: ProjectManifest | Mapping[str, Any] | None = None,
    *,
    flavor: PathFlavor | None = None,
) -> Project:
    """등록부와 매니페스트를 합친 `Project`.

    - `id`·`folder`·`archived`·`archived_at`·`labels`는 등록부.
    - `name`·`description`·`settings`·`attributes`는 매니페스트. 매니페스트가 없으면(깨짐·아직 없음)
      옛 등록부 값, 그것도 없으면 이름 = 폴더 이름(없으면 id).

    Raises:
        pydantic.ValidationError: 등록부·매니페스트가 계약 모양이 아님.

    >>> p = merge_project({"id": "pay-2", "folder": "/w/wt"},
    ...                   {"format": 1, "id": "pay", "name": "결제", "x-other": 1})
    >>> p.id, p.name, p.folder
    ('pay-2', '결제', '/w/wt')
    >>> merge_project({"id": "old", "working_directory": "/w/old"}, flavor="posix").name
    'old'
    """
    reg = (
        registration
        if isinstance(registration, ProjectRegistration)
        else ProjectRegistration.model_validate(registration)
    )
    if manifest is None:
        values = legacy_manifest_values(registration)
    else:
        man = (
            manifest
            if isinstance(manifest, ProjectManifest)
            else ProjectManifest.model_validate(manifest)
        )
        values = {
            k: v
            for k, v in man.model_dump(mode="json", exclude_unset=True).items()
            if k in MANIFEST_KEYS
        }
        values["name"] = man.name
    values.setdefault("name", None)
    if not values["name"]:
        values["name"] = _fallback_name(reg, flavor)
    return Project.model_validate(
        {
            "id": reg.id,
            "folder": reg.folder,
            "archived": reg.archived,
            "archived_at": reg.archived_at,
            "labels": list(reg.labels),
            **values,
        }
    )


def split_project(
    project: Project | Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """합친 보기 → (등록부 값, 매니페스트 사용자 값). 저장할 때 각 파일에 쓸 값이다.

    등록부 값에는 `REGISTRATION_KEYS`만, 매니페스트 값에는 `MANIFEST_KEYS`만 들어간다(옛 키·모르는
    키는 빠짐). 매니페스트의 `format`·`id`는 호출자(매니페스트 저장소)가 지킨다.

    >>> reg, man = split_project({"id": "a", "name": "A", "folder": "/w/a", "settings": None})
    >>> sorted(reg)
    ['archived', 'archived_at', 'folder', 'id', 'kind', 'labels']
    >>> sorted(man)
    ['attributes', 'description', 'name']
    """
    doc = (
        project.model_dump(mode="json", exclude_unset=False)
        if isinstance(project, Project)
        else Project.model_validate(project).model_dump(mode="json", exclude_unset=False)
    )
    reg = {k: doc[k] for k in sorted(REGISTRATION_KEYS) if k in doc}
    man = {k: doc[k] for k in sorted(MANIFEST_KEYS) if k in doc and doc[k] is not None}
    return reg, man


def initial_manifest(
    registration: ProjectRegistration | Mapping[str, Any],
    *,
    manifest_id: str | None = None,
    name: str | None = None,
    description: str | None = None,
    flavor: PathFlavor | None = None,
) -> ProjectManifest:
    """처음 만들 매니페스트(등록할 때 `init_space`에 넘김, 또는 옛 등록을 옮길 때).

    값 순서: 인자 → 옛 등록부 값 → 폴더 이름. 폴더 id 기본 = 등록 id.

    >>> m = initial_manifest({"id": "pay", "folder": "/w/pay", "description": "옛 설명"},
    ...                      flavor="posix")
    >>> m.id, m.name, m.description
    ('pay', 'pay', '옛 설명')
    """
    reg = (
        registration
        if isinstance(registration, ProjectRegistration)
        else ProjectRegistration.model_validate(registration)
    )
    values = legacy_manifest_values(registration)
    if name:
        values["name"] = name
    if description is not None:
        values["description"] = description
    if not values.get("name"):
        values["name"] = _fallback_name(reg, flavor)
    return ProjectManifest.model_validate({"id": manifest_id or reg.id, **values})


def combined_version(registration_version: str | None, manifest_version: str | None) -> str:
    """등록부·매니페스트 버전을 합친 해시(`ProjectView.version_hash`, `If-Match`).

    둘 중 하나가 바뀌면 바뀐다. 매니페스트가 없거나 깨졌으면 `manifest_version=None`.

    >>> a = combined_version("r1", "m1")
    >>> a == combined_version("r1", "m1"), a == combined_version("r1", "m2"), len(a)
    (True, False, 64)
    """
    text = f"registration:{registration_version or ''}\nmanifest:{manifest_version or ''}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


DEFAULT_IGNORED_KEY_MESSAGE: Final = (
    "프로젝트 ${project}의 옛 설정 키 ${key}는 더 이상 쓰지 않아 무시합니다. 저장하면 빠집니다."
)


def ignored_key_issues(
    document: Mapping[str, Any],
    *,
    message: str = DEFAULT_IGNORED_KEY_MESSAGE,
) -> list[Issue]:
    """옛 프로젝트 파일의 버리는 키(`IGNORED_PROJECT_KEYS`)마다 정보 이슈 `settings.ignored_key`.

    `details` = `{project_id, key}`. 문구는 `string.Template`(변수 project·key).

    >>> old = {"id": "p", "uses": [], "import_mode": "all"}
    >>> [i.details["key"] for i in ignored_key_issues(old)]
    ['uses', 'import_mode']
    """
    pid = document.get("id")
    project = pid if isinstance(pid, str) else ""
    return [
        Issue(
            severity="info",
            code=KnownIssueCodes.SETTINGS_IGNORED_KEY,
            message=string.Template(message).safe_substitute(project=project, key=key),
            details={"project_id": project, "key": key},
        )
        for key in ignored_project_keys(document)
    ]
