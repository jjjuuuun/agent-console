"""agent-console-example-edges: 예제 연결 종류 플러그인(접두어 붙여 넘기기).

엔진에는 entry point(`agent_console.edge_types`)로만 등록된다. 이 패키지는 공개 계약
(`agent_console_contracts`)과 실행 엔진 인터페이스(`agent_console_runtime`)만 사용한다.

공개 API:
    - 연결 종류: ``RelayEdge`` (id ``example.relay``)
    - config 모델: ``RelayConfig``, 상수: ``EDGE_TYPE_ID``, ``AGENT_ROLE``
"""

from agent_console_example_edges.relay import AGENT_ROLE, EDGE_TYPE_ID, RelayConfig, RelayEdge

__all__ = ["AGENT_ROLE", "EDGE_TYPE_ID", "RelayConfig", "RelayEdge"]
