"""반복 영역(사이클 연결) 계산(design §5R.4). 연결 종류 이름을 모르고 디스크립터 `cycle`만 본다."""

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from agent_console_contracts import EdgeSpec, EdgeTypeDescriptor, Graph

from ._index import latest_index

CYCLE_LIMIT_CONFIG_KEY: Final = "max_iterations"
"""사이클 연결 엣지 config에서 최대 반복을 덮어쓰는 키(design §5R.2, 계약 이슈
`flow.max_iterations_invalid`의 path `/max_iterations`와 같은 약속). 연결 종류의 config 스키마가
이 키를 선언한다."""


def descriptor_cycle_edge(edge: EdgeSpec, descriptor: EdgeTypeDescriptor) -> bool:
    """`validate_graph(cycle_edge=)`용 술어: 연결 종류 디스크립터에 `cycle` 정책이 있으면 참.

    이 엣지는 흐름 사이클을 닫을 수 있다(사이클 연결). 엣지 자체(config)는 보지 않는다.
    """
    return descriptor.cycle is not None


@dataclass(frozen=True)
class LoopRegion:
    """사이클 연결 하나가 다시 여는 반복 영역.

    Attributes:
        edge_id: 사이클 연결 id.
        nodes: 영역 노드 id(`graph.nodes` 순서). `entry`·`exit` 포함.
        entry: 사이클 연결의 도착 노드(다음 회차의 시작, 값이 들어가는 곳).
        exit: 사이클 연결의 출발 노드(회차를 닫는 노드).
    """

    edge_id: str
    nodes: tuple[str, ...]
    entry: str
    exit: str


def loop_regions(graph: Graph, edge_types: Iterable[EdgeTypeDescriptor]) -> dict[str, LoopRegion]:
    """사이클 연결마다 반복 영역을 계산한다(순수 함수, 예외 없음).

    영역 = 사이클 연결 `e(s → t)`에 대해 `t`에서 출발해 `s`에 닿는 경로 위의 노드(`s`·`t` 포함).
    경로는 `scheduling = flow` 연결만 따르고, **모든 사이클 연결은 뺀다**(그래서 사이클 연결이 있는
    사이클을 허용한 그래프에서 영역은 DAG 위의 구간이다. 중첩 반복의 안쪽 영역은 바깥 영역의 부분
    집합이 된다). 자기 자신으로 돌아가는 연결(`s = t`)의 영역은 `(s,)`다.

    `t`에서 `s`에 닿지 못하는 사이클 연결(사이클을 닫지 않는 앞쪽 연결)과 없는 노드를 가리키는
    연결은 결과에 없다(엔진은 보통 흐름 연결로 다룬다).

    Args:
        graph: 대상 그래프. 중복 노드 id는 첫 번째만 쓴다.
        edge_types: 연결 종류 디스크립터. 같은 id 중 최신 버전을 쓴다. 모르는 종류는 사이클 연결이
            아니며 흐름 연결로 본다(`validate_graph`와 같다).

    Returns:
        사이클 연결 id → 영역(`graph.edges` 순서).
    """
    index = latest_index(edge_types)
    order: dict[str, int] = {}
    for node in graph.nodes:
        order.setdefault(node.id, len(order))
    succ: dict[str, list[str]] = {nid: [] for nid in order}
    pred: dict[str, list[str]] = {nid: [] for nid in order}
    cycles: list[EdgeSpec] = []
    seen_edges: set[str] = set()
    for edge in graph.edges:
        if edge.id in seen_edges:
            continue
        seen_edges.add(edge.id)
        src, dst = edge.source.node, edge.target.node
        if src not in order or dst not in order:
            continue
        desc = index.get((edge.kind, None))
        if desc is not None and desc.scheduling != "flow":
            continue
        if desc is not None and descriptor_cycle_edge(edge, desc):
            cycles.append(edge)
            continue
        succ[src].append(dst)
        pred[dst].append(src)

    regions: dict[str, LoopRegion] = {}
    for edge in cycles:
        exit_node, entry_node = edge.source.node, edge.target.node
        forward = _reach(entry_node, succ)
        if exit_node not in forward:
            continue
        backward = _reach(exit_node, pred)
        members = sorted(forward & backward, key=order.__getitem__)
        regions[edge.id] = LoopRegion(
            edge_id=edge.id, nodes=tuple(members), entry=entry_node, exit=exit_node
        )
    return regions


def effective_max_iterations(
    edge: EdgeSpec, descriptor: EdgeTypeDescriptor, settings_value: int | None = None
) -> int | None:
    """사이클 연결의 유효 최대 반복(design §5R.4 1).

    순서(생략 = 상속): 엣지 config `max_iterations`(`CYCLE_LIMIT_CONFIG_KEY`) → 설정
    `flow.max_iterations`(`settings_value`) → 디스크립터 `cycle.max_iterations`.

    Returns:
        유효 값. 사이클 연결이 아니거나(디스크립터 `cycle` 없음) 엣지 config 값이 정수가 아니면
        None. 1 미만인 값도 그대로 돌려준다(검증·엔진이 판단한다).
    """
    policy = descriptor.cycle
    if policy is None:
        return None
    raw: Any = edge.config.get(CYCLE_LIMIT_CONFIG_KEY)
    if raw is not None:
        if isinstance(raw, bool) or not isinstance(raw, int):
            return None
        return raw
    if settings_value is not None:
        return settings_value
    return policy.max_iterations


def _reach(start: str, adjacency: Mapping[str, list[str]]) -> set[str]:
    found = {start}
    work = deque([start])
    while work:
        for nxt in adjacency[work.popleft()]:
            if nxt not in found:
                found.add(nxt)
                work.append(nxt)
    return found
