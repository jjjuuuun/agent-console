"""`validate_team`: 팀 구성 의미 검증(design §R3.1b, §R1.2a, §R14.2, §R14.6).

판단 근거는 디스크립터와 설정 데이터뿐이다.
- 연결: `scheduling`·`invocation`·`interaction`·`connects`.
- 위임 방식: `max_depth`·`allows_outgoing_flow`·`member_fields`·`member_interaction_kinds`·
  `requires_backend_capability`·`composable`, 설정 `delegation.max_depth`.
- 반복: 연결 디스크립터 `cycle`, 설정 `flow.max_iterations`(`_rules_loops`).
- 중첩 팀: 노드 디스크립터 `binds.kind == TeamConventions.team_kind`, 설정
  `delegation.max_nesting`, 주입한 팀 구성 조회(`_rules_teams`).
- 백엔드: `BackendCapabilities.interactions`, 선택 훅 `validate_settings`.
연결 종류·노드 타입·위임 방식·상호작용 종류 이름은 이 패키지에 없다.

규칙은 모듈별로 나뉜다(`_rules_structure`·`_rules_entry`·`_rules_delegation`·`_rules_loops`·
`_rules_interactions`·`_rules_resources`). 여기서는 순서대로 돌리기만 한다(이슈 순서가 결정적이다).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from agent_console_contracts import (
    Agent,
    BackendCapabilities,
    DelegationStrategyDescriptor,
    EdgeTypeDescriptor,
    Graph,
    Issue,
    NodeTypeDescriptor,
    WorkspaceSettings,
)
from agent_console_graph import PortResolver, descriptor_cycle_edge, validate_graph
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType

from ._check_context import TeamCheckContext
from ._conventions import DEFAULT_CONVENTIONS, TeamConventions
from ._issues import SettingsValidator, TeamIssueCodes
from ._nested import TeamLookup
from ._plan import TeamPlan, team_plan
from ._rules_delegation import check_delegation
from ._rules_delegation_static import check_delegation_config, delegation_static_issues
from ._rules_entry import check_entry_reply
from ._rules_interactions import check_interactions
from ._rules_loops import check_loops
from ._rules_resources import check_resource_slots
from ._rules_structure import check_connects, check_refs
from ._rules_teams import check_nested_teams

__all__ = ["TEAM_RULES", "SettingsValidator", "TeamIssueCodes", "validate_team"]

TEAM_RULES: tuple[Callable[[TeamCheckContext], None], ...] = (
    check_connects,
    check_refs,
    check_entry_reply,
    check_delegation,
    check_delegation_config,
    check_loops,
    check_nested_teams,
    check_interactions,
    check_resource_slots,
)
"""`validate_team`이 이 순서로 돌리는 규칙."""


def validate_team(
    graph: Graph,
    *,
    node_types: Iterable[NodeTypeDescriptor],
    edge_types: Iterable[EdgeTypeDescriptor],
    strategies: Iterable[DelegationStrategyDescriptor] = (),
    agents: Mapping[str, Agent] | None = None,
    workspace: WorkspaceSettings | None = None,
    backends: Mapping[str, BackendCapabilities] | None = None,
    settings_validators: Mapping[str, SettingsValidator] | None = None,
    default_backend: str | None = None,
    resources: ResourceLookup | None = None,
    resolve_ports: PortResolver | None = None,
    resource_types: Registry[ResourceType] | None = None,
    graph_checks: bool = True,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
    plan: TeamPlan | None = None,
    edge_checks: Callable[[Graph], Iterable[Issue]] | None = None,
    teams: TeamLookup | None = None,
    delegation_checks: Mapping[str, object] | None = None,
) -> list[Issue]:
    """팀 구성 그래프를 검증해 이슈 목록을 돌려준다. 그래프 문제로는 예외를 던지지 않는다.

    Args:
        graph: 팀 구성 그래프.
        node_types, edge_types: 디스크립터(레지스트리 내용).
        strategies: 위임 방식 디스크립터(X12). 모르는 방식의 연결은 `team.unknown_strategy` 경고만
            내고 그 방식에 기댄 규칙은 건너뛴다.
        agents: 에이전트 정의 id → 정의. None이면 정의 존재 검사를 건너뛴다(설정 층은 비어 있음).
        workspace: 공통 설정(설정 층·`delegation.max_depth`·병합 규칙).
        backends: 백엔드 id → 능력(`requires_backend_capability`·`interactions` 검사). 없으면 생략.
        settings_validators: 백엔드 id → `validate_settings` 훅. 훅이 없는 백엔드는 생략.
        default_backend: 유효 설정에 backend가 없을 때 쓸 백엔드 id(서버 설정).
        resources: 리소스 조회(리소스 노드 참조 검사). None이면 생략.
        resolve_ports: 동적 포트 해석기(구조 검사·제안 포트 계산).
        resource_types: 리소스 종류(선택). `resources`와 함께 주면 노드마다 묶음을 조립해 실행
            백엔드가 받지 않는 칸을 경고한다(`resource.slot_unsupported`, 백엔드 `slot_notes` 이유).
        graph_checks: 참이면 `ac-graph.validate_graph(cycle_edge=descriptor_cycle_edge)`(타입·
            config·포트·흐름 순환)를 먼저 돌려 함께 돌려준다. 흐름 사이클은 사이클마다 사이클 연결
            (디스크립터 `cycle`)이 있으면 허용되고(검토 반려를 앞 노드로 되돌리기 포함), 없으면
            그쪽 `cycle` 이슈(되돌아가는 연결을 사이클 연결 종류로 바꾸는 제안 포함)다.
        conventions: config 키 약속.
        plan: 이미 계산한 `team_plan` 결과(없으면 계산).
        edge_checks: 연결 의미 검사(선택, 예: 조건 연결의 조건 검사). 그래프를 받아 이슈를 돌려준다.
            엔진 쪽 검사를 이 패키지가 import하지 않도록 주입받는다(예: `ac-runtime`
            `validate_edges(graph, registries, services)`를 감싼 함수). 엔진 검증을 따로 돌려
            합치는 호출자(`graph_checks=False`)는 넘기지 않는다(같은 이슈가 두 번 나온다).
        teams: 팀 구성 조회 `(id, 고정 버전 | None) -> Graph | None`(중첩 팀 규칙, design §5R.7).
            None이면 자기 참조(`team.recursive`)만 보고 자식을 읽는 검사(`team.team_not_found`·
            `team.child_no_entry`·순환·`team.nesting_exceeded`)는 건너뛴다.
        delegation_checks: 위임 방식 id → 방식 객체(선택, design §5.2R.7). 객체의 선택 메서드
            `static_issues`·`declared_names`(ac-runtime `StaticDelegationChecks`·
            `DelegationNameDeclarer`)로 방식 고유 정적 검사와 합침 이름 충돌을 더한다
            (`delegation_static_issues`). 엔진 검증(`validate_graph_with` — 노드 타입 검사가 등록된
            위임 방식을 부른다)을 따로 돌려 합치는 호출자는 넘기지 않는다(같은 이슈가 두 번 나온다).
            방식 config 스키마 검사·같은 대상 중복은 이 값과 무관하게 늘 돈다.

    위임 깊이 한도 = 위임 방식 디스크립터 `max_depth`와 설정 `delegation.max_depth` 중 작은 값
    (한쪽만 있으면 그 값, 둘 다 없으면 제한 없음).
    """
    node_list = tuple(node_types)
    edge_list = tuple(edge_types)
    if plan is None:
        plan = team_plan(graph, node_types=node_list, edge_types=edge_list, conventions=conventions)
    issues: list[Issue] = []
    if graph_checks:
        issues.extend(
            validate_graph(
                graph,
                node_list,
                edge_list,
                resolve_ports=resolve_ports,
                cycle_edge=descriptor_cycle_edge,
            )
        )
    if edge_checks is not None:
        issues.extend(edge_checks(graph))
    ctx = TeamCheckContext(
        plan,
        strategies={s.id: s for s in strategies},
        agents=agents,
        workspace=workspace,
        backends=backends or {},
        settings_validators=settings_validators or {},
        default_backend=default_backend,
        resources=resources,
        resolve_ports=resolve_ports,
        resource_types=resource_types,
        teams=teams,
    )
    for rule in TEAM_RULES:
        rule(ctx)
    issues.extend(ctx.issues)
    if delegation_checks:
        issues.extend(delegation_static_issues(plan, delegation_checks, agents=agents))
    return issues
