"""위상 정렬·진입/종료 노드·사이클(강한 연결 요소) 계산."""

import heapq
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from agent_console_contracts import EdgeSpec, Graph

type EdgeFilter = Callable[[EdgeSpec], bool]
"""참이면 그 엣지를 위상 계산에서 뺀다(예: 반복 경계 엣지)."""


@dataclass(frozen=True)
class Topology:
    """그래프 구조 요약. 모든 순서는 결정적이다(같은 입력 → 같은 결과).

    Attributes:
        order: 위상 정렬된 노드 id. 동률은 `graph.nodes` 순서. 사이클이 있으면
            사이클에 속하거나 그 하류에 있는 노드는 빠진다(`is_dag`로 확인).
        entry_nodes: 들어오는 엣지가 없는 노드(`graph.nodes` 순서).
        exit_nodes: 나가는 엣지가 없는 노드(`graph.nodes` 순서).
        incoming: 노드 id → 들어오는 엣지 id(`graph.edges` 순서).
        outgoing: 노드 id → 나가는 엣지 id(`graph.edges` 순서).
        cycles: 사이클을 이루는 노드 묶음(강한 연결 요소 중 크기 ≥2 또는 자기 루프).
            각 묶음 안은 `graph.nodes` 순서, 묶음끼리는 첫 노드의 순서.
    """

    order: tuple[str, ...]
    entry_nodes: tuple[str, ...]
    exit_nodes: tuple[str, ...]
    incoming: Mapping[str, tuple[str, ...]]
    outgoing: Mapping[str, tuple[str, ...]]
    cycles: tuple[tuple[str, ...], ...]

    @property
    def is_dag(self) -> bool:
        """사이클이 없으면 참."""
        return not self.cycles


def topology(graph: Graph, *, ignore_edge: EdgeFilter | None = None) -> Topology:
    """그래프의 위상 정보를 계산한다. 예외를 던지지 않는다.

    - 중복 노드 id는 첫 번째만 쓴다. 없는 노드를 가리키는 엣지는 무시한다.
    - `ignore_edge(edge)`가 참인 엣지는 순서·진입/종료·사이클 계산에서 빠진다.
      (`incoming`/`outgoing`에도 포함되지 않는다.)
    """
    node_ids: list[str] = []
    seen: set[str] = set()
    for node in graph.nodes:
        if node.id not in seen:
            seen.add(node.id)
            node_ids.append(node.id)
    rank = {nid: i for i, nid in enumerate(node_ids)}

    incoming: dict[str, list[str]] = {nid: [] for nid in node_ids}
    outgoing: dict[str, list[str]] = {nid: [] for nid in node_ids}
    succ: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in graph.edges:
        src, dst = edge.source.node, edge.target.node
        if src not in seen or dst not in seen:
            continue
        if ignore_edge is not None and ignore_edge(edge):
            continue
        outgoing[src].append(edge.id)
        incoming[dst].append(edge.id)
        succ[src].append(dst)

    indegree = {nid: len(incoming[nid]) for nid in node_ids}
    # 준비된 노드 중 graph.nodes 순서(rank)가 가장 앞선 것부터 꺼낸다.
    ready = [(rank[nid], nid) for nid in node_ids if indegree[nid] == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, nid = heapq.heappop(ready)
        order.append(nid)
        for nxt in succ[nid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, (rank[nxt], nxt))

    cycles = _cycles(node_ids, succ, rank) if len(order) < len(node_ids) else ()
    return Topology(
        order=tuple(order),
        entry_nodes=tuple(nid for nid in node_ids if not incoming[nid]),
        exit_nodes=tuple(nid for nid in node_ids if not outgoing[nid]),
        incoming={nid: tuple(v) for nid, v in incoming.items()},
        outgoing={nid: tuple(v) for nid, v in outgoing.items()},
        cycles=cycles,
    )


def _cycles(
    node_ids: list[str], succ: Mapping[str, list[str]], rank: Mapping[str, int]
) -> tuple[tuple[str, ...], ...]:
    """Tarjan SCC(반복형). 크기 ≥2 또는 자기 루프인 요소만 돌려준다."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[tuple[str, ...]] = []
    counter = 0

    for root in node_ids:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            nid, i = work.pop()
            if i == 0:
                index[nid] = low[nid] = counter
                counter += 1
                stack.append(nid)
                on_stack.add(nid)
            nexts = succ[nid]
            if i < len(nexts):
                work.append((nid, i + 1))
                nxt = nexts[i]
                if nxt not in index:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[nid] = min(low[nid], index[nxt])
                continue
            if low[nid] == index[nid]:
                comp: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    comp.append(member)
                    if member == nid:
                        break
                if len(comp) > 1 or nid in succ[nid]:
                    found.append(tuple(sorted(comp, key=rank.__getitem__)))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[nid])
    found.sort(key=lambda comp: rank[comp[0]])
    return tuple(found)
