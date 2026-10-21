"""`team_plan`: 팀 구성 그래프를 디스크립터 속성만으로 해석한다.

설계: design §R1.2a, §R3.1, §R3.2, §R14.2.

- 입구·답변 = `scheduling` `entry`·`exit` 엣지(명시된 연결뿐, 모양으로 추론하지 않음).
- 위임 = 디스크립터 `invocation`이 있는 엣지(위임 방식 id는 엣지 config로 덮어쓸 수 있음).
- 리소스 첨부 = 리소스 정의에 묶인 노드(`binds.kind`)에서 나가는 `scheduling=none` 엣지
  (`invocation`·`interaction` 없음). 도착 노드의 노드 층 첨부가 된다.
- 허용 상호작용(grant) = 노드에서 나가는, 디스크립터 `interaction`이 있는 엣지들의 `kinds` 합
  (엣지 config `kinds`로 좁힘) + 대기 한도.

연결 종류·노드 타입 이름은 이 모듈에 없다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import (
    Agent,
    DelegationStrategyDescriptor,
    EdgeSpec,
    EdgeTypeDescriptor,
    Graph,
    InteractionGrant,
    NodeSpec,
    NodeTypeDescriptor,
    ResourceAttachment,
)
from agent_console_graph import ScheduleView, schedule_view

from ._conventions import DEFAULT_CONVENTIONS, TeamConventions

__all__ = [
    "Attachment",
    "DelegationLink",
    "MemberProfile",
    "TeamPlan",
    "describe_member",
    "runs_in_own_session",
    "session_grant",
    "shares_session",
    "team_plan",
]


@dataclass(frozen=True, slots=True)
class DelegationLink:
    """위임 연결 하나(디스크립터 `invocation`이 있는 엣지).

    Attributes:
        edge_id: 엣지 id.
        delegator / member: 위임자 노드 id / 위임받는 노드 id.
        strategy: 위임 방식 id(엣지 config 덮어쓰기 > 디스크립터 `invocation.strategy`).
        role / delegate_when: 위임받는 노드 config의 역할·언제 맡길지(없으면 None —
            `describe_member`가 에이전트 정의 값으로 채운다).
    """

    edge_id: str
    delegator: str
    member: str
    strategy: str
    role: str | None = None
    delegate_when: str | None = None


@dataclass(frozen=True, slots=True)
class Attachment:
    """리소스 노드 → 노드 연결로 생긴 첨부(도착 노드의 노드 층)."""

    edge_id: str
    resource_node: str
    target_node: str
    attachment: ResourceAttachment


@dataclass(frozen=True, slots=True)
class MemberProfile:
    """위임받는 노드를 위임자에게 소개하는 값(역할 이름·언제 맡길지)."""

    role: str
    delegate_when: str


@dataclass(frozen=True)
class TeamPlan:
    """팀 구성 그래프의 실행 의미 요약. 모든 순서는 결정적이다(노드·엣지는 그래프 순서).

    Attributes:
        graph: 대상 그래프.
        view: `ac-graph.schedule_view` 결과(스케줄 대상·위상).
        conventions: 해석에 쓴 약속.
        node_descriptors / edge_descriptors: 노드 id / 엣지 id → 디스크립터(모르는 타입은 빠짐).
        node_types / edge_types: 받은 디스크립터 목록(제안 데이터 계산용).
        entries / entry_nodes: `entry` 엣지 id / 입구 노드 id(실행 가능 노드만).
        answers / answer_nodes: `exit` 엣지 id / 답변을 내는 노드 id.
        delegations: 위임 연결 전부. `delegates_of[위임자]`, `callers_of[대상]`로도 찾는다.
        callees: 위임받는 노드 id(호출 대상 — 엔진이 스케줄하지 않는다).
        attachments_of: 노드 id → 리소스 연결 첨부(노드 층에 들어감).
        grants: 노드 id → 허용 상호작용. 상호작용 연결이 없는 노드는 없다.
        grant_edges: 노드 id → grant를 만든 엣지 id.
        agent_refs / resource_refs: 노드 id → 묶인 에이전트·리소스 정의 id.
        team_refs: 노드 id → 중첩 팀 노드가 묶은 자식 팀 구성 id(`binds.kind ==
            conventions.team_kind`, design §5R.7).
        team_versions: 노드 id → 고정한 자식 팀 구성 버전(config `conventions.node_version_key`,
            없으면 빠짐 = 실행 시점 최신).
        outside: 입구 엣지의 출발 노드와 답변 엣지의 도착 노드(사용자 쪽 노드).
    """

    graph: Graph
    view: ScheduleView
    conventions: TeamConventions
    node_descriptors: Mapping[str, NodeTypeDescriptor]
    edge_descriptors: Mapping[str, EdgeTypeDescriptor]
    node_types: tuple[NodeTypeDescriptor, ...]
    edge_types: tuple[EdgeTypeDescriptor, ...]
    entries: tuple[str, ...]
    entry_nodes: tuple[str, ...]
    answers: tuple[str, ...]
    answer_nodes: tuple[str, ...]
    delegations: tuple[DelegationLink, ...]
    delegates_of: Mapping[str, tuple[DelegationLink, ...]]
    callers_of: Mapping[str, tuple[DelegationLink, ...]]
    callees: frozenset[str]
    attachments_of: Mapping[str, tuple[Attachment, ...]]
    grants: Mapping[str, InteractionGrant]
    grant_edges: Mapping[str, tuple[str, ...]]
    agent_refs: Mapping[str, str]
    resource_refs: Mapping[str, str]
    outside: frozenset[str]
    team_refs: Mapping[str, str] = field(default_factory=dict)
    team_versions: Mapping[str, str] = field(default_factory=dict)
    _nodes: Mapping[str, NodeSpec] = field(default_factory=dict, repr=False)
    _edges: Mapping[str, EdgeSpec] = field(default_factory=dict, repr=False)

    def node(self, node_id: str) -> NodeSpec | None:
        """노드 id → 노드(중복 id는 첫 번째)."""
        return self._nodes.get(node_id)

    def edge(self, edge_id: str) -> EdgeSpec | None:
        """엣지 id → 엣지(중복 id는 첫 번째)."""
        return self._edges.get(edge_id)

    def role_of(self, node_id: str) -> str | None:
        """노드 타입 디스크립터의 `role`(연결 규칙 근거). 모르는 타입이면 None."""
        desc = self.node_descriptors.get(node_id)
        return desc.role if desc is not None else None

    def label_of(self, node_id: str) -> str:
        """화면용 노드 이름: `label` → 묶인 정의 id(에이전트·리소스·팀 구성) → 노드 타입 `title`
        → 노드 id(마지막 대체값). 정의 이름까지 보려면 `node_display_name`을 쓴다."""
        node = self._nodes.get(node_id)
        if node is not None and node.label:
            return node.label
        ref = (
            self.agent_refs.get(node_id)
            or self.resource_refs.get(node_id)
            or self.team_refs.get(node_id)
        )
        if ref:
            return ref
        desc = self.node_descriptors.get(node_id)
        return desc.title if desc is not None else node_id

    def edges_from(self, node_id: str) -> list[EdgeSpec]:
        """`node_id`에서 나가는 엣지(그래프 순서)."""
        return [e for e in self._edges.values() if e.source.node == node_id]

    def edges_to(self, node_id: str) -> list[EdgeSpec]:
        """`node_id`로 들어오는 엣지(그래프 순서)."""
        return [e for e in self._edges.values() if e.target.node == node_id]


def _index[D: (NodeTypeDescriptor, EdgeTypeDescriptor)](
    descriptors: Iterable[D],
) -> dict[tuple[str, int | None], D]:
    """(id, version) 및 (id, None)=최신 버전 → 디스크립터."""
    index: dict[tuple[str, int | None], D] = {}
    for desc in descriptors:
        index.setdefault((desc.id, desc.version), desc)
        latest = index.get((desc.id, None))
        if latest is None or desc.version > latest.version:
            index[(desc.id, None)] = desc
    return index


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def edge_kinds(edge: EdgeSpec, desc: EdgeTypeDescriptor, conventions: TeamConventions) -> list[str]:
    """엣지 하나가 허용하는 상호작용 종류 = 디스크립터 `interaction.kinds` ∩ 엣지 config 좁힘.

    디스크립터 순서를 따른다. 디스크립터에 `interaction`이 없으면 빈 목록. config 값이 목록이
    아니면 좁히지 않는다(문자열이 아닌 항목은 무시). grant 계산과 검증 규칙이 같이 쓴다.
    """
    if desc.interaction is None:
        return []
    allowed = list(desc.interaction.kinds)
    narrowed = edge.config.get(conventions.edge_kinds_key)
    if isinstance(narrowed, list):
        wanted = {k for k in narrowed if isinstance(k, str)}
        allowed = [k for k in allowed if k in wanted]
    return allowed


def _grant(
    edges: list[tuple[EdgeSpec, EdgeTypeDescriptor]], conventions: TeamConventions
) -> InteractionGrant:
    kinds: list[str] = []
    timeout: float | None = None
    timeout_action: Any = None
    first_action: Any = None
    for edge, desc in edges:
        for kind in edge_kinds(edge, desc, conventions):
            if kind not in kinds:
                kinds.append(kind)
        action = edge.config.get(conventions.edge_on_timeout_key)
        action = action if isinstance(action, str) and action else None
        if first_action is None:
            first_action = action
        raw = edge.config.get(conventions.edge_timeout_key)
        seconds = float(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else None
        if seconds is not None and seconds > 0 and (timeout is None or seconds < timeout):
            timeout, timeout_action = seconds, action
    on_timeout = timeout_action if timeout_action is not None else first_action
    return InteractionGrant.model_validate(
        {"kinds": kinds, "timeout_seconds": timeout, "on_timeout": on_timeout}
    )


def team_plan(
    graph: Graph,
    *,
    node_types: Iterable[NodeTypeDescriptor],
    edge_types: Iterable[EdgeTypeDescriptor],
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
) -> TeamPlan:
    """팀 구성 그래프를 해석한다. 예외를 던지지 않는다(문제는 `validate_team`이 이슈로 알린다).

    Args:
        graph: 팀 구성 그래프.
        node_types: 노드 타입 디스크립터(여러 버전 가능, `type_version`이 없으면 최신).
        edge_types: 엣지 타입 디스크립터(같은 id 중 최신 버전).
        conventions: config 키 약속(기본 = 기본 플러그인).

    Returns:
        `TeamPlan`. 타입을 모르는 노드·엣지, 없는 노드를 가리키는 엣지는 어느 묶음에도 들지 않는다.

    grant 규칙: 종류는 엣지별 허용 종류(디스크립터 `interaction.kinds` ∩ 엣지 config `kinds`)의
    합(처음 나온 순서). 대기 한도는 엣지 config 값 중 가장 짧은 것, 초과 시 동작은 그 엣지 값
    (없으면 처음 지정된 값). 둘 다 없으면 null(= 설정 `interaction.*`을 따른다).
    """
    node_list = tuple(node_types)
    edge_list = tuple(edge_types)
    view = schedule_view(graph, node_list, edge_list)
    nindex = _index(node_list)
    eindex = _index(edge_list)

    nodes: dict[str, NodeSpec] = {}
    for node in graph.nodes:
        nodes.setdefault(node.id, node)
    edges: dict[str, EdgeSpec] = {}
    for edge in graph.edges:
        edges.setdefault(edge.id, edge)

    node_desc: dict[str, NodeTypeDescriptor] = {}
    agent_refs: dict[str, str] = {}
    resource_refs: dict[str, str] = {}
    team_refs: dict[str, str] = {}
    team_versions: dict[str, str] = {}
    for nid, node in nodes.items():
        ndesc = nindex.get((node.type, node.type_version))
        if ndesc is None:
            continue
        node_desc[nid] = ndesc
        if ndesc.binds is None:
            continue
        ref = _text(node.config.get(ndesc.binds.field))
        if ref is None:
            continue
        if ndesc.binds.kind == conventions.agent_kind:
            agent_refs[nid] = ref
        elif ndesc.binds.kind == conventions.resource_kind:
            resource_refs[nid] = ref
        elif ndesc.binds.kind == conventions.team_kind:
            team_refs[nid] = ref
            version = _text(node.config.get(conventions.node_version_key))
            if version is not None:
                team_versions[nid] = version

    edge_desc: dict[str, EdgeTypeDescriptor] = {}
    delegations: list[DelegationLink] = []
    attachments: dict[str, list[Attachment]] = {}
    interaction_edges: dict[str, list[tuple[EdgeSpec, EdgeTypeDescriptor]]] = {}
    outside: set[str] = set()
    for eid, edge in edges.items():
        edesc = eindex.get((edge.kind, None))
        src, dst = edge.source.node, edge.target.node
        if edesc is None or src not in nodes or dst not in nodes:
            continue
        edge_desc[eid] = edesc
        if edesc.scheduling == "entry":
            outside.add(src)
        elif edesc.scheduling == "exit":
            outside.add(dst)
        if edesc.invocation is not None:
            member = nodes[dst]
            delegations.append(
                DelegationLink(
                    edge_id=eid,
                    delegator=src,
                    member=dst,
                    strategy=_text(edge.config.get(conventions.edge_strategy_key))
                    or edesc.invocation.strategy,
                    role=_text(member.config.get(conventions.node_role_key)),
                    delegate_when=_text(member.config.get(conventions.node_delegate_when_key)),
                )
            )
        if edesc.interaction is not None:
            interaction_edges.setdefault(src, []).append((edge, edesc))
        if (
            edesc.scheduling == "none"
            and edesc.invocation is None
            and edesc.interaction is None
            and src in resource_refs
        ):
            data: dict[str, Any] = {"ref": resource_refs[src]}
            mode = edge.config.get(conventions.edge_mode_key)
            if isinstance(mode, str) and mode:
                data["mode"] = mode
            override = edge.config.get(conventions.edge_override_key)
            if isinstance(override, Mapping):
                data["config_override"] = dict(override)
            try:
                att = ResourceAttachment.model_validate(data)
            except ValueError:
                continue
            attachments.setdefault(dst, []).append(Attachment(eid, src, dst, att))

    delegates_of: dict[str, list[DelegationLink]] = {}
    callers_of: dict[str, list[DelegationLink]] = {}
    for link in delegations:
        delegates_of.setdefault(link.delegator, []).append(link)
        callers_of.setdefault(link.member, []).append(link)

    return TeamPlan(
        graph=graph,
        view=view,
        conventions=conventions,
        node_descriptors=node_desc,
        edge_descriptors=edge_desc,
        node_types=node_list,
        edge_types=edge_list,
        entries=view.entry_edges,
        entry_nodes=view.entry_nodes,
        answers=view.exit_edges,
        answer_nodes=view.exit_nodes,
        delegations=tuple(delegations),
        delegates_of={k: tuple(v) for k, v in delegates_of.items()},
        callers_of={k: tuple(v) for k, v in callers_of.items()},
        callees=frozenset(callers_of),
        attachments_of={k: tuple(v) for k, v in attachments.items()},
        grants={k: _grant(v, conventions) for k, v in interaction_edges.items()},
        grant_edges={k: tuple(e.id for e, _ in v) for k, v in interaction_edges.items()},
        agent_refs=agent_refs,
        resource_refs=resource_refs,
        outside=frozenset(outside),
        team_refs=team_refs,
        team_versions=team_versions,
        _nodes=nodes,
        _edges=edges,
    )


def session_grant(
    plan: TeamPlan,
    node_id: str,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
) -> InteractionGrant | None:
    """위임자 세션 하나가 열 수 있는 상호작용(design §R3.2-6, §R14.8, §5.2R.7).

    노드 자신의 grant에 위임받는 노드들의 grant를 위임 방식 `member_interaction_kinds`로 걸러
    더한다(SDK 세션 하나에 콜백 하나). 위임 방식 디스크립터를 모르면 거르지 않는다.
    대기 한도는 자신의 값, 없으면 대상들 중 가장 짧은 값.

    디스크립터 `shares_session`이 false인 방식(대상이 자기 세션에서 도는 방식)의 대상은 더하지
    않는다 — 상호작용 종류도 대기 한도도 위임자 세션에 들어오지 않는다(`shares_session` 참조).

    Returns:
        허용이 하나도 없으면 None.
    """
    own = plan.grants.get(node_id)
    kinds = list(own.kinds) if own is not None else []
    timeout = own.timeout_seconds if own is not None else None
    on_timeout = own.on_timeout if own is not None else None
    found = own is not None
    for link in plan.delegates_of.get(node_id, ()):
        member = plan.grants.get(link.member)
        if member is None or not shares_session(link, strategies):
            continue
        found = True
        desc = (strategies or {}).get(link.strategy)
        allowed = desc.member_interaction_kinds if desc is not None else None
        for kind in member.kinds:
            if (allowed is None or kind in allowed) and kind not in kinds:
                kinds.append(kind)
        if own is None or own.timeout_seconds is None:
            mt = member.timeout_seconds
            if mt is not None and (timeout is None or mt < timeout):
                timeout, on_timeout = mt, member.on_timeout or on_timeout
    if not found:
        return None
    return InteractionGrant(kinds=kinds, timeout_seconds=timeout, on_timeout=on_timeout)


def shares_session(
    link: DelegationLink, strategies: Mapping[str, DelegationStrategyDescriptor] | None = None
) -> bool:
    """위임 연결의 대상이 위임자 세션 안에서 도는지(디스크립터 `shares_session`).

    방식 디스크립터를 모르면 true(계약 기본값과 같다 — 기존 외부 방식 동작 유지).
    """
    desc = (strategies or {}).get(link.strategy)
    return desc.shares_session if desc is not None else True


def runs_in_own_session(
    plan: TeamPlan,
    node_id: str,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
) -> bool:
    """노드가 자기 세션을 여는지: 위임받지 않거나, 같은 세션이 아닌 방식으로 불리는 연결이 있다.

    같은 세션 방식으로만 불리는 위임 대상은 위임자 세션의 일부라 false다.
    """
    links = plan.callers_of.get(node_id, ())
    return not links or any(not shares_session(link, strategies) for link in links)


def describe_member(link: DelegationLink, agent: Agent | None = None) -> MemberProfile:
    """위임받는 노드의 역할 이름·언제 맡길지.

    노드 config 값이 에이전트 정의(`role`·`description`)보다 우선한다.
    """
    return MemberProfile(
        role=link.role or (agent.role if agent is not None else ""),
        delegate_when=link.delegate_when or (agent.description if agent is not None else ""),
    )
