"""스케줄 관점 요약: 엣지 디스크립터 `scheduling`과 노드 `executable`만으로 계산한다(design §R3.1).

연결 종류·노드 타입 이름은 모른다. 입구는 `scheduling = entry` 엣지로 명시된 것뿐이며,
그래프 모양(들어오는 엣지가 없는 노드 등)으로 추론하지 않는다.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from agent_console_contracts import (
    EdgeScheduling,
    EdgeSpec,
    EdgeTypeDescriptor,
    Graph,
    NodeTypeDescriptor,
)

from ._index import latest_index
from ._topology import EdgeFilter, Topology, topology


@dataclass(frozen=True)
class ScheduleView:
    """그래프의 스케줄 관점 요약.

    모든 순서는 결정적이다(노드는 `graph.nodes`, 엣지는 `graph.edges` 순).

    타입을 모르는 엣지(디스크립터 없음)와 없는 노드를 가리키는 엣지는 어느 묶음에도 넣지 않는다.
    타입을 모르는 노드는 실행할 수 없는 노드로 본다(검증은 `validate_graph` 몫).

    Attributes:
        scheduling: 엣지 id → 디스크립터 `scheduling`.
        entry_edges / flow_edges / exit_edges / none_edges: 종류별 엣지 id.
        executable: 디스크립터 `executable`이 참인 노드 id.
        scheduled: 스케줄 대상 노드 = 실행 가능하고 `entry`나 `flow` 엣지가 하나 이상 들어오는 노드.
            호출 대상(위임받는 노드)·리소스 노드·연결이 덜 된 노드는 빠진다.
        entry_nodes: `entry` 엣지가 들어오는 실행 가능 노드(입구). 비어 있으면 실행할 입구가 없다.
        exit_nodes: `exit` 엣지가 나가는 노드(답변을 내는 노드).
        incoming: 스케줄 대상 노드 id → 들어오는 `entry`·`flow` 엣지 id(join 평가 대상).
        outgoing: 노드 id → 나가는 `flow` 엣지 id.
        exits: 노드 id → 나가는 `exit` 엣지 id.
        topology: `flow` 엣지만으로 계산한 위상 정보(순서·사이클).
    """

    scheduling: Mapping[str, EdgeScheduling]
    entry_edges: tuple[str, ...]
    flow_edges: tuple[str, ...]
    exit_edges: tuple[str, ...]
    none_edges: tuple[str, ...]
    executable: frozenset[str]
    scheduled: tuple[str, ...]
    entry_nodes: tuple[str, ...]
    exit_nodes: tuple[str, ...]
    incoming: Mapping[str, tuple[str, ...]]
    outgoing: Mapping[str, tuple[str, ...]]
    exits: Mapping[str, tuple[str, ...]]
    topology: Topology


def non_flow_edges(edge_types: Iterable[EdgeTypeDescriptor]) -> EdgeFilter:
    """`topology(ignore_edge=)`에 넘길 술어: 디스크립터 `scheduling`이 `flow`가 아니면 참.

    타입을 모르는 엣지는 거짓(계산에 포함). 엣지 타입은 같은 id 중 최신 버전을 쓴다.
    """
    index = latest_index(edge_types)

    def ignore(edge: EdgeSpec) -> bool:
        desc = index.get((edge.kind, None))
        return desc is not None and desc.scheduling != "flow"

    return ignore


def schedule_view(
    graph: Graph,
    node_types: Iterable[NodeTypeDescriptor],
    edge_types: Iterable[EdgeTypeDescriptor],
) -> ScheduleView:
    """그래프의 스케줄 관점 요약을 계산한다. 예외를 던지지 않는다.

    Args:
        graph: 대상 그래프. 중복 노드 id는 첫 번째만 쓴다.
        node_types: 노드 타입 디스크립터(여러 버전 가능). `NodeSpec.type_version`이 없으면 최신.
        edge_types: 엣지 타입 디스크립터. 같은 id 중 최신 버전을 쓴다.
    """
    node_index = latest_index(node_types)
    edge_index = latest_index(edge_types)

    node_ids: list[str] = []
    seen: set[str] = set()
    executable: set[str] = set()
    for node in graph.nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        node_ids.append(node.id)
        desc = node_index.get((node.type, node.type_version))
        if desc is not None and desc.executable:
            executable.add(node.id)

    scheduling: dict[str, EdgeScheduling] = {}
    groups: dict[EdgeScheduling, list[str]] = {"entry": [], "flow": [], "exit": [], "none": []}
    into: dict[str, list[str]] = {nid: [] for nid in node_ids}
    outgoing: dict[str, list[str]] = {nid: [] for nid in node_ids}
    exits: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in graph.edges:
        edesc = edge_index.get((edge.kind, None))
        src, dst = edge.source.node, edge.target.node
        if edesc is None or src not in seen or dst not in seen or edge.id in scheduling:
            continue
        kind = edesc.scheduling
        scheduling[edge.id] = kind
        groups[kind].append(edge.id)
        if kind in ("entry", "flow"):
            into[dst].append(edge.id)
        if kind == "flow":
            outgoing[src].append(edge.id)
        elif kind == "exit":
            exits[src].append(edge.id)

    scheduled = tuple(nid for nid in node_ids if nid in executable and into[nid])
    entry_targets = {nid for nid in node_ids if any(scheduling[e] == "entry" for e in into[nid])}
    return ScheduleView(
        scheduling=scheduling,
        entry_edges=tuple(groups["entry"]),
        flow_edges=tuple(groups["flow"]),
        exit_edges=tuple(groups["exit"]),
        none_edges=tuple(groups["none"]),
        executable=frozenset(executable),
        scheduled=scheduled,
        entry_nodes=tuple(nid for nid in node_ids if nid in executable and nid in entry_targets),
        exit_nodes=tuple(nid for nid in node_ids if exits[nid]),
        incoming={nid: tuple(into[nid]) for nid in scheduled},
        outgoing={nid: tuple(v) for nid, v in outgoing.items()},
        exits={nid: tuple(v) for nid, v in exits.items()},
        topology=topology(graph, ignore_edge=lambda e: scheduling.get(e.id, "flow") != "flow"),
    )
