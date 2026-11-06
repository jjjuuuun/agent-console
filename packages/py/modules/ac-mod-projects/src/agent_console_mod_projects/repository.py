"""앱 등록부(정의 종류 ``project``, ``<workspace>/projects/<id>.yaml``, design §PI.2 K33-1).

등록부에는 폴더·보관 상태·라벨만 담는다(``ProjectRegistration``). 이름·설명·프로젝트 층은 폴더
매니페스트에 있다. 옛(0.11 이하) 파일의 ``name``·``description``·``settings``는 모르는 키로 남아
있고 첫 저장 때 매니페스트로 옮긴다. 이 모듈은 정의 모듈의 종류 목록을 바꾸지 않고 **자기**
``FileDefinitionStore`` 인스턴스로 같은 워크스페이스 루트의 ``projects/`` 폴더를 맡는다.
"""

from __future__ import annotations

from pydantic import ValidationError

from agent_console_contracts import ProjectRegistration
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
"""등록부 정의 종류 이름(계약 ``ProjectRegistration.kind``)."""


def project_kind(directory: str = DEFAULT_DIRECTORY) -> DefinitionKind:
    """등록부 종류(모델 ``ProjectRegistration``, 폴더 ``directory``).

    앱 등록부 종류라 프로젝트 사본 공간에 들어가지 않는다(``portable=False``, design §PI.4.2).
    """
    return DefinitionKind(
        name=PROJECT_KIND_NAME, directory=directory, model=ProjectRegistration, portable=False
    )


class ProjectRepository:
    """등록부 읽기·쓰기(파일 원문 그대로, "생략 = 기본값").

    Args:
        store: 등록부 종류(``project_kind``)를 등록한 정의 저장소.
        kind: 종류 이름.
    """

    def __init__(self, store: DefinitionStore, kind: str = PROJECT_KIND_NAME) -> None:
        self.store = store
        self.kind = kind

    def documents(self) -> list[StoredDefinition]:
        """읽을 수 있는 등록부 원문 전부(id 순, 깨졌거나 모양이 틀린 파일은 뺀다)."""
        out: list[StoredDefinition] = []
        for project_id in self.store.list_ids(self.kind):
            try:
                stored = self.store.get(self.kind, project_id)
                stored.model(ProjectRegistration)
            except (StoreError, ValidationError):
                continue
            out.append(stored)
        return out

    def registrations(self) -> list[ProjectRegistration]:
        """등록부 모델 전부(id 순)."""
        return [s.model(ProjectRegistration) for s in self.documents()]

    def ids(self) -> frozenset[str]:
        """읽을 수 있는 등록 id."""
        return frozenset(s.id for s in self.documents())

    def get(self, project_id: str) -> StoredDefinition:
        """등록부 원문. 없으면 ``NotFound``."""
        try:
            return self.store.get(self.kind, project_id)
        except InvalidIdentifier as exc:
            raise NotFound(f"프로젝트를 찾을 수 없습니다: {project_id}") from exc

    def find(self, project_id: str) -> StoredDefinition | None:
        """등록부 원문. 없거나 읽을 수 없으면 None."""
        try:
            stored = self.get(project_id)
            stored.model(ProjectRegistration)
        except (StoreError, ValidationError):
            return None
        return stored

    def require(self, project_id: str) -> ProjectRegistration:
        """등록부 모델. 없으면 ``NotFound``."""
        return self.get(project_id).model(ProjectRegistration)

    def create(self, document: dict[str, object]) -> StoredDefinition:
        """새 등록. 같은 id가 있으면 ``AlreadyExists``."""
        return self.store.create(self.kind, document)

    def save(self, document: dict[str, object], *, expected_version: str) -> StoredDefinition:
        """등록부를 덮어쓴다(기대 버전이 다르면 ``VersionConflict``)."""
        return self.store.save(self.kind, document, expected_version=expected_version)


__all__ = ["PROJECT_KIND_NAME", "ProjectRepository", "project_kind"]
