"""팀 규칙을 실행에 잇는 부품.

실행 전 검사·사전 점검(``preflight`` — 실행 백엔드가 빈 노드면 ``backend.unresolved``)·준비
(``runs.preparers``), 노드 서비스(``runs.services``), 팀 구성 목록 검증 요약
(``graphs.validation``).

계산은 ``ac-teams``(``validate_team``·``merge_validation``·``prepare_run``·``validation_summary``)에
있다. 여기서는 정의 읽기·공통 설정·리소스·디스크립터(플러그인 레지스트리)를 모아 넘긴다. FastAPI를
모른다. 실행 모듈(``mod-runs``)의 프로토콜은 구조적으로 만족한다(그 패키지를 import하지 않는다).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from pydantic import ValidationError

from agent_console_contracts import (
    Agent,
    ErrorInfo,
    Fix,
    Graph,
    GraphValidationSummary,
    Issue,
    WorkspaceSettings,
)
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    DEFAULT_BACKEND,
    ERROR_FIXES,
    RESOURCE_LOOKUP,
    RUN_FILES_ROOT,
    SCOPE_LAYERS,
    TEAM_LOOKUP,
    WORKING_DIRECTORY,
)
from agent_console_nodes_core import WORKSPACE_SETTINGS as WORKSPACE_SETTINGS_SERVICE
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType, new_resource_types
from agent_console_runtime import Registries, ServiceKey, Services, port_resolver
from agent_console_store import AGENT_KIND, StoreError
from agent_console_teams import (
    DEFAULT_CONVENTIONS,
    Layer,
    RunPreparation,
    TeamCatalog,
    TeamPlan,
    merge_validation,
    prepare_run,
    resolve_backends,
    team_rules_apply,
    team_settings,
    unresolved_backends,
    validate_team,
    validation_summary,
)

from .cache import GraphValidationCache, workspace_revision
from .fixes import DEFAULT_ISSUE_FIXES, IssueFixes
from .ports import DefinitionLookup, GraphLoader, RunChecker
from .preflight import DEFAULT_BACKEND_FIX_TEXTS, BackendFixTexts, backend_unresolved_error

_log = logging.getLogger("agent_console_link_runs_teams")

RUN_CONTEXT_CWD: Final = "cwd"
"""Run 맥락(``run.started`` payload)에서 유효 작업 폴더 키. 로그 대응표(``ac-link-logs-runs``
``run_event_map.yaml``)가 같은 키를 읽는다(바꾸려면 ``TeamRules(cwd_key=)``와 대응표를 함께)."""


@dataclass(frozen=True)
class TeamRunPreparation(RunPreparation):
    """``ac-teams.RunPreparation`` + Run 맥락(``mod-runs`` 준비 결과의 선택 속성
    ``run_context``)."""

    run_context: dict[str, Any] = field(default_factory=dict)


class TeamRules:
    """팀 규칙 검사·실행 준비·노드 서비스.

    Args:
        lookup: 정의 읽기(에이전트 정의).
        catalog: 지금 디스크립터 묶음(``catalog_from_registries``).
        registries: 플러그인 레지스트리 묶음(동적 포트 해석기). 없으면 None.
        workspace: 지금 공통 설정(없으면 기본값).
        resources: 리소스 조회(없으면 None — 리소스 검사·서비스 없이).
        types: 리소스 종류(없으면 빈 레지스트리).
        graphs: 팀 구성 읽기 `(id, 버전 해시 | None) -> Graph`(없으면 예외, 예: ``runs.starter``의
            ``load_graph``). 없으면(None) 중첩 팀 규칙은 자식을 읽지 않고, 노드 서비스
            ``TEAM_LOOKUP``도 넣지 않는다(중첩 팀 노드는 실행 시 ``team.lookup_unavailable``).
        fix_texts: 사전 점검 오류 ``backend.unresolved``의 문구·해결 버튼 데이터.
        issue_fixes: 검증 이슈·노드 실패 코드 → 해결 버튼 표(``annotate_issues``·노드 서비스
            ``ERROR_FIXES``).
        cwd_key: 준비 결과 Run 맥락에서 유효 작업 폴더를 싣는 키(``RUN_CONTEXT_CWD``). None이면
            싣지 않는다.
    """

    def __init__(
        self,
        lookup: DefinitionLookup,
        *,
        catalog: Callable[[], TeamCatalog] = TeamCatalog,
        registries: Callable[[], Any] = lambda: None,
        workspace: Callable[[], WorkspaceSettings | None] = lambda: None,
        resources: Callable[[], ResourceLookup | None] = lambda: None,
        types: Callable[[], Registry[ResourceType] | None] = lambda: None,
        graphs: Callable[[], GraphLoader | None] = lambda: None,
        fix_texts: BackendFixTexts = DEFAULT_BACKEND_FIX_TEXTS,
        issue_fixes: IssueFixes = DEFAULT_ISSUE_FIXES,
        cwd_key: str | None = RUN_CONTEXT_CWD,
    ) -> None:
        self.lookup = lookup
        self._catalog = catalog
        self._registries = registries
        self._workspace = workspace
        self._resources = resources
        self._types = types
        self._graphs = graphs
        self._fix_texts = fix_texts
        self._issue_fixes = issue_fixes
        self._cwd_key = cwd_key
        self._empty_types: Registry[ResourceType] = new_resource_types()

    # ------------------------------------------------------------ 재료

    @property
    def workspace(self) -> WorkspaceSettings:
        return self._workspace() or WorkspaceSettings()

    @property
    def types(self) -> Registry[ResourceType]:
        found = self._types()
        return found if found is not None else self._empty_types

    def find_agent(self, agent_id: str) -> Agent | None:
        """에이전트 정의(읽을 수 없으면 None, 노드 서비스 ``AGENT_LOOKUP``)."""
        try:
            return Agent.model_validate(self.lookup.get(AGENT_KIND.name, agent_id).document)
        except (StoreError, ValidationError):
            return None

    def find_team(self, graph_id: str, version: str | None = None) -> Graph | None:
        """팀 구성(고정 버전이면 그 버전). 읽을 수 없으면 None(노드 서비스 ``TEAM_LOOKUP``·중첩 팀
        규칙의 조회)."""
        loader = self._graphs()
        if loader is None:
            return None
        try:
            return loader(graph_id, version)
        except Exception:  # 제공 모듈의 오류 타입을 모른다(없음·읽기 실패·계약 위반 모두 "없음")
            _log.debug("팀 구성 읽기 실패: %s@%s", graph_id, version, exc_info=True)
            return None

    def team_lookup(self) -> Callable[[str, str | None], Graph | None] | None:
        """중첩 팀 조회 함수(팀 구성 읽기가 없으면 None)."""
        return self.find_team if self._graphs() is not None else None

    def agents_for(self, plan: TeamPlan) -> dict[str, Agent]:
        """팀 구성이 쓰는 에이전트 정의(id → 정의, 없는 것은 빠짐)."""
        found: dict[str, Agent] = {}
        for agent_id in set(plan.agent_refs.values()):
            agent = self.find_agent(agent_id)
            if agent is not None:
                found[agent_id] = agent
        return found

    # ------------------------------------------------------------ runs.services

    def services(self, env: Any) -> dict[ServiceKey[Any], Any]:
        """노드 서비스(``ac-nodes-core`` 키). ``env``는 실행 환경(``working_directory``·
        ``run_files_root``)."""
        workspace = self.workspace
        items: dict[ServiceKey[Any], Any] = {
            AGENT_LOOKUP: self.find_agent,
            WORKING_DIRECTORY: str(env.working_directory),
            WORKSPACE_SETTINGS_SERVICE: workspace,
            RUN_FILES_ROOT: str(env.run_files_root),
            ERROR_FIXES: self.error_fix,
        }
        resources = self._resources()
        if resources is not None:
            items[RESOURCE_LOOKUP] = resources
        if workspace.default_backend:
            items[DEFAULT_BACKEND] = workspace.default_backend
        teams = self.team_lookup()
        if teams is not None:
            items[TEAM_LOOKUP] = teams
        return items

    # ------------------------------------------------------------ runs.preparers

    def team_issues(self, graph: Graph, *, plan: TeamPlan | None = None) -> list[Issue]:
        """팀 구성 의미 검증(그래프 구조 검사는 빼고 — 엔진 검증과 겹치지 않게)."""
        catalog = self._catalog()
        workspace = self.workspace
        p = plan or catalog.plan(graph)
        registries = self._registries()
        return validate_team(
            graph,
            node_types=catalog.node_types,
            edge_types=catalog.edge_types,
            strategies=catalog.strategies.values(),
            agents=self.agents_for(p),
            workspace=workspace,
            backends=catalog.backends,
            settings_validators=catalog.settings_validators,
            default_backend=workspace.default_backend,
            resources=self._resources(),
            resource_types=self.types,
            resolve_ports=port_resolver(registries) if isinstance(registries, Registries) else None,
            graph_checks=False,
            plan=p,
            teams=self.team_lookup(),
        )

    def check(
        self,
        graph: Graph,
        engine_issues: Sequence[Issue],
        services: Services,
        *,
        strict: bool,
    ) -> list[Issue]:
        """엔진 이슈 뒤에 붙일 팀 이슈(같은 노드에 같은 뜻의 엔진 error가 있으면 뺀다).

        모르는 타입이 있으면(``team_rules_apply`` 거짓) 팀 규칙은 건너뛴다. 계산 오류는 그대로
        던진다(``strict``와 무관 — 실행 모듈이 검증 응답이면 기록하고 넘어간다).
        """
        engine = list(engine_issues)
        if not team_rules_apply(engine):
            return []
        merged = merge_validation(engine, self.team_issues(graph))
        return merged[len(engine) :]

    def error_fix(self, code: str, graph: Graph, node_id: str | None) -> Fix | None:
        """노드 실패 해결 버튼(노드 서비스 ``ERROR_FIXES``, 자식 Run의 ``agent.no_backend`` 등)."""
        return self._issue_fixes.fix_for(
            code, team_kind=DEFAULT_CONVENTIONS.team_kind, graph_id=graph.id, node_id=node_id
        )

    def annotate_issues(self, graph: Graph, issues: Sequence[Issue]) -> list[Issue]:
        """검증 이슈(엔진 + 팀 규칙)에 해결 버튼을 붙인다(``mod-runs`` 선택 메서드)."""
        return self._issue_fixes.attach(
            issues, team_kind=DEFAULT_CONVENTIONS.team_kind, graph_id=graph.id
        )

    def preflight(self, graph: Graph, services: Services) -> ErrorInfo | None:
        """실행을 만들기 전 사전 점검(``mod-runs`` 선택 메서드): 실행 백엔드가 빈 노드가 있으면
        ``backend.unresolved`` 오류 본문, 없으면 None.

        해결 순서는 설정 층 그대로(노드 → 에이전트 → 팀 구성 → 공통 → ``default_backend``)다.
        백엔드를 자동으로 고르지 않는다. 위임 방식 디스크립터를 넘겨 자기 세션을 여는 방식
        (``shares_session`` false)의 대상도 세션 주인으로 점검한다. 해석할 수 없는 그래프면
        None(엔진 검증이 맡는다).
        """
        catalog = self._catalog()
        plan = catalog.try_plan(graph)
        if plan is None:
            return None
        workspace = self.workspace
        agents = self.agents_for(plan)
        resolved = resolve_backends(
            plan,
            agents=agents,
            workspace=workspace,
            strategies=catalog.strategies,
            default_backend=workspace.default_backend,
            scope_layers=_scope_layers(services),
        )
        return backend_unresolved_error(
            plan,
            unresolved_backends(plan, resolved, agents=agents, strategies=catalog.strategies),
            catalog.backend_descriptors,
            texts=self._fix_texts,
        )

    def prepare(self, graph: Graph, services: Services) -> TeamRunPreparation:
        """허용 상호작용(``plan.grants``)·유효 상호작용 설정(기본값 → 공통 → 팀 구성)과 Run 맥락
        (유효 작업 폴더 ``cwd``, ``run_working_directory``).

        결과는 ``mod-runs``의 준비 결과 모양(``grants``·``interaction_settings``·선택
        ``run_context``)을 그대로 만족한다. grant는 위임 방식의 같은 세션 여부(``shares_session``)를
        반영한 세션 단위다."""
        catalog = self._catalog()
        prep = prepare_run(
            graph, catalog.plan(graph), self.workspace, strategies=catalog.strategies
        )
        context: dict[str, Any] = {}
        cwd = self.run_working_directory(graph, services)
        if self._cwd_key and cwd:
            context[self._cwd_key] = cwd
        return TeamRunPreparation(
            grants=prep.grants,
            interaction_settings=prep.interaction_settings,
            flow_settings=prep.flow_settings,
            delegation_settings=prep.delegation_settings,
            run_context=context,
        )

    def run_working_directory(self, graph: Graph, services: Services) -> str | None:
        """Run의 유효 작업 폴더: 팀 구성 수준 설정(공통 → 범위 층(``SCOPE_LAYERS``) → 팀 구성)의
        ``working_directory``, 없으면 노드 서비스 ``WORKING_DIRECTORY``(서버 작업 폴더). 노드마다
        다른 값(에이전트·노드 층)은 노드가 정한다 — 이것은 Run 하나의 기준 값이다."""
        value = team_settings(
            graph, self.workspace, scope_layers=_scope_layers(services)
        ).effective.value.working_directory
        return value or services.get(WORKING_DIRECTORY) or None


def _scope_layers(services: Services) -> Sequence[Layer]:
    found = services.get(SCOPE_LAYERS)
    return tuple(found) if found else ()


class ValidationSummaries:
    """``graphs.validation``: 팀 구성 목록 검증 요약(엔진 + 팀 규칙, 워크스페이스 개정 캐시).

    Args:
        checker: 실행 검증(``runs.starter``).
        lookup: 정의 저장소(개정 지문 재료).
    """

    def __init__(self, checker: RunChecker, lookup: Any) -> None:
        self._checker = checker
        self._lookup = lookup
        self._cache = GraphValidationCache()
        self._generation = 0
        self._lock = threading.Lock()

    def invalidate(self, _item: object = None) -> None:
        """캐시를 버린다(``definitions.saved`` 구독)."""
        with self._lock:
            self._generation += 1
        self._cache.clear()

    def revision(self) -> str:
        fingerprint = workspace_revision(self._lookup)
        if fingerprint is not None:
            return fingerprint
        with self._lock:
            return f"generation:{self._generation}"

    def summaries(self, graph_ids: Sequence[str]) -> dict[str, GraphValidationSummary | None]:
        return self._cache.summaries(self.revision(), list(graph_ids), self.compute)

    def compute(self, graph_id: str) -> GraphValidationSummary | None:
        """그래프 하나의 요약(읽을 수 없거나 계산이 실패하면 None)."""
        try:
            graph = self._checker.load_graph(graph_id)
        except Exception:
            return None
        try:
            return validation_summary(self._checker.check(graph))
        except Exception:
            _log.exception("팀 구성 검증 요약 실패: %s", graph_id)
            return None


__all__ = ["RUN_CONTEXT_CWD", "TeamRules", "TeamRunPreparation", "ValidationSummaries"]
