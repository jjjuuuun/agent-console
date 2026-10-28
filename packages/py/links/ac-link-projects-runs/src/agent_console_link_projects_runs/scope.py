"""프로젝트 → 설정 층·실행 범위(서버·HTTP 없이 쓰는 부품).

- ``ProjectScope.layers(project_id)``: 프로젝트 층 하나(값 = ``ac-projects.project_layer_value``)와
  경고. 없는 프로젝트면 경고 ``project.unknown`` 하나와 빈 층 목록.
- ``ProjectScope.scope_run(graph, services, *, project_id)``: ``mod-runs`` ``runs.scopes`` 모양.
  노드 서비스 ``SCOPE_LAYERS``(``ac-nodes-core``)에 층을 넣는다. 자식 Run은 부모 서비스를 물려받아
  같은 층(루트 Run의 프로젝트)을 쓴다.
- ``ProjectScope.scope_layers(scope_id)``: ``link-definitions-teams``
  ``settings.scope_layers`` 모양.

층 위치(공통 바로 아래)는 ``ac-teams``가 정한다. 이 모듈은 층 값만 만든다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from string import Template
from typing import Any, Final

from agent_console_contracts import Graph, Issue
from agent_console_nodes_core import SCOPE_LAYERS
from agent_console_projects import CODE_UNKNOWN, project_layer_value
from agent_console_runtime import ServiceKey, Services
from agent_console_teams import Layer

from .ports import ProjectLookup

__all__ = [
    "DEFAULT_LAYER_ID",
    "DEFAULT_LAYER_LABEL",
    "DEFAULT_UNKNOWN_MESSAGE",
    "ProjectScope",
    "RunScopeResult",
    "ScopeLayers",
]

DEFAULT_LAYER_ID: Final = "project"
"""프로젝트 층 id(유효 설정 출처 키). 다른 층 id와 겹치면 안 된다."""

DEFAULT_LAYER_LABEL: Final = "프로젝트"
"""프로젝트 층 화면 이름."""

DEFAULT_UNKNOWN_MESSAGE: Final = (
    "프로젝트 ${project}을(를) 찾을 수 없어 프로젝트 설정 없이 실행합니다."
)
"""없는 프로젝트 경고 문구(``string.Template``, 변수 ``project``)."""

_log = logging.getLogger("agent_console_link_projects_runs")


@dataclass(frozen=True)
class ScopeLayers:
    """범위 하나의 설정 층과 경고(``settings.scope_layers`` 결과 모양)."""

    layers: Sequence[Layer] = ()
    warnings: Sequence[Issue] = ()


@dataclass(frozen=True)
class RunScopeResult:
    """``runs.scopes`` 결과 모양(``mod-runs`` ``RunScope``와 같은 속성)."""

    services: Mapping[ServiceKey[Any], Any] = field(default_factory=dict)
    warnings: Sequence[Issue] = ()


class ProjectScope:
    """프로젝트 id → 프로젝트 층.

    Args:
        lookup: 지금 프로젝트 읽기(``projects.lookup``)를 돌려주는 함수. None을 돌려주면 범위를
            무시한다(층·경고 없음).
        layer_id: 층 id(출처 키).
        layer_label: 층 화면 이름.
        unknown_message: 없는 프로젝트 경고 문구(``string.Template``, 변수 ``project``).

    >>> from agent_console_contracts import Project
    >>> class Lookup:
    ...     def get_project(self, project_id):
    ...         if project_id == "app":
    ...             return Project(id="app", name="App", folder="/w/app")
    ...         return None
    >>> scope = ProjectScope(lambda: Lookup())
    >>> found = scope.layers("app")
    >>> [(layer.id, dict(layer.value or {})) for layer in found.layers]
    [('project', {'working_directory': '/w/app'})]
    >>> [w.code for w in scope.layers("ghost").warnings]
    ['project.unknown']
    """

    def __init__(
        self,
        lookup: Callable[[], ProjectLookup | None],
        *,
        layer_id: str = DEFAULT_LAYER_ID,
        layer_label: str = DEFAULT_LAYER_LABEL,
        unknown_message: str = DEFAULT_UNKNOWN_MESSAGE,
    ) -> None:
        self._lookup = lookup
        self._layer_id = layer_id
        self._layer_label = layer_label
        self._unknown = Template(unknown_message)

    def layers(self, project_id: str | None) -> ScopeLayers:
        """프로젝트 층(값이 비면 ``value=None`` — 아무것도 바꾸지 않는 층)과 경고.

        ``project_id``가 비었거나 프로젝트 읽기가 없으면 빈 결과.
        """
        if not project_id:
            return ScopeLayers()
        lookup = self._lookup()
        if lookup is None:
            return ScopeLayers()
        try:
            project = lookup.get_project(project_id)
        except Exception:  # 제공 모듈의 오류 타입을 모른다 — 없는 것으로 본다
            _log.exception("프로젝트 읽기 실패: %s", project_id)
            project = None
        if project is None:
            return ScopeLayers(warnings=[self._unknown_issue(project_id)])
        value = project_layer_value(project)
        layer = Layer(self._layer_id, self._layer_label, value or None, f"project:{project.id}")
        return ScopeLayers(layers=[layer])

    def scope_layers(self, scope_id: str) -> ScopeLayers:
        """``settings.scope_layers``: 범위 id(= 프로젝트 id) → 층·경고."""
        return self.layers(scope_id)

    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScopeResult | None:
        """``runs.scopes``: 이 Run의 노드 서비스 ``SCOPE_LAYERS``(프로젝트 층)와 경고.

        프로젝트가 없으면(``project_id`` 없음) None. 없는 프로젝트면 경고만(층 없이 실행).
        이미 다른 공급자가 넣은 범위 층이 있으면 그 뒤에 붙인다.
        """
        if not project_id:
            return None
        found = self.layers(project_id)
        if not found.layers:
            return RunScopeResult(warnings=list(found.warnings)) if found.warnings else None
        existing = services.get(SCOPE_LAYERS) or ()
        return RunScopeResult(
            services={SCOPE_LAYERS: (*existing, *found.layers)},
            warnings=list(found.warnings),
        )

    def _unknown_issue(self, project_id: str) -> Issue:
        return Issue(
            severity="warning",
            code=CODE_UNKNOWN,
            message=self._unknown.safe_substitute(project=project_id),
            details={"project": project_id},
        )
