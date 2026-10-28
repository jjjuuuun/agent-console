"""mod-projects의 공개 포트·토픽(이름 = 포트, design §UX-P.5).

제공:

- ``projects.lookup``: 프로젝트 읽기(``ProjectLookup`` — ``get_project``·``list_projects``).
  실행 준비 층 공급(``link-projects-runs``) 등이 이름으로 받는다.
- ``projects.folders``(5.7R.30 후속): 등록된 프로젝트 폴더(``ProjectFolderSet`` — 현재·전체).
  로그 수집 범위 등 "앱의 프로젝트 폴더만" 다루는 기능이 이름으로 받는다.
- ``definitions.checks``(여러 제공자): 정의 저장 전 범위 검사(경고·정보만, 저장을 막지 않음).
  정의 읽기 포트가 없으면 빈 목록을 낸다(사실상 꺼짐).

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``definitions.lookup``: 정의 읽기. 없으면 ``definitions.store``로 읽는다. 둘 다 없으면 범위
  검사·옮기기 계획이 "정의를 읽을 수 없음" 정보로 바뀌고 프로젝트 CRUD만 동작한다.
- ``definitions.store``: 정의 쓰기(옮기기 적용·프로젝트 삭제 때 정의 처리). 없으면 그 동작이
  409 ``feature_unavailable``.
- ``definitions.references``(여러 제공자, X25): 참조 추출. 없으면 참조 규칙 대신
  ``project.references_unavailable`` 정보.
- 토픽 ``definitions.saved``: 받으면 정의 스냅샷 캐시를 버린다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue, Project
from agent_console_modkit import PortKey, Topic
from agent_console_projects import ProjectFolderSet


class StoredLike(Protocol):
    """저장된 정의 하나(문서·버전)."""

    @property
    def document(self) -> dict[str, Any]: ...

    @property
    def version_hash(self) -> str: ...


@runtime_checkable
class DefinitionReader(Protocol):
    """정의 읽기(``definitions.lookup`` 모양의 일부). 없는 정의는 저장소 예외(``NotFound``)."""

    def kinds(self) -> list[str]: ...

    def list_ids(self, kind: str) -> list[str]: ...

    def get(self, kind: str, id: str) -> StoredLike: ...


@runtime_checkable
class DefinitionWriter(DefinitionReader, Protocol):
    """정의 쓰기(``definitions.store`` 모양의 일부)."""

    def save(
        self,
        kind: str,
        document: Mapping[str, Any],
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> StoredLike: ...

    def delete(self, kind: str, id: str, *, expected_version: str | None = None) -> None: ...


@runtime_checkable
class DefinitionCheck(Protocol):
    """``definitions.checks`` 모양."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]: ...


@runtime_checkable
class ProjectLookup(Protocol):
    """``projects.lookup`` 모양: 프로젝트 읽기."""

    def get_project(self, project_id: str) -> Project | None:
        """id의 프로젝트. 없거나 읽을 수 없으면 None."""
        ...

    def list_projects(self) -> list[Project]:
        """모든 프로젝트(id 순, 읽을 수 없는 파일은 뺀다)."""
        ...


class References(Protocol):
    """``definitions.references`` 모양(X25): 문서 하나가 쓰는 정의의 ``(종류, id)``."""

    def __call__(self, kind: str, document: Mapping[str, Any]) -> Iterable[tuple[str, str]]: ...


class SavedLike(Protocol):
    """``definitions.saved`` 항목 모양(``kind``·``id``·``version_hash``)."""

    @property
    def kind(self) -> str: ...

    @property
    def id(self) -> str: ...


PROJECTS_LOOKUP: PortKey[ProjectLookup] = PortKey("projects.lookup", "프로젝트 읽기")
PROJECT_FOLDERS: PortKey[Callable[[], ProjectFolderSet]] = PortKey(
    "projects.folders", "앱에 등록된 프로젝트 폴더(현재·전체)"
)
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)
DEFINITIONS_LOOKUP: PortKey[DefinitionReader] = PortKey("definitions.lookup", "정의 읽기")
DEFINITIONS_STORE: PortKey[DefinitionWriter] = PortKey("definitions.store", "정의 저장소")
DEFINITIONS_REFERENCES: PortKey[References] = PortKey(
    "definitions.references", "정의 문서의 참조 추출(X25)", multi=True
)
DEFINITIONS_SAVED: Topic[SavedLike] = Topic("definitions.saved")

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_REFERENCES",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "PROJECTS_LOOKUP",
    "PROJECT_FOLDERS",
    "DefinitionCheck",
    "DefinitionReader",
    "DefinitionWriter",
    "ProjectLookup",
    "References",
    "SavedLike",
    "StoredLike",
]
