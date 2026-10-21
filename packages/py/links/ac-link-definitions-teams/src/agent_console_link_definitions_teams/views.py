"""팀 구성 화면용 계산(design §2R.6): 사용처·입구 이름·실행 계획·유효 설정·묶음 미리보기.

계산은 ``ac-teams``에 있다. 여기서는 정의 읽기·공통 설정·리소스·디스크립터(플러그인 레지스트리)를
모아 넘기고, 응답에서 비밀을 가린다(``x-secret`` 평문은 ``mask_effective_secrets``, 해석한 값·의심
값은 가림 함수). FastAPI를 모른다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from agent_console_contracts import (
    Agent,
    BundlePreview,
    DefinitionReference,
    EffectiveSettings,
    Graph,
    Issue,
    TeamPlanSummary,
    WorkspaceSettings,
)
from agent_console_registry import Registry
from agent_console_resources import (
    InMemoryResources,
    ResourceLookup,
    ResourceType,
    new_resource_types,
)
from agent_console_store import AGENT_KIND, GRAPH_KIND, RESOURCE_KIND, StoreError
from agent_console_teams import (
    Layer,
    NodeSettings,
    TeamCatalog,
    TeamPlan,
    agent_layers,
    bundle_preview,
    definition_references,
    mask_effective_secrets,
    merge_rules,
    node_settings,
    plan_summary,
    resolve_settings,
)

from .ports import DefinitionLookup, Redactor, ScopeLayersSource


class NodeNotFoundError(LookupError):
    """팀 구성에 그 노드가 없다(404)."""

    def __init__(self, node_id: str) -> None:
        super().__init__(f"노드 {node_id}이(가) 없습니다")
        self.node_id = node_id


def redact_values(value: Any, redact: Redactor) -> Any:
    """JSON 값의 문자열(키 포함)마다 비밀을 가린다(직렬화 전체를 가리면 JSON이 깨질 수 있다)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {redact(str(k)): redact_values(v, redact) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_values(v, redact) for v in value]
    return value


