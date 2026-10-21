"""검증 이슈의 수정 제안 데이터(`Issue.suggestions`, design §R1.2a "제안 버튼").

자동 추론은 여기서만 쓴다. 제안은 그래프에 적용할 변경(`GraphPatch`)이며 사용자가 눌러야
데이터가 된다. 연결 종류는 디스크립터 속성
(`scheduling`·`interaction`·`connects`·`default_ports`)으로 고르고, 이름은 모른다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from typing import Any

from agent_console_contracts import (
    EdgeConnects,
    EdgeSpec,
    EdgeTypeDescriptor,
    Endpoint,
    GraphPatch,
    IssueSuggestion,
    NodeSpec,
    NodeTypeDescriptor,
    PortSpec,
    Position,
)
from agent_console_graph import InvalidSchemaError, PortResolver, check_instance, node_ports

from ._plan import TeamPlan

__all__ = ["SuggestionBuilder"]


def _latest[D: (NodeTypeDescriptor, EdgeTypeDescriptor)](descriptors: tuple[D, ...]) -> list[D]:
    """같은 id 중 최신 버전만, 처음 나온 순서."""
    best: dict[str, D] = {}
    order: list[str] = []
    for desc in descriptors:
        if desc.id not in best:
            order.append(desc.id)
            best[desc.id] = desc
        elif desc.version > best[desc.id].version:
            best[desc.id] = desc
    return [best[i] for i in order]


def _role_ok(allowed: list[str], role: str | None) -> bool:
    return not allowed or (role is not None and role in allowed)


def _first(spec: PortSpec | None, *, outputs: bool) -> str | None:
    if spec is None:
        return None
    ports = spec.outputs if outputs else spec.inputs
    return ports[0].name if ports else None


def _config_fits(desc: EdgeTypeDescriptor, config: Mapping[str, Any]) -> bool:
    try:
        return not check_instance(desc.config_schema, dict(config))
    except InvalidSchemaError:
        return False


def _carried(
    desc: EdgeTypeDescriptor, config: Mapping[str, Any], drop: Collection[str]
) -> dict[str, Any] | None:
    """새 종류 스키마가 선언한 키만 옮긴 config(통과 못 하면 빈 config, 그것도 안 되면 None)."""
    props = desc.config_schema.get("properties")
    kept = (
        {k: v for k, v in config.items() if k in props and k not in drop}
        if isinstance(props, Mapping)
        else {}
    )
    if _config_fits(desc, kept):
        return kept
    if kept and _config_fits(desc, {}):
        return {}
    return None


class SuggestionBuilder:
    """제안 하나를 만들 때마다 새 노드·엣지 id가 겹치지 않게 한다(한 번의 검증 안에서)."""

    def __init__(self, plan: TeamPlan, resolve_ports: PortResolver | None = None) -> None:
        self._plan = plan
        self._resolve = resolve_ports
        self._node_ids = {n.id for n in plan.graph.nodes}
        self._edge_ids = {e.id for e in plan.graph.edges}
        self._edge_types = _latest(plan.edge_types)
        self._node_types = _latest(plan.node_types)

    @staticmethod
    def _new_id(base: str, used: set[str]) -> str:
        candidate, n = base, 2
        while candidate in used:
            candidate, n = f"{base}-{n}", n + 1
        used.add(candidate)
        return candidate

    def _ports(self, node_id: str) -> PortSpec | None:
        desc = self._plan.node_descriptors.get(node_id)
        node = self._plan.node(node_id)
        if desc is None or node is None:
            return None
        try:
            return node_ports(desc, node.config, self._resolve)
        except Exception:
            return None

    def _outside_candidates(self, allowed: list[str], exclude: str) -> list[str]:
        plan = self._plan
        ordered = [n.id for n in plan.graph.nodes if n.id in plan.outside and n.id != exclude]
        return [nid for nid in dict.fromkeys(ordered) if _role_ok(allowed, plan.role_of(nid))]

    def _creatable(self, allowed: list[str]) -> NodeTypeDescriptor | None:
        if not allowed:
            return None
        for desc in self._node_types:
            hidden = desc.ui_hints is not None and desc.ui_hints.hidden
            if desc.role in allowed and desc.binds is None and not hidden:
                return desc
        return None

    def connect(
        self,
        *,
        node_id: str,
        node_is_source: bool,
        accept: Callable[[EdgeTypeDescriptor], bool],
        suggestion_id: str,
        label: str,
        node_port: str | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> IssueSuggestion | None:
        """`node_id`와 사용자 쪽 노드(입구의 출발·답변의 도착 노드)를 잇는 엣지를 제안한다.

        `accept`를 만족하고 `connects`가 맞는 첫 연결 종류를 쓴다. 맞는 사용자 쪽 노드가 없으면
        `connects` 반대편 역할의 노드 타입(정의에 묶이지 않고 숨기지 않은 첫 타입)으로 새로 만든다.
        포트: 디스크립터 `default_ports` → 노드 포트 목록의 첫 포트. 고를 수 없으면 None.
        """
        plan = self._plan
        role = plan.role_of(node_id)
        for edesc in self._edge_types:
            if not accept(edesc):
                continue
            connects = edesc.connects or EdgeConnects()
            mine, other_side = (
                (connects.source, connects.target)
                if node_is_source
                else (connects.target, connects.source)
            )
            if not _role_ok(mine, role):
                continue
            defaults = edesc.default_ports
            my_default = (
                (defaults.source if node_is_source else defaults.target) if defaults else None
            )
            other_default = (
                (defaults.target if node_is_source else defaults.source) if defaults else None
            )
            my_port = (
                node_port or my_default or _first(self._ports(node_id), outputs=node_is_source)
            )
            if my_port is None:
                continue
            add_nodes: list[NodeSpec] = []
            candidates = self._outside_candidates(other_side, node_id)
            if candidates:
                other = candidates[0]
                other_port = other_default or _first(self._ports(other), outputs=not node_is_source)
            else:
                ntype = self._creatable(other_side)
                if ntype is None:
                    continue
                other_port = other_default or _first(ntype.static_ports, outputs=not node_is_source)
                if other_port is None:
                    continue
                other = self._new_id(ntype.id, self._node_ids)
                node = plan.node(node_id)
                pos = node.position if node is not None else None
                add_nodes.append(
                    NodeSpec(
                        id=other,
                        type=ntype.id,
                        label=ntype.title,
                        position=Position(x=pos.x + (240 if node_is_source else -240), y=pos.y)
                        if pos is not None
                        else None,
                    )
                )
            if other_port is None:
                continue
            here = Endpoint(node=node_id, port=my_port)
            there = Endpoint(node=other, port=other_port)
            edge = EdgeSpec(
                id=self._new_id(f"{edesc.id}-{node_id}", self._edge_ids),
                source=here if node_is_source else there,
                target=there if node_is_source else here,
                kind=edesc.id,
                config=dict(config or {}),
            )
            return IssueSuggestion(
                id=suggestion_id,
                label=label,
                patch=GraphPatch(add_nodes=add_nodes, add_edges=[edge]),
            )
        return None

    def replace_kind(
        self,
        edge: EdgeSpec,
        *,
        accept: Callable[[EdgeTypeDescriptor], bool],
        suggestion_id: str,
        label: Callable[[EdgeTypeDescriptor], str],
        drop_keys: Collection[str] = (),
        prefer: Callable[[EdgeTypeDescriptor], bool] | None = None,
    ) -> IssueSuggestion | None:
        """연결 종류만 바꾸는 제안(같은 id·같은 포트, 화면 명세 S2).

        패치는 `remove_edge_ids` + `add_edges`다.

        `accept`를 만족하고 `connects`가 두 끝 노드 역할에 맞는 종류(지금 종류 제외) 중 `prefer`가
        참인 첫 종류, 없으면 첫 종류를 쓴다. config는 새 종류 스키마가 선언한 키만 옮기고
        (`drop_keys` 제외) 스키마를 통과하지 않으면 빈 config로 다시 본다. 고를 수 없으면 None.
        """
        plan = self._plan
        src_role, dst_role = plan.role_of(edge.source.node), plan.role_of(edge.target.node)
        found: list[tuple[EdgeTypeDescriptor, dict[str, Any]]] = []
        for desc in self._edge_types:
            if desc.id == edge.kind or not accept(desc):
                continue
            if desc.ui_hints is not None and desc.ui_hints.hidden:
                continue
            connects = desc.connects or EdgeConnects()
            if not (_role_ok(connects.source, src_role) and _role_ok(connects.target, dst_role)):
                continue
            config = _carried(desc, edge.config, drop_keys)
            if config is None:
                continue
            found.append((desc, config))
        if not found:
            return None
        desc, config = next(
            (item for item in found if prefer is not None and prefer(item[0])), found[0]
        )
        replaced = edge.model_copy(update={"kind": desc.id, "config": config})
        return IssueSuggestion(
            id=suggestion_id,
            label=label(desc),
            patch=GraphPatch(remove_edge_ids=[edge.id], add_edges=[replaced]),
        )

    def narrow(
        self, edge: EdgeSpec, kinds: list[str], *, kinds_key: str, suggestion_id: str
    ) -> IssueSuggestion:
        """상호작용 연결의 허용 종류를 `kinds`로 좁히는 제안(비면 연결 삭제)."""
        if not kinds:
            return IssueSuggestion(
                id=suggestion_id,
                label="이 연결 삭제",
                patch=GraphPatch(remove_edge_ids=[edge.id]),
            )
        replaced = edge.model_copy(update={"config": {**edge.config, kinds_key: list(kinds)}})
        return IssueSuggestion(
            id=suggestion_id,
            label=f"허용 종류를 {', '.join(kinds)}(으)로 좁히기",
            patch=GraphPatch(remove_edge_ids=[edge.id], add_edges=[replaced]),
        )
