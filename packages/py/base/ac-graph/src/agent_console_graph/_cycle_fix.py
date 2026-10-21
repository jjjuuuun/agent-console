"""사이클 오류의 수정 제안: 되돌아가는 연결을 사이클 연결 종류로 바꾸기(design §5R.4, 화면 S2).

연결 종류 이름을 모른다. 바꿀 종류는 `validate_graph(cycle_edge=)` 술어가 참이 되는 흐름 종류
(기본 술어 `descriptor_cycle_edge` = 디스크립터 `cycle`)이고, `connects`(노드 타입 `role`)가 맞고
엣지 config가 그 종류 스키마를 통과하는 첫 종류다. 제안은 데이터(`GraphPatch`)이고 사용자가 눌러야
적용된다.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from agent_console_contracts import (
    EdgeSpec,
    EdgeTypeDescriptor,
    GraphPatch,
    IssueSuggestion,
    NodeSpec,
    NodeTypeDescriptor,
)

type _Predicate = Callable[[EdgeSpec, EdgeTypeDescriptor], bool]
type _ConfigCheck = Callable[[EdgeTypeDescriptor, Mapping[str, Any]], bool]


def back_edges(
    members: Iterable[str],
    edges: Iterable[EdgeSpec],
    *,
    order: Mapping[str, int],
    entered: Iterable[str] = (),
) -> list[EdgeSpec]:
    """사이클 묶음(강한 연결 요소) 안에서 "되돌아가는" 연결.

    묶음 밖에서 들어오는 노드(`entered`) 중 그래프 순서가 가장 앞선 노드(없으면 묶음의 첫 노드)에서
    깊이 우선으로 따라가며(엣지는 그래프 순서) 탐색 경로 위 노드로 돌아가는 엣지를 모은다.

    Args:
        members: 묶음 노드 id.
        edges: 묶음 안 엣지(사이클 계산에 들어간 엣지만, 그래프 순서).
        order: 노드 id → 그래프 순서.
        entered: 묶음 밖에서 들어오는 엣지가 닿는 묶음 노드.
    """
    nodes = sorted(set(members), key=order.__getitem__)
    if not nodes:
        return []
    inside = set(nodes)
    succ: dict[str, list[EdgeSpec]] = {nid: [] for nid in nodes}
    for edge in edges:
        if edge.source.node in inside and edge.target.node in inside:
            succ[edge.source.node].append(edge)
    heads = sorted(set(entered) & inside, key=order.__getitem__)
    found: list[EdgeSpec] = []
    visited: set[str] = set()
    for root in [*heads, *nodes]:
        if root in visited:
            continue
        visited.add(root)
        on_path = {root}
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            nid, i = work.pop()
            out = succ[nid]
            if i >= len(out):
                on_path.discard(nid)
                continue
            work.append((nid, i + 1))
            edge = out[i]
            nxt = edge.target.node
            if nxt in on_path:
                found.append(edge)
            elif nxt not in visited:
                visited.add(nxt)
                on_path.add(nxt)
                work.append((nxt, 0))
    return found


def _role_ok(allowed: list[str], role: str | None) -> bool:
    return not allowed or (role is not None and role in allowed)


def _carried_config(desc: EdgeTypeDescriptor, config: Mapping[str, Any]) -> dict[str, Any]:
    """새 종류 스키마가 선언한 키만 옮긴다(선언이 없으면 아무것도 옮기지 않는다)."""
    props = desc.config_schema.get("properties")
    if not isinstance(props, Mapping):
        return {}
    return {k: v for k, v in config.items() if k in props}


def cycle_fix_suggestions(
    cycle_back_edges: Iterable[EdgeSpec],
    *,
    nodes: Mapping[str, NodeSpec],
    node_descriptor: Callable[[NodeSpec], NodeTypeDescriptor | None],
    edge_types: Iterable[EdgeTypeDescriptor],
    cycle_edge: _Predicate,
    config_ok: _ConfigCheck,
) -> list[IssueSuggestion]:
    """되돌아가는 연결마다 "'{B} → {A}' 연결을 '{종류}'로 바꾸기" 제안(맞는 종류가 없으면 없음).

    패치는 `remove_edge_ids=[원래 id]` + `add_edges=[같은 id·같은 포트·새 종류]`다. config는 새 종류
    스키마가 선언한 키만 옮기고, 그 결과가 스키마를 통과하지 않으면 빈 config로 다시 본다.

    Args:
        cycle_back_edges: 바꿀 후보 연결(`back_edges`).
        nodes: 노드 id → 노드.
        node_descriptor: 노드 → 노드 타입 디스크립터(역할 판정, 없으면 None).
        edge_types: 연결 종류 디스크립터(같은 id 중 최신만, 주어진 순서로 고른다).
        cycle_edge: 사이클 연결 술어(`validate_graph(cycle_edge=)`와 같은 것).
        config_ok: (종류, config) → 스키마 통과 여부.
    """
    suggestions: list[IssueSuggestion] = []
    kinds = list(edge_types)
    for edge in cycle_back_edges:
        src, dst = nodes.get(edge.source.node), nodes.get(edge.target.node)
        if src is None or dst is None:
            continue
        src_desc, dst_desc = node_descriptor(src), node_descriptor(dst)
        src_role = src_desc.role if src_desc is not None else None
        dst_role = dst_desc.role if dst_desc is not None else None
        for desc in kinds:
            if desc.id == edge.kind or desc.scheduling != "flow":
                continue
            if desc.ui_hints is not None and desc.ui_hints.hidden:
                continue
            connects = desc.connects
            if connects is not None and not (
                _role_ok(connects.source, src_role) and _role_ok(connects.target, dst_role)
            ):
                continue
            config = _carried_config(desc, edge.config)
            if not config_ok(desc, config):
                if not config or not config_ok(desc, {}):
                    continue
                config = {}
            replaced = edge.model_copy(update={"kind": desc.id, "config": config})
            if not cycle_edge(replaced, desc):
                continue
            a, b = src.label or src.id, dst.label or dst.id
            suggestions.append(
                IssueSuggestion(
                    id=f"cycle:{edge.id}:{desc.id}",
                    label=f"'{a} → {b}' 연결을 '{desc.title}'(으)로 바꾸기",
                    patch=GraphPatch(remove_edge_ids=[edge.id], add_edges=[replaced]),
                )
            )
            break
    return suggestions
