"""실행 백엔드 해석(순수): 노드마다 유효 백엔드와 실행 전 사전 점검 대상(design §5.2R.5).

해결 순서는 설정 층 그대로다(바꾸지 않는다): 노드 → 에이전트 → 팀 구성 → 공통
(`agent_defaults.backend`, 읽기 호환 `default_backend`) → 인자 `default_backend`(마지막 대체값).
층 병합은 `node_settings`와 같은 함수를 쓴다.

어떤 노드가 백엔드를 쓰는지는 이름이 아니라 디스크립터로 판단한다:

- 실행 가능(`executable`)하고 에이전트 정의에 묶인 노드(`binds.kind == conventions.agent_kind`),
- 또는 노드 타입 디스크립터 `capabilities`에 `conventions.backend_capability`가 있는 노드.

위임받는 노드(엔진이 스케줄하지 않음)는 위임자 세션에서 돌므로(`session_owner`) 사전 점검은 세션
주인 노드만 본다. 백엔드 이름은 이 모듈에 없다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agent_console_contracts import Agent, DelegationStrategyDescriptor, WorkspaceSettings
from agent_console_settings import Layer

from ._plan import TeamPlan
from ._preview import session_owner
from ._settings import node_settings

__all__ = [
    "UnresolvedBackend",
    "backend_nodes",
    "node_display_name",
    "resolve_backends",
    "unresolved_backends",
]


def backend_nodes(plan: TeamPlan) -> list[str]:
    """백엔드를 쓰는 노드 id(그래프 순서, 중복 없음). 판단 기준은 모듈 문서."""
    c = plan.conventions
    out: list[str] = []
    for node in plan.graph.nodes:
        if node.id in out:
            continue
        desc = plan.node_descriptors.get(node.id)
        if desc is None:
            continue
        bound = desc.executable and node.id in plan.agent_refs
        declared = c.backend_capability in desc.capabilities
        if bound or declared:
            out.append(node.id)
    return out


def resolve_backends(
    plan: TeamPlan,
    *,
    agents: Mapping[str, Agent] | None = None,
    workspace: WorkspaceSettings | None = None,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
    default_backend: str | None = None,
    scope_layers: Sequence[Layer] = (),
) -> dict[str, str | None]:
    """백엔드를 쓰는 노드마다 유효 백엔드 id(정해지지 않았으면 None).

    Args:
        plan: `team_plan` 결과.
        agents: 에이전트 정의 id → 정의(에이전트 층). 없는 정의는 에이전트 층이 빈다.
        workspace: 공통 설정(공통 층, `default_backend` 읽기 호환 포함).
        strategies: 위임 방식 디스크립터(`node_settings`와 같은 인자, 값에는 영향 없음).
        default_backend: 모든 층이 비었을 때 쓸 마지막 대체값(예: 서버가 주입한 기본 백엔드).
        scope_layers: 공통 바로 아래에 끼울 층(`node_settings`와 같다, 예: 프로젝트 층).

    Returns:
        `{node_id: backend_id | None}`(`backend_nodes` 순서). 등록 여부는 보지 않는다.
    """
    out: dict[str, str | None] = {}
    for nid in backend_nodes(plan):
        value = node_settings(
            plan,
            nid,
            agents=agents,
            workspace=workspace,
            strategies=strategies,
            scope_layers=scope_layers,
        ).effective.value
        out[nid] = value.backend or default_backend or None
    return out


@dataclass(frozen=True, slots=True)
class UnresolvedBackend:
    """사전 점검에서 백엔드가 비어 있는 노드 하나.

    Attributes:
        node_id: 노드 id(상세에만 쓴다).
        label: 화면 이름(`node_display_name`).
    """

    node_id: str
    label: str


def node_display_name(
    plan: TeamPlan, node_id: str, agents: Mapping[str, Agent] | None = None
) -> str:
    """사용자 문구에 쓸 노드 이름: 노드 `label` → 묶인 에이전트 정의 `name` → `plan.label_of`
    (정의 id → 노드 타입 `title` → 노드 id). 노드 id는 문구가 아니라 `details`에 둔다."""
    node = plan.node(node_id)
    if node is not None and node.label:
        return node.label
    ref = plan.agent_refs.get(node_id)
    agent = (agents or {}).get(ref) if ref is not None else None
    if agent is not None and agent.name:
        return agent.name
    return plan.label_of(node_id)


def unresolved_backends(
    plan: TeamPlan,
    resolved: Mapping[str, str | None],
    *,
    agents: Mapping[str, Agent] | None = None,
) -> list[UnresolvedBackend]:
    """실행 전에 막아야 할 노드: 백엔드를 실제로 여는 세션 주인 노드 중 백엔드가 빈 것.

    위임받는 노드는 위임자(세션 주인)의 백엔드로 돌므로 자기 값이 비어도 막지 않는다.

    Args:
        plan: `team_plan` 결과.
        resolved: `resolve_backends` 결과.
        agents: 이름 표시용 에이전트 정의.

    Returns:
        그래프 순서의 목록(없으면 빈 목록 = 실행해도 된다).
    """
    out: list[UnresolvedBackend] = []
    seen: set[str] = set()
    for nid in resolved:
        owner = session_owner(plan, nid)
        if owner in seen or owner not in resolved:
            continue
        seen.add(owner)
        if resolved[owner] is None:
            out.append(UnresolvedBackend(owner, node_display_name(plan, owner, agents)))
    return out
