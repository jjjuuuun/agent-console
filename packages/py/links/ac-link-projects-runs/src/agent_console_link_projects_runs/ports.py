"""link-projects-runs의 포트(이름 = 포트, design §UX-P.5·§5.2R.6).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다. 아래 프로토콜은
이 모듈이 **받는** 쪽의 모양이다(제공 모듈을 import하지 않는다).

받음:

- 필수 ``projects.lookup``: 프로젝트 읽기(``ProjectLookup`` — ``get_project``). ``mod-projects``가
  준다. 없으면 이 연동은 꺼진다(실행은 프로젝트 층 없이, 지금과 같음).

제공:

- ``runs.scopes``(여러 제공자): 실행 범위(``ProjectScope.scope_run``). ``mod-runs``가 실행을 시작할
  때 요청 ``project_id``로 부른다 → 노드 서비스 ``SCOPE_LAYERS``(``ac-nodes-core``)에 프로젝트 층을
  넣는다. 없는 프로젝트면 경고 ``project.unknown``(Run 이벤트 ``log.warning``) 후 층 없이.
- ``settings.scope_layers``(여러 제공자): 범위 id → 설정 층(``ProjectScope.scope_layers``).
  ``link-definitions-teams`` 유효 설정 경로의 ``?project=``가 쓴다.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Project
from agent_console_modkit import PortKey


@runtime_checkable
class ProjectLookup(Protocol):
    """``projects.lookup`` 모양의 쓰는 부분: 프로젝트 읽기."""

    def get_project(self, project_id: str) -> Project | None:
        """id의 프로젝트. 없거나 읽을 수 없으면 None."""
        ...


PROJECTS_LOOKUP: PortKey[ProjectLookup] = PortKey("projects.lookup", "프로젝트 읽기")
RUN_SCOPES: PortKey[Any] = PortKey("runs.scopes", "실행 범위(요청 project_id)", multi=True)
SCOPE_LAYERS: PortKey[Any] = PortKey(
    "settings.scope_layers", "범위 id → 설정 층(예: 프로젝트 층)", multi=True
)

__all__ = ["PROJECTS_LOOKUP", "RUN_SCOPES", "SCOPE_LAYERS", "ProjectLookup"]
