"""정의 문서가 쓰는 정의(``definitions.dependencies``): 팀 구성 → 에이전트·리소스·자식 팀 구성,
에이전트 → 리소스. 같은 계산을 참조 추출 함수 모양(``definitions.references``, X25)으로도 낸다.

저장되기 전 문서(예: 가져올 항목)에서 바로 계산한다. 계산은 ``ac-teams``(``graph_dependencies``·
``agent_dependencies``), 팀 구성은 지금 디스크립터(``TeamCatalog``)로 해석한다. 정의 종류 이름은
``TeamConventions``(데이터)에서 읽는다. 다른 종류는 의존이 없다(빈 목록).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import Agent, Graph
from agent_console_teams import (
    DEFAULT_CONVENTIONS,
    DefinitionDependency,
    TeamCatalog,
    TeamConventions,
    agent_dependencies,
    graph_dependencies,
)

__all__ = ["TeamDocumentDependencies"]


class TeamDocumentDependencies:
    """``definitions.dependencies`` 구현.

    Args:
        catalog: 지금 디스크립터 묶음을 돌려주는 함수.
        conventions: 정의 종류 이름·config 키 약속(기본 ``DEFAULT_CONVENTIONS``).
    """

    def __init__(
        self,
        catalog: Callable[[], TeamCatalog],
        *,
        conventions: TeamConventions = DEFAULT_CONVENTIONS,
    ) -> None:
        self._catalog = catalog
        self._c = conventions

    def dependencies_of(
        self, kind: str, document: Mapping[str, Any]
    ) -> Sequence[DefinitionDependency]:
        """``kind`` 문서가 쓰는 정의(공통 층 첨부는 넣지 않는다 — 문서 밖 설정이다).

        Raises:
            pydantic.ValidationError: 문서가 그 종류 모델에 맞지 않을 때.
        """
        if kind == self._c.team_kind:
            graph = Graph.model_validate(dict(document))
            return graph_dependencies(
                self._catalog().plan(graph, conventions=self._c), conventions=self._c
            )
        if kind == self._c.agent_kind:
            agent = Agent.model_validate(dict(document))
            return agent_dependencies(agent, conventions=self._c)
        return []

    def references(self, kind: str, document: Mapping[str, Any]) -> list[tuple[str, str]]:
        """``definitions.references``(X25) 모양: 문서가 쓰는 정의의 ``(종류, id)``.

        중복은 빼고 처음 나온 순서를 지킨다.

        ``dependencies_of``와 같은 계산이다. 모르는 종류·모델에 맞지 않는 문서는 빈 목록(예외 없음 —
        범위 검사 같은 소비자가 문서 하나 때문에 멈추지 않게 한다).
        """
        try:
            found = self.dependencies_of(kind, document)
        except ValidationError:
            return []
        return list(dict.fromkeys((d.kind, d.id) for d in found))
