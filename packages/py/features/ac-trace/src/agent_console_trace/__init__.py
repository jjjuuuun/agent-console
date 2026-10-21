"""agent-console-trace: 실행 이벤트 → 위임 흐름, 여러 실행의 위임·넘기기 집계(design §R4.2, §R3.1c).

span 사이 관계는 명시 id(`tool_use_id`·`node_path`·호출 `call`·`edge.traversed`·`interaction_id`·
`run.child_started.child_run_id`)로만 잇는다.
시간상 이웃을 인과로 잇지 않는다(agent_bench 원칙). `agent_console_contracts`에만 의존한다.
"""

from ._build import (
    SPAN_KIND_DELEGATED,
    SPAN_KIND_INTERACTION,
    SPAN_KIND_NODE,
    build_trace,
    call_span_id,
    child_span_id,
    delegated_span_id,
    interaction_span_id,
    node_span_id,
)
from ._matrix import handoff_matrix

__all__ = [
    "SPAN_KIND_DELEGATED",
    "SPAN_KIND_INTERACTION",
    "SPAN_KIND_NODE",
    "build_trace",
    "call_span_id",
    "child_span_id",
    "delegated_span_id",
    "handoff_matrix",
    "interaction_span_id",
    "node_span_id",
]
