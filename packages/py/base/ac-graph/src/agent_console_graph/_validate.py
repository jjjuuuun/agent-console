"""그래프 구조 검증. 문제는 예외가 아니라 `Issue` 목록으로 돌려준다."""

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final, Literal

from agent_console_contracts import (
    EdgeSpec,
    EdgeTypeDescriptor,
    Graph,
    Issue,
    IssueSuggestion,
    NodeSpec,
    NodeTypeDescriptor,
    PortSpec,
)

from ._cycle_fix import back_edges, cycle_fix_suggestions
from ._index import latest_index
from ._ports import PortResolver, node_ports
from ._schema import InvalidSchemaError, SchemaChecker, compile_schema
from ._topology import topology


class GraphIssueCodes:
    """`validate_graph`가 내는 `Issue.code` 값. 모두 severity="error"다(`PORTS_UNRESOLVED` 제외)."""

    DUPLICATE_NODE_ID: Final = "duplicate_node_id"
    DUPLICATE_EDGE_ID: Final = "duplicate_edge_id"
    UNKNOWN_NODE_TYPE: Final = "unknown_node_type"
    UNKNOWN_EDGE_TYPE: Final = "unknown_edge_type"
    INVALID_CONFIG: Final = "invalid_config"
    INVALID_CONFIG_SCHEMA: Final = "invalid_config_schema"
    PORT_RESOLUTION_FAILED: Final = "port_resolution_failed"
    PORTS_UNRESOLVED: Final = "ports_unresolved"  # warning: 동적 포트인데 해석기 없음
    UNKNOWN_NODE: Final = "unknown_node"
    UNKNOWN_PORT: Final = "unknown_port"
    CYCLE: Final = "cycle"


type CycleEdgePredicate = Callable[[EdgeSpec, EdgeTypeDescriptor], bool]
"""참이면 그 엣지는 사이클을 만들어도 된다(사이클 검사에서 뺀다). 예: 반복 경계 엣지 타입."""

type NodeValidator = Callable[[NodeSpec, NodeTypeDescriptor], Iterable[Issue]]
"""스키마 외 의미 검증(주입). config가 스키마를 통과한 노드에만 호출한다."""

_C = GraphIssueCodes


