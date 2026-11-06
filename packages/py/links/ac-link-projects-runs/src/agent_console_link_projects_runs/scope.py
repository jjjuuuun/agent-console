"""프로젝트 → 설정 층·실행 범위(서버·HTTP 없이 쓰는 부품).

- ``ProjectScope.layers(project_id)``: 프로젝트 층 하나(값 = ``ac-projects.project_layer_value``)와
  경고. 없는 프로젝트면 경고 ``project.unknown`` 하나와 빈 층 목록.
- ``ProjectScope.scope_run(graph, services, *, project_id)``: ``mod-runs`` ``runs.scopes`` 모양.
  노드 서비스 ``SCOPE_LAYERS``(``ac-nodes-core``)에 층을 넣는다. 자식 Run은 부모 서비스를 물려받아
  같은 층(루트 Run의 프로젝트)을 쓴다.
- ``ProjectScope.scope_layers(scope_id)``: ``link-definitions-teams``
  ``settings.scope_layers`` 모양.
- ``ProjectScope.run_definitions(project_id, graph_id)``(5.7R.33g, X26 선택 메서드): Run의 정의 조회
  출처 = 그 프로젝트 공간. 그래프를 읽기 전에 막을 것 — 없는 프로젝트(404 ``project.not_found``),
  상태(409 ``project.folder_missing``·``project.manifest_invalid``), 실행 대상이 공간에 없음(422
  ``project.not_imported``, ``in_library``). 라이브러리로 넘어가 찾지 않는다(K33-18).
- ``scope_run``의 거부 ``errors``(5.7R.33g): 프로젝트 없이 시작(422 ``project.required``), 기록
  DB를 쓸 수 없음(409 ``project.records_unavailable``, K33-34), 유효 설정의 경로가 폴더 밖(422
  ``project.outside_folder``, §PI.5). Run 당시 그래프 보기(``graph_of_run``)는 ``run_definitions``만
  부르므로 기록 DB를 쓸 수 없는 프로젝트의 지난 Run도 볼 수 있다.

층 위치(공통 바로 아래)는 ``ac-teams``가 정한다. 이 모듈은 층 값만 만든다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from string import Template
from typing import Any, Final

from agent_console_contracts import (
    ErrorInfo,
    Graph,
    Issue,
    KnownProjectStatuses,
    Project,
    WorkspaceSettings,
)
from agent_console_nodes_core import AGENT_LOOKUP, SCOPE_LAYERS, WORKSPACE_SETTINGS
from agent_console_projects import CODE_UNKNOWN, project_layer_value
from agent_console_runtime import ServiceKey, Services
from agent_console_teams import DEFAULT_CONVENTIONS, Layer, TeamCatalog

from .ports import DefinitionReader, DefinitionSpaces, ProjectLookup, ProjectViews
from .preflight import (
    DEFAULT_PREFLIGHT_TEXTS,
    PreflightTexts,
    not_imported_error,
    outside_folder_error,
    outside_paths_of_graph,
    required_error,
    space_error,
    unknown_error,
    view_error,
)

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
    """``runs.scopes`` 결과 모양(``mod-runs`` ``RunScope``와 같은 속성).

    ``errors``(5.7R.33g, X26 거부)가 있으면 ``mod-runs``가 첫 오류로 Run을 만들지 않고 거부한다.
    """

    services: Mapping[ServiceKey[Any], Any] = field(default_factory=dict)
    warnings: Sequence[Issue] = ()
    errors: Sequence[ErrorInfo] = ()


def _not_found(exc: Exception) -> bool:
    return isinstance(exc, LookupError) or getattr(exc, "code", None) == "not_found"


class ProjectScope:
    """프로젝트 id → 프로젝트 층.

    Args:
        lookup: 지금 프로젝트 읽기(``projects.lookup``)를 돌려주는 함수. None을 돌려주면 범위를
            무시한다(층·경고 없음).
        layer_id: 층 id(출처 키).
        layer_label: 층 화면 이름.
        unknown_message: 없는 프로젝트 경고 문구(``string.Template``, 변수 ``project``).
        spaces: 지금 ``definitions.spaces``(등록 id → 공간 정의 저장소)를 돌려주는 함수. None을
            돌려주면 정의 출처를 정하지 않는다(라이브러리 그대로).
        library: 지금 ``definitions.lookup``(라이브러리)을 돌려주는 함수. ``in_library``만 정한다.
        catalog: 노드·백엔드 디스크립터를 돌려주는 함수(경로 지킴). None이면 경로 지킴을 하지
            않는다.
        allowed: 경로 지킴에서 함께 허용하는 폴더(앱 workspace·상태 폴더, 절대 경로).
        environ: ``~`` 펼치기용 환경.
        require_project: 참이면 ``project_id`` 없는 실행을 422 ``project.required``로 거부한다.
        graph_kind: 실행 대상(루트 팀 구성)의 정의 종류 이름.
        texts: 사전 점검 오류 문구·해결 버튼.

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
        spaces: Callable[[], DefinitionSpaces | None] | None = None,
        library: Callable[[], DefinitionReader | None] | None = None,
        catalog: Callable[[], TeamCatalog] | None = None,
        allowed: Sequence[str] = (),
        environ: Mapping[str, str] | None = None,
        require_project: bool = False,
        graph_kind: str = DEFAULT_CONVENTIONS.team_kind,
        texts: PreflightTexts = DEFAULT_PREFLIGHT_TEXTS,
    ) -> None:
        self._lookup = lookup
        self._layer_id = layer_id
        self._layer_label = layer_label
        self._unknown = Template(unknown_message)
        self._spaces = spaces or (lambda: None)
        self._library = library or (lambda: None)
        self._catalog = catalog
        self._allowed = tuple(allowed)
        self._environ = dict(environ or {})
        self._require = require_project
        self._graph_kind = graph_kind
        self._texts = texts

    def _project(self, lookup: ProjectLookup, project_id: str) -> Project | None:
        try:
            return lookup.get_project(project_id)
        except Exception:  # 제공 모듈의 오류 타입을 모른다 — 없는 것으로 본다
            _log.exception("프로젝트 읽기 실패: %s", project_id)
            return None

    def _view_error(
        self, lookup: ProjectLookup, project_id: str, *, records: bool
    ) -> ErrorInfo | None:
        """프로젝트 상태(``records``면 기록 DB까지)로 막을 오류. 상태를 읽을 수 없으면 None."""
        if not isinstance(lookup, ProjectViews):
            return None
        try:
            view = lookup.get_view(project_id)
        except Exception as exc:
            if _not_found(exc):
                return unknown_error(project_id, self._texts)
            _log.exception("프로젝트 상태 읽기 실패: %s", project_id)
            return None
        if not records and view.status == KnownProjectStatuses.READY:
            return None  # 정의 출처 단계는 상태만 본다(지난 Run 보기는 기록 DB와 무관)
        return view_error(view, self._texts)

    def layers(self, project_id: str | None) -> ScopeLayers:
        """프로젝트 층(값이 비면 ``value=None`` — 아무것도 바꾸지 않는 층)과 경고.

        ``project_id``가 비었거나 프로젝트 읽기가 없으면 빈 결과.
        """
        if not project_id:
            return ScopeLayers()
        lookup = self._lookup()
        if lookup is None:
            return ScopeLayers()
        project = self._project(lookup, project_id)
        if project is None:
            return ScopeLayers(warnings=[self._unknown_issue(project_id)])
        value = project_layer_value(project)
        layer = Layer(self._layer_id, self._layer_label, value or None, f"project:{project.id}")
        return ScopeLayers(layers=[layer])

    def scope_layers(self, scope_id: str) -> ScopeLayers:
        """``settings.scope_layers``: 범위 id(= 프로젝트 id) → 층·경고."""
        return self.layers(scope_id)

    def run_definitions(self, project_id: str, graph_id: str) -> Any:
        """X26 ``run_definitions``: Run의 정의 조회 출처 = 그 프로젝트 공간의 정의 저장소.

        ``definitions.spaces``가 없으면 None(출처를 정하지 않음). 막을 때는 오류 본문:
        없는 프로젝트 404 ``project.not_found``, 상태가 ``ready``가 아님 409
        ``project.folder_missing``·``project.manifest_invalid``(공간을 열 수 없을 때도),
        실행 대상이 공간에 없음 422 ``project.not_imported``(``in_library`` = 라이브러리에 있음).
        """
        lookup = self._lookup()
        if lookup is None:
            return None
        project = self._project(lookup, project_id)
        if project is None:
            return unknown_error(project_id, self._texts)
        error = self._view_error(lookup, project_id, records=False)
        if error is not None:
            return error
        spaces = self._spaces()
        if spaces is None:
            return None
        try:
            store = spaces.open(project_id)
        except Exception as exc:
            if isinstance(exc, LookupError):
                return unknown_error(project_id, self._texts)
            return space_error(project_id, exc, folder=project.folder, texts=self._texts)
        try:
            store.get(self._graph_kind, graph_id)
        except Exception as exc:
            if not _not_found(exc):
                return space_error(project_id, exc, folder=project.folder, texts=self._texts)
            return not_imported_error(
                project_id,
                self._graph_kind,
                graph_id,
                in_library=self._in_library(graph_id),
                texts=self._texts,
            )
        return store

    def _in_library(self, graph_id: str) -> bool:
        library = self._library()
        if library is None:
            return False
        try:
            library.get(self._graph_kind, graph_id)
        except Exception:
            return False
        return True

    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScopeResult | None:
        """``runs.scopes``: 이 Run의 노드 서비스 ``SCOPE_LAYERS``(프로젝트 층)·경고·거부.

        프로젝트가 없으면(``project_id`` 없음) ``require_project``일 때 거부 ``project.required``,
        아니면 None. 없는 프로젝트면 경고만(층 없이 — 프로젝트 읽기가 있으면 ``run_definitions``가
        먼저 막는다). 이미 다른 공급자가 넣은 범위 층이 있으면 그 뒤에 붙인다. 프로젝트가 있으면
        기록 DB(``records_writable``)와 경로 지킴(유효 설정의 ``x-path`` 값)을 점검해 거부를 싣는다.
        """
        if not project_id:
            if self._require and self._lookup() is not None:
                return RunScopeResult(errors=[required_error(self._texts)])
            return None
        found = self.layers(project_id)
        if not found.layers:
            return RunScopeResult(warnings=list(found.warnings)) if found.warnings else None
        existing = tuple(services.get(SCOPE_LAYERS) or ())
        layers = (*existing, *found.layers)
        errors = self._start_errors(graph, services, project_id, layers)
        return RunScopeResult(
            services={SCOPE_LAYERS: layers},
            warnings=list(found.warnings),
            errors=errors,
        )

    def _start_errors(
        self, graph: Graph, services: Services, project_id: str, layers: Sequence[Layer]
    ) -> list[ErrorInfo]:
        lookup = self._lookup()
        if lookup is None:
            return []
        error = self._view_error(lookup, project_id, records=True)
        if error is not None:
            return [error]
        project = self._project(lookup, project_id)
        folder = project.folder if project is not None else None
        if not folder or self._catalog is None:
            return []
        workspace = services.get(WORKSPACE_SETTINGS)
        paths = outside_paths_of_graph(
            graph,
            catalog=self._catalog(),
            folder=folder,
            allowed=self._allowed,
            find_agent=services.get(AGENT_LOOKUP),
            workspace=workspace if isinstance(workspace, WorkspaceSettings) else None,
            scope_layers=layers,
            placeholders={"workspace": folder},
            environ=self._environ,
        )
        if paths:
            return [outside_folder_error(project_id, folder, paths, self._texts)]
        return []

    def _unknown_issue(self, project_id: str) -> Issue:
        return Issue(
            severity="warning",
            code=CODE_UNKNOWN,
            message=self._unknown.safe_substitute(project=project_id),
            details={"project": project_id},
        )