class TeamViews:
    """팀 구성 화면 계산 묶음.

    Args:
        lookup: 정의 읽기.
        catalog: 지금 디스크립터 묶음(``catalog_from_registries``).
        workspace: 지금 공통 설정(없으면 기본값).
        resources: 리소스 조회(없으면 빈 조회).
        types: 리소스 종류(없으면 빈 레지스트리).
        redact: 응답 문자열 가림 함수.
        scopes: 지금 범위 층 공급자 목록(``settings.scope_layers``). 유효 설정의 ``scope``
            인자(예: 프로젝트 id)를 층으로 바꾼다. 없으면 범위를 무시한다.
    """

    def __init__(
        self,
        lookup: DefinitionLookup,
        *,
        catalog: Callable[[], TeamCatalog] = TeamCatalog,
        workspace: Callable[[], WorkspaceSettings | None] = lambda: None,
        resources: Callable[[], ResourceLookup | None] = lambda: None,
        types: Callable[[], Registry[ResourceType] | None] = lambda: None,
        redact: Callable[[], Redactor] = lambda: lambda text: text,
        scopes: Callable[[], Sequence[ScopeLayersSource]] = list,
    ) -> None:
        self.lookup = lookup
        self._catalog = catalog
        self._workspace = workspace
        self._resources = resources
        self._types = types
        self._redact = redact
        self._scopes = scopes
        self._empty_types: Registry[ResourceType] = new_resource_types()
        self._empty_resources = InMemoryResources()

    # ------------------------------------------------------------ 재료

    @property
    def catalog(self) -> TeamCatalog:
        return self._catalog()

    @property
    def workspace(self) -> WorkspaceSettings:
        return self._workspace() or WorkspaceSettings()

    @property
    def resources(self) -> ResourceLookup:
        return self._resources() or self._empty_resources

    @property
    def types(self) -> Registry[ResourceType]:
        found = self._types()
        return found if found is not None else self._empty_types

    def scope_layers(self, scope: str | None) -> tuple[list[Layer], list[Issue]]:
        """범위 id → 공통 바로 아래에 끼울 층과 경고(공급자 순서대로, 없거나 None이면 빈 것)."""
        layers: list[Layer] = []
        warnings: list[Issue] = []
        if not scope:
            return layers, warnings
        for source in self._scopes():
            found = source.scope_layers(scope)
            layers.extend(found.layers)
            warnings.extend(found.warnings)
        return layers, warnings

    def model[M: BaseModel](self, kind: str, item_id: str, model: type[M]) -> M:
        """정의 하나(없으면 저장소 ``NotFound``, 계약에 맞지 않으면 ``ValidationError``)."""
        return model.model_validate(self.lookup.get(kind, item_id).document)

    def find[M: BaseModel](self, kind: str, item_id: str, model: type[M]) -> M | None:
        """읽을 수 없으면 None."""
        try:
            return self.model(kind, item_id, model)
        except (StoreError, ValidationError):
            return None

    def all[M: BaseModel](self, kind: str, model: type[M]) -> list[M]:
        """한 종류의 읽을 수 있는 정의 전부(id 순)."""
        out: list[M] = []
        for item_id in self.lookup.list_ids(kind):
            found = self.find(kind, item_id, model)
            if found is not None:
                out.append(found)
        return out

    def agents_for(self, plan: TeamPlan) -> dict[str, Agent]:
        """팀 구성이 쓰는 에이전트 정의(id → 정의, 없는 것은 빠짐)."""
        found: dict[str, Agent] = {}
        for agent_id in set(plan.agent_refs.values()):
            agent = self.find(AGENT_KIND.name, agent_id, Agent)
            if agent is not None:
                found[agent_id] = agent
        return found

    # ------------------------------------------------------------ 포트 구현

    def references(self, kind: str, item_id: str) -> list[DefinitionReference]:
        """``definitions.usages``: 정의 ``kind/id``가 붙은 곳(노드·층 첨부·에이전트·공통)."""
        is_resource = kind == RESOURCE_KIND.name
        return definition_references(
            kind,
            item_id,
            graphs=self.all(GRAPH_KIND.name, Graph),
            agents=self.all(AGENT_KIND.name, Agent) if is_resource else (),
            workspace=self.workspace if is_resource else None,
            node_types=self.catalog.node_types,
        )

    def entry_labels(self, graph: Graph) -> list[str] | None:
        """``graphs.entry_labels``: 입구 노드 표시 이름(해석할 수 없으면 None)."""
        plan = self.catalog.try_plan(graph)
        if plan is None:
            return None
        try:
            return [plan.label_of(n) for n in plan.entry_nodes]
        except Exception:
            return None

    # ------------------------------------------------------------ 화면 계산

    def plan_summary(self, graph: Graph) -> TeamPlanSummary:
        return plan_summary(self.catalog.plan(graph))

    def _node_settings(
        self, graph: Graph, node_id: str, scope_layers: Sequence[Layer] = ()
    ) -> NodeSettings:
        if all(n.id != node_id for n in graph.nodes):
            raise NodeNotFoundError(node_id)
        catalog = self.catalog
        plan = catalog.plan(graph)
        return node_settings(
            plan,
            node_id,
            agents=self.agents_for(plan),
            workspace=self.workspace,
            strategies=catalog.strategies,
            resource_types=self.types,
            resources=self.resources,
            backends=catalog.backends,
            scope_layers=scope_layers,
        )

    def node_effective(
        self, graph: Graph, node_id: str, *, scope: str | None = None
    ) -> EffectiveSettings:
        """노드 유효 설정(4층 + 리소스 연결)·출처·경고, ``x-secret`` 가림.

        Args:
            scope: 범위 id(예: 프로젝트 id). 주면 범위 층을 공통 바로 아래에 끼우고 공급자 경고를
                ``warnings``에 더한다.
        """
        layers, notes = self.scope_layers(scope)
        effective = self._node_settings(graph, node_id, layers).effective
        if notes:
            effective = effective.model_copy(update={"warnings": [*effective.warnings, *notes]})
        return mask_effective_secrets(effective, types=self.types, resources=self.resources)

    def node_bundle(self, graph: Graph, node_id: str) -> BundlePreview:
        """노드 실행 묶음 미리보기 + 경고. 비밀 참조는 그대로, 평문·해석 값은 가린다."""
        if all(n.id != node_id for n in graph.nodes):
            raise NodeNotFoundError(node_id)
        catalog = self.catalog
        plan = catalog.plan(graph)
        preview = bundle_preview(
            plan,
            node_id,
            resource_types=self.types,
            resources=self.resources,
            backends=catalog.backends,
            agents=self.agents_for(plan),
            workspace=self.workspace,
            strategies=catalog.strategies,
            notes=catalog.preview_notes,
        )
        return BundlePreview.model_validate(
            redact_values(preview.model_dump(mode="json"), self._redact())
        )

    def agent_effective(self, agent_id: str, *, scope: str | None = None) -> EffectiveSettings:
        """팀 구성 밖 유효 설정(공통 → [범위 층] → 에이전트)과 출처, ``x-secret`` 가림."""
        agent = self.model(AGENT_KIND.name, agent_id, Agent)
        workspace = self.workspace
        layers, notes = self.scope_layers(scope)
        effective = resolve_settings(
            agent_layers(agent, workspace, scope_layers=layers),
            rules=merge_rules(workspace, None),
            resource_types=self.types,
            resources=self.resources,
            backends=self.catalog.backends,
        ).effective
        if notes:
            effective = effective.model_copy(update={"warnings": [*effective.warnings, *notes]})
        return mask_effective_secrets(effective, types=self.types, resources=self.resources)


__all__ = ["NodeNotFoundError", "TeamViews", "redact_values"]