def validate_graph(
    graph: Graph,
    node_types: Iterable[NodeTypeDescriptor],
    edge_types: Iterable[EdgeTypeDescriptor],
    *,
    resolve_ports: PortResolver | None = None,
    cycle_edge: CycleEdgePredicate | None = None,
    validate_node: NodeValidator | None = None,
) -> list[Issue]:
    """그래프를 검증해 이슈 목록을 돌려준다. 빈 목록이면 통과.

    그래프 문제로는 예외를 던지지 않는다. `resolve_ports`의 예외는 이슈로 바꾸지만,
    `cycle_edge`·`validate_node`가 던진 예외는 호출자 버그로 보고 그대로 전파한다.

    Args:
        graph: 검사할 그래프.
        node_types: 사용할 수 있는 노드 타입 디스크립터(여러 버전 가능). `NodeSpec.type_version`이
            없으면 같은 id 중 최신 버전을 쓴다.
        edge_types: 사용할 수 있는 엣지 타입 디스크립터. 같은 id 중 최신 버전을 쓴다.
        resolve_ports: 동적 포트(`dynamic_ports=True`) 해석기. 없으면 그 노드의 포트 검사는
            건너뛰고 `ports_unresolved` 경고를 낸다.
        cycle_edge: 사이클을 허용할 흐름 엣지 판정. 없으면 흐름 엣지 사이클은 모두 오류(DAG만 허용).
            디스크립터 `scheduling`이 `flow`가 아닌 엣지(`none`·`entry`·`exit`)는 이 판정과 무관하게
            사이클 계산에서 빠진다(design §R3.1). 타입을 모르는 엣지는 사이클 계산에 포함한다.
            이 술어를 주면 `cycle` 이슈에 수정 제안(`suggestions`)이 붙는다: 사이클 안의 되돌아가는
            연결마다, 바꿨을 때 이 술어가 참이 되는 흐름 종류(`connects`·config 스키마가 맞는 첫
            종류)로 바꾸는 `GraphPatch`(`remove_edge_ids` + `add_edges`, 같은 id·포트). 맞는 종류가
            없으면 제안도 없고 문구도 그대로다.
        validate_node: 노드별 추가 의미 검증. 돌려준 이슈에 `node_id`가 없으면 채운다.

    검사 순서(결과 순서): 중복 id → 노드(타입·config·포트) → 엣지(타입·config·끝점·포트) → 사이클.
    포트를 알 수 없는 노드(타입 없음·config 오류·해석 실패)에 붙은 끝점의 포트는 검사하지 않는다.
    """
    issues: list[Issue] = []
    node_index = latest_index(node_types)
    edge_index = latest_index(edge_types)
    checkers = _CheckerCache()

    nodes: dict[str, NodeSpec] = {}
    for node in graph.nodes:
        if node.id in nodes:
            issues.append(
                _err(
                    _C.DUPLICATE_NODE_ID,
                    f"같은 id를 쓰는 노드가 여럿 있습니다: '{_name(node, node_index)}'",
                    node.id,
                    details={"node_id": node.id},
                )
            )
        else:
            nodes[node.id] = node
    edge_ids: set[str] = set()
    for edge in graph.edges:
        if edge.id in edge_ids:
            issues.append(
                _err(
                    _C.DUPLICATE_EDGE_ID,
                    "같은 id를 쓰는 연결이 여럿 있습니다",
                    edge_id=edge.id,
                    details={"edge_id": edge.id},
                )
            )
        edge_ids.add(edge.id)

    ports: dict[str, PortSpec] = {}
    for node in nodes.values():
        ok, node_issues = _check_node(node, node_index, checkers, resolve_ports, validate_node)
        issues.extend(node_issues)
        if ok is not None:
            ports[node.id] = ok

    edge_descs: dict[str, EdgeTypeDescriptor] = {}
    for edge in graph.edges:
        desc = edge_index.get((edge.kind, None))
        if desc is None:
            issues.append(
                _err(
                    _C.UNKNOWN_EDGE_TYPE,
                    f"알 수 없는 엣지 타입 {edge.kind!r}",
                    edge_id=edge.id,
                    details={"kind": edge.kind},
                )
            )
        else:
            edge_descs.setdefault(edge.id, desc)
            issues.extend(_config_issues(checkers, desc, edge.config, edge_id=edge.id))
        for end in ("source", "target"):
            issues.extend(_endpoint_issues(edge, end, nodes, ports, node_index))

    def ignore(edge: EdgeSpec) -> bool:
        desc = edge_descs.get(edge.id)
        if desc is None:
            return False
        if desc.scheduling != "flow":
            return True
        return cycle_edge is not None and cycle_edge(edge, desc)

    for cycle in topology(graph, ignore_edge=ignore).cycles:
        suggestions = (
            _cycle_suggestions(
                graph, cycle, nodes, node_index, edge_index, ignore, cycle_edge, checkers
            )
            if cycle_edge is not None
            else []
        )
        issue = _err(
            _C.CYCLE,
            _cycle_message(cycle, nodes, suggestions, node_index),
            details={"nodes": list(cycle)},
        )
        if suggestions:
            issue = issue.model_copy(update={"suggestions": suggestions})
        issues.append(issue)
    return issues


