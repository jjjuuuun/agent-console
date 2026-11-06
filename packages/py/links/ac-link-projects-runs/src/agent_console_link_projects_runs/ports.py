"""link-projects-runs의 포트(이름 = 포트, design §UX-P.5·§5.2R.6).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다. 아래 프로토콜은
이 모듈이 **받는** 쪽의 모양이다(제공 모듈을 import하지 않는다).

받음:

- 필수 ``projects.lookup``: 프로젝트 읽기(``ProjectLookup`` — ``get_project``). ``mod-projects``가
  준다. 없으면 이 연동은 꺼진다(실행은 프로젝트 층 없이, 지금과 같음). 같은 객체가 선택 메서드
  ``get_view``(``ProjectViews``)를 가지면 실행 전 상태·기록 DB 점검에 쓴다(5.7R.33g).
- 선택 ``definitions.spaces``: 등록 id → 그 프로젝트 공간의 정의 저장소(``DefinitionSpaces``).
  있으면 Run의 정의 조회 출처 = 그 공간(X26 ``run_definitions``, 5.7R.33g). 없으면 출처를 정하지
  않는다.
- 선택 ``definitions.lookup``: 라이브러리 정의 읽기. ``project.not_imported``의 ``in_library``만
  정한다(실행에는 쓰지 않는다, K33-18).

제공:

- ``runs.scopes``(여러 제공자): 실행 범위(``ProjectScope.scope_run``). ``mod-runs``가 실행을 시작할
  때 요청 ``project_id``로 부른다 → 노드 서비스 ``SCOPE_LAYERS``(``ac-nodes-core``)에 프로젝트 층을
  넣는다. 사전 점검(5.7R.33g): 정의 출처(``run_definitions`` — 없는 프로젝트 404, 상태 409,
  공간에 없는 실행 대상 422 ``project.not_imported``)와 범위 결과의 거부(``errors`` —
  ``project.required``·``project.records_unavailable``·``project.outside_folder``).
- ``settings.scope_layers``(여러 제공자): 범위 id → 설정 층(``ProjectScope.scope_layers``).
  ``link-definitions-teams`` 유효 설정 경로의 ``?project=``가 쓴다.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Project, ProjectView
from agent_console_modkit import PortKey


@runtime_checkable
class ProjectLookup(Protocol):
    """``projects.lookup`` 모양의 쓰는 부분: 프로젝트 읽기."""

    def get_project(self, project_id: str) -> Project | None:
        """id의 프로젝트. 없거나 읽을 수 없으면 None."""
        ...


@runtime_checkable
class ProjectViews(Protocol):
    """``projects.lookup`` 객체의 **선택** 메서드: 프로젝트와 상태(``ProjectView``)."""

    def get_view(self, project_id: str) -> ProjectView:
        """상태·쓰기 가능·기록 DB 상태. 모르는 프로젝트면 예외(저장소 ``NotFound`` 등)."""
        ...


class DefinitionReader(Protocol):
    """정의 읽기(``definitions.lookup``·공간 저장소 모양의 쓰는 부분). 없으면 예외."""

    def get(self, kind: str, id: str) -> Any: ...


class DefinitionSpaces(Protocol):
    """``definitions.spaces`` 모양: 공간 이름(등록 id) → 정의 저장소."""

    def open(self, project_id: str) -> Any:
        """그 공간의 정의 저장소(``agent_console_store`` 정의 저장소 — ``mod-runs``
        ``DefinitionSource``를 만족). 모르는 프로젝트 ``LookupError``, 폴더 없음 등은 ``code``를
        가진 저장소 예외."""
        ...


PROJECTS_LOOKUP: PortKey[ProjectLookup] = PortKey("projects.lookup", "프로젝트 읽기")
DEFINITIONS_SPACES: PortKey[DefinitionSpaces] = PortKey(
    "definitions.spaces", "공간 이름(등록 id) → 정의 저장소"
)
DEFINITIONS_LOOKUP: PortKey[DefinitionReader] = PortKey("definitions.lookup", "정의 읽기")
RUN_SCOPES: PortKey[Any] = PortKey("runs.scopes", "실행 범위(요청 project_id)", multi=True)
SCOPE_LAYERS: PortKey[Any] = PortKey(
    "settings.scope_layers", "범위 id → 설정 층(예: 프로젝트 층)", multi=True
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SPACES",
    "PROJECTS_LOOKUP",
    "RUN_SCOPES",
    "SCOPE_LAYERS",
    "DefinitionReader",
    "DefinitionSpaces",
    "ProjectLookup",
    "ProjectViews",
]
