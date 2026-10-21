"""레지스트리에 등록된 타입으로 그래프를 검증한다(ac-graph `validate_graph` 어댑터)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from agent_console_contracts import (
    EdgeTypeDescriptor,
    Graph,
    Issue,
    NodeSpec,
    NodeTypeDescriptor,
    PortSpec,
)
from agent_console_graph import PortResolver, descriptor_cycle_edge, validate_graph

from ._interfaces import EdgeValidationContext, EdgeValidator, ValidationContext
from ._registries import Registries
from ._services import Services


class GraphValidationError(ValueError):
    """그래프에 error 이슈가 있어 실행할 수 없다. `issues`에 전체 이슈."""

    def __init__(self, issues: list[Issue]) -> None:
        errors = [i for i in issues if i.severity == "error"]
        super().__init__(f"그래프 검증 실패: 오류 {len(errors)}개")
        self.issues = issues


def port_resolver(registries: Registries) -> PortResolver:
    """ac-graph `PortResolver`: 디스크립터 id·version으로 노드 타입을 찾아 `resolve_ports` 호출."""

    def resolve(descriptor: NodeTypeDescriptor, config: Mapping[str, Any], /) -> PortSpec:
        return registries.node_types.get(descriptor.id, descriptor.version).resolve_ports(config)

    return resolve


def node_type_descriptors(registries: Registries) -> list[NodeTypeDescriptor]:
    """등록된 모든 노드 타입 디스크립터(모든 버전)."""
    return [e.item.descriptor for e in registries.node_types.list(all_versions=True)]


def edge_type_descriptors(registries: Registries) -> list[EdgeTypeDescriptor]:
    """등록된 모든 엣지 타입 디스크립터(모든 버전)."""
    return [e.item.descriptor for e in registries.edge_types.list(all_versions=True)]


def validate_graph_with(
    graph: Graph, registries: Registries, *, services: Services | None = None
) -> list[Issue]:
    """레지스트리 기준으로 그래프를 검증한다(구조·config 스키마·포트·사이클·노드 의미 검증).

    흐름 사이클은 사이클 연결(연결 종류 디스크립터 `cycle`, `descriptor_cycle_edge`)이 하나 이상
    있을 때만 허용한다(design §5R.4). 노드 의미 검증은 `NodeType.validate`.
    """
    svc = services or Services()

    def validate_node(node: NodeSpec, descriptor: NodeTypeDescriptor) -> Iterable[Issue]:
        impl = registries.node_types.get(descriptor.id, descriptor.version)
        ctx = ValidationContext(graph=graph, node=node, registries=registries, services=svc)
        return impl.validate(node.config, ctx)

    issues = validate_graph(
        graph,
        node_type_descriptors(registries),
        edge_type_descriptors(registries),
        resolve_ports=port_resolver(registries),
        cycle_edge=descriptor_cycle_edge,
        validate_node=validate_node,
    )
    issues.extend(validate_edges(graph, registries, svc))
    return issues


def validate_edges(graph: Graph, registries: Registries, services: Services) -> list[Issue]:
    """선택 능력 `EdgeValidator`를 가진 엣지 타입의 의미 검증(모르는 타입은 건너뜀)."""
    issues: list[Issue] = []
    for edge in graph.edges:
        if edge.kind not in registries.edge_types:
            continue
        impl = registries.edge_types.get(edge.kind)
        if not isinstance(impl, EdgeValidator):
            continue
        ctx = EdgeValidationContext(
            graph=graph, edge=edge, registries=registries, services=services
        )
        for issue in impl.validate_edge(edge, ctx):
            issues.append(issue if issue.edge_id else issue.model_copy(update={"edge_id": edge.id}))
    return issues
