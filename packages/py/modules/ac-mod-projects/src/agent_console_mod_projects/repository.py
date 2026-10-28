"""프로젝트 저장(정의 종류 ``project``, ``<workspace>/projects/<id>.yaml``, design §UX-P.4).

이 모듈은 정의 모듈의 종류 목록을 바꾸지 않고 **자기** ``FileDefinitionStore`` 인스턴스로 같은
워크스페이스 루트의 ``projects/`` 폴더를 맡는다(버전 기록소도 같은 DB). 저장 원문은 "생략 = 기본값"
이다(쓰지 않은 키는 파일에 없다).
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import Project, ProjectCreate, ProjectUpdate
from agent_console_store import (
    DefinitionKind,
    DefinitionStore,
    InvalidIdentifier,
    NotFound,
    StoredDefinition,
    StoreError,
)

from .settings import DEFAULT_DIRECTORY

PROJECT_KIND_NAME = "project"
"""프로젝트 정의 종류 이름(계약 ``Project.kind``)."""

CLEARABLE_FIELDS: frozenset[str] = frozenset({"working_directory", "settings"})
"""``ProjectUpdate``에서 null이 "값 지우기(상속)"인 필드. 다른 필드의 null은 생략과 같다."""


def project_kind(directory: str = DEFAULT_DIRECTORY) -> DefinitionKind:
    """프로젝트 정의 종류(모델 ``Project``, 폴더 ``directory``)."""
    # 앱 등록부 종류라 프로젝트 사본 공간에 들어가지 않는다(design §PI.4.2, 5.7R.33w).
    return DefinitionKind(
        name=PROJECT_KIND_NAME, directory=directory, model=Project, portable=False
    )


def create_document(body: ProjectCreate) -> dict[str, Any]:
    """만들기 요청 → 저장 원문(요청에 쓴 키만)."""
    return {"id": body.id, **body.model_dump(mode="json", exclude_unset=True)}


def apply_update(document: dict[str, Any], body: ProjectUpdate) -> dict[str, Any]:
    """저장 원문에 고치기 요청을 반영한 새 원문(입력은 바꾸지 않는다).

    요청에 쓴 필드만 바꾼다. ``working_directory``·``settings``의 null은 키를 지우고(상속),
    그 밖의 null은 무시한다.
    """
    out = copy.deepcopy(document)
    for name in body.model_fields_set:
        value = getattr(body, name)
        if value is None:
            if name in CLEARABLE_FIELDS:
                out.pop(name, None)
            continue
        out[name] = (
            value.model_dump(mode="json", exclude_unset=True)
            if hasattr(value, "model_dump")
            else copy.deepcopy(value)
        )
    return out


class ProjectRepository:
    """프로젝트 CRUD(``projects.lookup`` 포트 구현이기도 하다).

    Args:
        store: 프로젝트 종류(``project_kind``)를 등록한 정의 저장소.
        kind: 종류 이름.
    """

    def __init__(self, store: DefinitionStore, kind: str = PROJECT_KIND_NAME) -> None:
        self.store = store
        self.kind = kind

    # ------------------------------------------------------------ projects.lookup

    def get_project(self, project_id: str) -> Project | None:
        """id의 프로젝트. 없거나 읽을 수 없으면 None."""
        try:
            return self.store.get(self.kind, project_id).model(Project)
        except (StoreError, ValidationError):
            return None

    def list_projects(self) -> list[Project]:
        """모든 프로젝트(id 순). 읽을 수 없는 파일은 뺀다."""
        out: list[Project] = []
        for project_id in self.store.list_ids(self.kind):
            project = self.get_project(project_id)
            if project is not None:
                out.append(project)
        return out

    # ------------------------------------------------------------ 원문 CRUD

    def ids(self) -> frozenset[str]:
        """읽을 수 있는 프로젝트 id."""
        return frozenset(p.id for p in self.list_projects())

    def documents(self) -> list[StoredDefinition]:
        """저장 원문 전부(id 순, 읽을 수 없거나 모델에 맞지 않는 파일은 뺀다)."""
        out: list[StoredDefinition] = []
        for project_id in self.store.list_ids(self.kind):
            try:
                stored = self.store.get(self.kind, project_id)
                stored.model(Project)
            except (StoreError, ValidationError):
                continue
            out.append(stored)
        return out

    def get(self, project_id: str) -> StoredDefinition:
        """저장 원문. 없으면 ``NotFound``."""
        try:
            return self.store.get(self.kind, project_id)
        except InvalidIdentifier as exc:
            raise NotFound(f"프로젝트를 찾을 수 없습니다: {project_id}") from exc

    def require(self, project_id: str) -> Project:
        """프로젝트 모델. 없으면 ``NotFound``."""
        return self.get(project_id).model(Project)

    def create(self, body: ProjectCreate) -> StoredDefinition:
        """만들기. 같은 id가 있으면 ``AlreadyExists``."""
        return self.store.create(self.kind, create_document(body))

    def update(
        self, project_id: str, body: ProjectUpdate, *, expected_version: str | None = None
    ) -> StoredDefinition:
        """고치기(요청에 쓴 필드만). 기대 버전이 지금과 다르면 ``VersionConflict``."""
        stored = self.get(project_id)
        return self.store.save(
            self.kind,
            apply_update(stored.document, body),
            expected_version=expected_version or stored.version_hash,
        )

    def delete(self, project_id: str, *, expected_version: str | None = None) -> None:
        """삭제(버전 이력은 남는다)."""
        self.store.delete(self.kind, project_id, expected_version=expected_version)


__all__ = [
    "CLEARABLE_FIELDS",
    "PROJECT_KIND_NAME",
    "ProjectRepository",
    "apply_update",
    "create_document",
    "project_kind",
]
