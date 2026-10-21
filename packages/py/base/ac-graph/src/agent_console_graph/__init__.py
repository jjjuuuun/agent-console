"""agent-console-graph: 그래프 정의 순수 로직.

구조 검증, 포트 해석, 위상 정렬·사이클 검사, 버전 해시.

특정 노드·엣지 타입을 모른다. 타입 목록(디스크립터)과 동적 포트 해석기는 인자로 받는다.

공개 API:
    - ``validate_graph(graph, node_types, edge_types, *, resolve_ports, cycle_edge, validate_node)``
      → ``list[Issue]``. 코드 값은 ``GraphIssueCodes``.
    - ``graph_hash(graph)`` / ``canonical_graph(graph)``: 의미 있는 변경에만 바뀌는 버전 해시.
    - ``topology(graph, *, ignore_edge)`` → ``Topology``(위상 순서, 진입/종료 노드, 사이클).
    - ``node_ports(descriptor, config, resolve_ports)`` / ``PortResolver``: 노드 포트 해석.
    - ``schedule_view(graph, node_types, edge_types)`` → ``ScheduleView``: 엣지 디스크립터
      ``scheduling``(flow·none·entry·exit)과 노드 ``executable``로 본 입구·답변·스케줄 대상.
    - ``non_flow_edges(edge_types)``: ``topology(ignore_edge=)``용 술어(flow가 아닌 엣지 제외).
    - 반복(design §5R.4): ``descriptor_cycle_edge``(``validate_graph(cycle_edge=)``용 술어 —
      디스크립터 ``cycle``이 있으면 사이클 연결), ``loop_regions(graph, edge_types)`` →
      ``{edge_id: LoopRegion}``, ``effective_max_iterations(edge, descriptor, settings_value)``
      (엣지 config ``max_iterations`` → 설정 → 디스크립터), ``CYCLE_LIMIT_CONFIG_KEY``.
    - ``compile_schema(schema)`` / ``check_instance(schema, value)`` → ``list[SchemaViolation]``:
      JSON Schema 검사(외부 ``$ref``를 가져오지 않음). 잘못된 스키마는 ``InvalidSchemaError``.
"""

from agent_console_graph._hash import HASH_ALGORITHM, canonical_graph, graph_hash
from agent_console_graph._loops import (
    CYCLE_LIMIT_CONFIG_KEY,
    LoopRegion,
    descriptor_cycle_edge,
    effective_max_iterations,
    loop_regions,
)
from agent_console_graph._ports import PortResolver, PortsUnavailableError, node_ports
from agent_console_graph._schedule import ScheduleView, non_flow_edges, schedule_view
from agent_console_graph._schema import (
    InvalidSchemaError,
    SchemaChecker,
    SchemaViolation,
    check_instance,
    compile_schema,
)
from agent_console_graph._topology import EdgeFilter, Topology, topology
from agent_console_graph._validate import (
    CycleEdgePredicate,
    GraphIssueCodes,
    NodeValidator,
    validate_graph,
)

__all__ = [
    "CYCLE_LIMIT_CONFIG_KEY",
    "HASH_ALGORITHM",
    "CycleEdgePredicate",
    "EdgeFilter",
    "GraphIssueCodes",
    "InvalidSchemaError",
    "LoopRegion",
    "NodeValidator",
    "PortResolver",
    "PortsUnavailableError",
    "ScheduleView",
    "SchemaChecker",
    "SchemaViolation",
    "Topology",
    "canonical_graph",
    "check_instance",
    "compile_schema",
    "descriptor_cycle_edge",
    "effective_max_iterations",
    "graph_hash",
    "loop_regions",
    "node_ports",
    "non_flow_edges",
    "schedule_view",
    "topology",
    "validate_graph",
]