def _cycle_message(
    cycle: tuple[str, ...],
    nodes: Mapping[str, NodeSpec],
    suggestions: list[IssueSuggestion],
    index: Mapping[tuple[str, int | None], NodeTypeDescriptor],
) -> str:
    """사이클 문구(노드 이름, id는 `details.nodes`). 제안이 있으면 고칠 방법을 덧붙인다."""
    names = [_name(n, index) if (n := nodes.get(nid)) is not None else "?" for nid in cycle]
    if not suggestions:
        return "흐름이 되돌아 도는 사이클이 있습니다: " + " → ".join([*names, names[0]])
    path = " → ".join([*names, names[0]])
    return (
        f"흐름이 되돌아 도는 사이클이 있습니다: {path}. "
        "되돌아가는 연결 하나를 반복(사이클) 연결 종류로 바꾸세요."
    )


def _cycle_suggestions(
    graph: Graph,
    cycle: tuple[str, ...],
    nodes: Mapping[str, NodeSpec],
    node_index: Mapping[tuple[str, int | None], NodeTypeDescriptor],
    edge_index: Mapping[tuple[str, int | None], EdgeTypeDescriptor],
    ignore: Callable[[EdgeSpec], bool],
    cycle_edge: CycleEdgePredicate,
    checkers: "_CheckerCache",
) -> list[IssueSuggestion]:
    """사이클 묶음의 되돌아가는 연결을 사이클 연결 종류로 바꾸는 제안(`_cycle_fix`)."""
    members = set(cycle)
    order = {n.id: i for i, n in reversed(list(enumerate(graph.nodes)))}
    inner = [
        e
        for e in graph.edges
        if e.source.node in members and e.target.node in members and not ignore(e)
    ]
    entered = []
    for e in graph.edges:
        if e.target.node not in members or e.source.node in members:
            continue
        desc = edge_index.get((e.kind, None))
        if desc is None or desc.scheduling in ("entry", "flow"):
            entered.append(e.target.node)

    def config_ok(desc: EdgeTypeDescriptor, config: Mapping[str, Any]) -> bool:
        return not _config_issues(checkers, desc, config, edge_id="")

    return cycle_fix_suggestions(
        back_edges(members, inner, order=order, entered=entered),
        nodes=nodes,
        node_descriptor=lambda n: node_index.get((n.type, n.type_version)),
        edge_types=[d for (_, version), d in edge_index.items() if version is None],
        cycle_edge=cycle_edge,
        config_ok=config_ok,
    )


def _check_node(
    node: NodeSpec,
    index: Mapping[tuple[str, int | None], NodeTypeDescriptor],
    checkers: "_CheckerCache",
    resolve_ports: PortResolver | None,
    validate_node: NodeValidator | None,
) -> tuple[PortSpec | None, list[Issue]]:
    """노드 하나 검사. 포트를 알 수 있으면 (포트, 이슈), 아니면 (None, 이슈)."""
    desc = index.get((node.type, node.type_version))
    if desc is None:
        version = "" if node.type_version is None else f" (버전 {node.type_version})"
        return None, [
            _err(
                _C.UNKNOWN_NODE_TYPE,
                (
                    f"{_label_prefix(node)}노드 종류 '{node.type}'{version}을(를) 알 수 없습니다. "
                    "그 종류를 주는 확장이 설치·활성화되어 있는지 확인하세요"
                ),
                node.id,
                details={"type": node.type, "type_version": node.type_version},
            )
        ]
    issues = _config_issues(checkers, desc, node.config, node_id=node.id)
    if issues:
        return None, issues
    if validate_node is not None:
        for issue in validate_node(node, desc):
            if issue.node_id is None and issue.edge_id is None:
                issue = issue.model_copy(update={"node_id": node.id})
            issues.append(issue)
    if desc.dynamic_ports and resolve_ports is None:
        issues.append(
            Issue(
                severity="warning",
                code=_C.PORTS_UNRESOLVED,
                message=f"노드 타입 {desc.id!r}의 동적 포트를 해석할 수 없어 포트 검사를 생략",
                node_id=node.id,
            )
        )
        return None, issues
    try:
        return node_ports(desc, node.config, resolve_ports), issues
    except Exception as exc:
        issues.append(
            _err(
                _C.PORT_RESOLUTION_FAILED,
                f"포트 해석 실패: {exc}",
                node.id,
                path="",
                details={"error": type(exc).__name__},
            )
        )
        return None, issues


