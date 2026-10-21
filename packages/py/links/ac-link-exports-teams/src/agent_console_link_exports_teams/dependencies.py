"""정의가 쓰는 정의(``exports.dependencies``): 팀 구성 → 에이전트·리소스, 에이전트 → 리소스.

계산은 ``ac-teams``(``graph_dependencies``·``agent_dependencies``). 팀 구성은 디스크립터
(``TeamCatalog``)로 해석한다. 다른 종류는 의존이 없다(빈 목록).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from agent_console_contracts import Agent, Graph, WorkspaceSettings
from agent_console_store import AGENT_KIND, GRAPH_KIND
from agent_console_teams import (
    DefinitionDependency,
    TeamCatalog,
    agent_dependencies,
    graph_dependencies,
)

from .ports import DefinitionLookup


class TeamExportDependencies:
    """``exports.dependencies`` 구현.

    Args:
        lookup: 정의 읽기.
        catalog: 지금 디스크립터 묶음.
        workspace: 지금 공통 설정(없으면 None — 공통 층 첨부는 넣지 않는다).
    """

    def __init__(
        self,
        lookup: DefinitionLookup,
        *,
        catalog: Callable[[], TeamCatalog] = TeamCatalog,
        workspace: Callable[[], WorkspaceSettings | None] = lambda: None,
    ) -> None:
        self._lookup = lookup
        self._catalog = catalog
        self._workspace = workspace

    def dependencies(self, kind: str, id: str) -> Sequence[DefinitionDependency]:
        if kind == GRAPH_KIND.name:
            graph = Graph.model_validate(self._lookup.get(kind, id).document)
            return graph_dependencies(self._catalog().plan(graph), workspace=self._workspace())
        if kind == AGENT_KIND.name:
            agent = Agent.model_validate(self._lookup.get(kind, id).document)
            return agent_dependencies(agent, workspace=self._workspace())
        return []


__all__ = ["TeamExportDependencies"]
