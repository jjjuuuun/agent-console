"""팀 검증 규칙이 함께 쓰는 문맥: 해석 결과·입력 데이터·유효 설정 캐시·제안 도우미·이슈 모음."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from agent_console_contracts import (
    Agent,
    AgentSettings,
    BackendCapabilities,
    DelegationSettings,
    DelegationStrategyDescriptor,
    EdgeSpec,
    Issue,
    IssueSuggestion,
    WorkspaceSettings,
)
from agent_console_graph import LoopRegion, PortResolver, loop_regions
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType

from ._backends import node_display_name
from ._conventions import TeamConventions
from ._issues import SettingsValidator
from ._nested import TeamLookup
from ._plan import TeamPlan, edge_kinds
from ._preview import session_owner
from ._run import delegation_settings, flow_settings
from ._settings import delegation_max_depth, node_settings
from ._suggest import SuggestionBuilder

__all__ = ["TeamCheckContext"]


class TeamCheckContext:
    """규칙 함수(`(ctx) -> None`)가 읽고 `add`로 이슈를 쌓는 문맥.

    한 번의 `validate_team` 동안만 산다.
    """

    def __init__(
        self,
        plan: TeamPlan,
        *,
        strategies: Mapping[str, DelegationStrategyDescriptor],
        agents: Mapping[str, Agent] | None,
        workspace: WorkspaceSettings | None,
        backends: Mapping[str, BackendCapabilities],
        settings_validators: Mapping[str, SettingsValidator],
        default_backend: str | None,
        resources: ResourceLookup | None,
        resolve_ports: PortResolver | None,
        resource_types: Registry[ResourceType] | None = None,
        teams: TeamLookup | None = None,
    ) -> None:
        self.plan = plan
        self.c: TeamConventions = plan.conventions
        self.strategies = strategies
        self.agents = agents
        self.workspace = workspace
        self.backends = backends
        self.validators = settings_validators
        self.default_backend = default_backend
        self.resources = resources
        self.resource_types = resource_types
        self.teams = teams
        """팀 구성 조회(중첩 팀 규칙). None이면 자식 팀 구성을 읽는 검사를 건너뛴다."""
        self.suggest = SuggestionBuilder(plan, resolve_ports)
        self.max_depth_setting = delegation_max_depth(workspace, plan.graph)
        self.regions: dict[str, LoopRegion] = loop_regions(plan.graph, plan.edge_types)
        """사이클을 닫는 사이클 연결 id → 반복 영역(`ac-graph.loop_regions`)."""
        try:
            self.max_iterations_setting = flow_settings(workspace, plan.graph).max_iterations
        except ValidationError:
            self.max_iterations_setting = None
        try:
            self.max_nesting_setting: int | None = delegation_settings(
                workspace, plan.graph
            ).max_nesting
        except ValidationError:  # 설정이 틀리면 계약 기본값(설정 오류는 설정 검사가 알린다)
            self.max_nesting_setting = DelegationSettings().max_nesting
        self.issues: list[Issue] = []
        self._settings: dict[str, AgentSettings] = {}

    def opening_inbound(self, node_id: str) -> tuple[str, ...]:
        """노드로 들어오는 입구·흐름 엣지 중 반복을 닫는 사이클 연결을 뺀 것.

        사이클 연결은 첫 회차에 지나가지 않으므로(엔진: 처음에 dead) 이것만 들어오는 노드는
        처음 실행될 수 없다.
        """
        return tuple(e for e in self.plan.view.incoming.get(node_id, ()) if e not in self.regions)

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)

    def settings(self, node_id: str) -> AgentSettings:
        """노드의 유효 설정(캐시)."""
        if node_id not in self._settings:
            self._settings[node_id] = node_settings(
                self.plan,
                node_id,
                agents=self.agents,
                workspace=self.workspace,
                strategies=self.strategies,
            ).effective.value
        return self._settings[node_id]

    def backend_of(self, node_id: str) -> str | None:
        return self.settings(node_id).backend or self.default_backend

    def session_owner(self, node_id: str) -> str:
        """노드가 실제로 도는 세션의 노드(`_preview.session_owner`, 방식 `shares_session` 반영)."""
        return session_owner(self.plan, node_id, self.strategies)

    def label(self, node_id: str) -> str:
        """사용자 문구의 노드 이름(`node_display_name`: label → 에이전트 정의 이름 → …)."""
        return node_display_name(self.plan, node_id, self.agents)

    def node_order(self) -> list[str]:
        return list(dict.fromkeys(n.id for n in self.plan.graph.nodes))

    def is_outside(self, node_id: str) -> bool:
        """사용자 쪽 노드: 입구의 출발·답변의 도착이거나, 그 자리에 올 수 있는 역할."""
        if node_id in self.plan.outside:
            return True
        role = self.plan.role_of(node_id)
        if role is None:
            return False
        for desc in self.plan.edge_types:
            connects = desc.connects
            if connects is None:
                continue
            if (desc.scheduling == "entry" and role in connects.source) or (
                desc.scheduling == "exit" and role in connects.target
            ):
                return True
        return False

    def grant_edges(self, node_id: str) -> list[EdgeSpec]:
        return [e for eid in self.plan.grant_edges.get(node_id, ()) if (e := self.plan.edge(eid))]

    def edge_kinds(self, edge_id: str) -> list[str]:
        """엣지가 허용하는 상호작용 종류(`_plan.edge_kinds`, grant 계산과 같은 함수)."""
        desc = self.plan.edge_descriptors.get(edge_id)
        edge = self.plan.edge(edge_id)
        if desc is None or edge is None:
            return []
        return edge_kinds(edge, desc, self.c)

    # ------------------------------------------------------------ 제안
    def entry_suggestion(self, node_id: str, n: int) -> IssueSuggestion | None:
        return self.suggest.connect(
            node_id=node_id,
            node_is_source=False,
            accept=lambda d: d.scheduling == "entry",
            suggestion_id=f"entry:{node_id}:{n}",
            label=f"'{self.label(node_id)}'을(를) 입구로",
        )

    def reply_suggestion(
        self, node_id: str, n: int, port: str | None = None
    ) -> IssueSuggestion | None:
        return self.suggest.connect(
            node_id=node_id,
            node_is_source=True,
            node_port=port,
            accept=lambda d: d.scheduling == "exit",
            suggestion_id=f"reply:{node_id}:{port or ''}:{n}",
            label=(
                f"'{self.label(node_id)}'의 '{port}' 결과를 답변으로"
                if port
                else f"'{self.label(node_id)}'을(를) 답변으로"
            ),
        )