class _CheckerCache:
    """`validate_graph` 호출 한 번 안에서 디스크립터별 검사기(또는 스키마 오류)를 재사용."""

    def __init__(self) -> None:
        self._items: dict[int, SchemaChecker | InvalidSchemaError] = {}

    def get(self, desc: NodeTypeDescriptor | EdgeTypeDescriptor) -> SchemaChecker:
        # 디스크립터는 호출 동안 index가 붙잡고 있으므로 id()가 재사용되지 않는다.
        key = id(desc)
        item = self._items.get(key)
        if item is None:
            try:
                item = compile_schema(desc.config_schema)
            except InvalidSchemaError as exc:
                item = exc
            self._items[key] = item
        if isinstance(item, InvalidSchemaError):
            raise item
        return item


def _config_issues(
    checkers: _CheckerCache,
    desc: NodeTypeDescriptor | EdgeTypeDescriptor,
    config: Mapping[str, Any],
    *,
    node_id: str | None = None,
    edge_id: str | None = None,
) -> list[Issue]:
    try:
        violations = checkers.get(desc)(dict(config))
    except InvalidSchemaError as exc:
        return [
            _err(
                _C.INVALID_CONFIG_SCHEMA,
                f"타입의 config_schema가 잘못되었습니다: {exc}",
                node_id,
                edge_id=edge_id,
                path="",
            )
        ]
    return [
        _err(
            _C.INVALID_CONFIG,
            v.message,
            node_id,
            edge_id=edge_id,
            path=v.pointer,
            details={"validator": v.validator, "schema_path": v.schema_path},
        )
        for v in violations
    ]


def _endpoint_issues(
    edge: EdgeSpec,
    end: Literal["source", "target"],
    nodes: Mapping[str, NodeSpec],
    ports: Mapping[str, PortSpec],
    index: Mapping[tuple[str, int | None], NodeTypeDescriptor],
) -> list[Issue]:
    ep = edge.source if end == "source" else edge.target
    side_name = "출발" if end == "source" else "도착"
    if ep.node not in nodes:
        return [
            _err(
                _C.UNKNOWN_NODE,
                f"연결의 {side_name} 노드가 팀 구성에 없습니다",
                edge_id=edge.id,
                details={"end": end, "node": ep.node},
            )
        ]
    spec = ports.get(ep.node)
    if spec is None:
        return []
    side = spec.outputs if end == "source" else spec.inputs
    names = [p.name for p in side]
    if ep.port in names:
        return []
    kind = "출력" if end == "source" else "입력"
    return [
        _err(
            _C.UNKNOWN_PORT,
            f"'{_name(nodes[ep.node], index)}'에 {kind} 포트 '{ep.port}'가 없습니다",
            edge_id=edge.id,
            details={"end": end, "node": ep.node, "port": ep.port, "available": names},
        )
    ]


def _name(node: NodeSpec, index: Mapping[tuple[str, int | None], NodeTypeDescriptor]) -> str:
    """사용자 문구의 노드 이름: `label` → 노드 타입 `title` → 타입 id(노드 id는 쓰지 않는다)."""
    if node.label:
        return node.label
    desc = index.get((node.type, node.type_version))
    return desc.title if desc is not None else node.type


def _label_prefix(node: NodeSpec) -> str:
    return f"'{node.label}'의 " if node.label else ""


def _err(
    code: str,
    message: str,
    node_id: str | None = None,
    *,
    edge_id: str | None = None,
    path: str | None = None,
    details: dict[str, Any] | None = None,
) -> Issue:
    return Issue(
        severity="error",
        code=code,
        message=message,
        node_id=node_id,
        edge_id=edge_id,
        path=path,
        details=details or {},
    )
