"""link-wiki-runs의 포트(이름 = 포트, design §7R.3·§7R.4·§7R.18 Q14).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다. 아래
프로토콜은 이 모듈이 **받는** 쪽의 모양이다(제공 모듈을 import하지 않는다).

받음:

- 필수 ``wiki.service``: 위키 서비스(``WikiServiceLike`` — ``tool_targets(space)``·
  ``notify(...)``·``wiki_ids(space)``). ``mod-wiki``가 준다. 없으면 이 연동은 꺼진다(실행은 위키
  도구 없이, 위키 칸은 백엔드가 적용하지 못한 칸 경고 R13.5).
- 선택 ``projects.lookup``: 프로젝트 목록(``list_projects()`` → ``id`` 속성). 있으면 저장 전 검사가
  모든 프로젝트 공간의 위키 id도 안다(없으면 단독 공간만).

제공:

- ``runs.scopes``(여러 제공자): Run마다 노드 서비스 ``TOOL_PROVIDERS``(``ac-nodes-core``, X30)에
  위키 도구 공급자를 더한다(``WikiRunScope.scope_run``). 자식 Run은 부모 서비스를 물려받는다.
- ``runs.services``(여러 제공자): 노드 서비스 ``WIKI_UPDATE_SERVICE``(노드 종류 ``wiki-update``가
  쓰는 위키 서비스, ``WikiNodeServices``). 그래프 검증에서도 보이므로 서비스가 없으면 그 노드에
  경고가 난다.
- ``definitions.checks``(여러 제공자): 위키 리소스의 모르는 위키 id 경고(``WikiResourceCheck``).
- ``wiki.integrations``(여러 제공자): ``{id, capabilities={"runs"}}`` — ``mod-wiki``의
  ``WikiCapabilities.runs``가 참이 된다(웹이 실행 연동 켜짐을 모듈 id 없이 안다).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from agent_console_modkit import PortKey
from agent_console_wiki import WikiToolTarget

INTEGRATION_RUNS: Final = "runs"
"""``wiki.integrations`` 능력 이름: 에이전트 쓰기(실행 연동). ``mod-wiki``의 같은 이름 상수와 같은
값이다(코드 개념 — 포트 이름처럼 이름으로만 맞춘다)."""


@runtime_checkable
class WikiServiceLike(Protocol):
    """``wiki.service`` 모양 중 이 연동이 쓰는 부분."""

    def wiki_ids(self, space: str | None) -> list[str]:
        """그 공간의 위키 id(공간을 열 수 없으면 예외)."""
        ...

    def tool_targets(self, space: str | None) -> Mapping[str, WikiToolTarget]:
        """그 공간의 위키 → 도구 대상(저장소·이름·에이전트 작업 폴더 기준 페이지 폴더)."""
        ...

    def notify(
        self,
        space: str | None,
        wiki_id: str,
        paths: Sequence[str] = (),
        *,
        deleted: bool = False,
        external: bool = False,
    ) -> None:
        """WS ``wiki.changed``(저장소로 직접 쓴 뒤)."""
        ...


@runtime_checkable
class ProjectLookupLike(Protocol):
    """``projects.lookup`` 모양 중 이 연동이 쓰는 부분(``list_projects()`` 항목의 ``id``)."""

    def list_projects(self) -> Sequence[Any]:
        """모든 프로젝트."""
        ...


@dataclass(frozen=True)
class WikiRunsIntegration:
    """``wiki.integrations`` 항목(``mod-wiki`` ``WikiIntegration`` 모양)."""

    id: str
    capabilities: Collection[str] = field(default_factory=lambda: frozenset({INTEGRATION_RUNS}))


WIKI_SERVICE: PortKey[WikiServiceLike] = PortKey("wiki.service", "위키 서비스")
PROJECTS_LOOKUP: PortKey[ProjectLookupLike] = PortKey("projects.lookup", "프로젝트 읽기")
RUN_SCOPES: PortKey[Any] = PortKey("runs.scopes", "실행 범위(Run마다 위키 도구 공급자)", multi=True)
RUN_SERVICES: PortKey[Any] = PortKey("runs.services", "노드 서비스(위키 고치기 노드)", multi=True)
DEFINITION_CHECKS: PortKey[Any] = PortKey("definitions.checks", "저장 전 정의 검사", multi=True)
WIKI_INTEGRATIONS: PortKey[Any] = PortKey("wiki.integrations", "위키 연동 능력 선언", multi=True)

__all__ = [
    "DEFINITION_CHECKS",
    "INTEGRATION_RUNS",
    "PROJECTS_LOOKUP",
    "RUN_SCOPES",
    "RUN_SERVICES",
    "WIKI_INTEGRATIONS",
    "WIKI_SERVICE",
    "ProjectLookupLike",
    "WikiRunsIntegration",
    "WikiServiceLike",
]
