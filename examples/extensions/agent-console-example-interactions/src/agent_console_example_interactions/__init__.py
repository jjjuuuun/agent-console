"""agent-console-example-interactions: 예제 상호작용 종류(서명 받기)와 그 종류를 허용하는 연결.

엔진에는 entry point(`agent_console.interaction_kinds`, `agent_console.edge_types`)로만 등록된다.
공개 계약(`agent_console_contracts`)과 실행 엔진 인터페이스(`agent_console_runtime`)만 사용한다.

공개 API:
    - 상호작용 종류 디스크립터: ``SIGN_OFF`` (id ``example.sign_off``)
    - 연결 종류: ``AskSignOffEdge`` (id ``example.ask_sign_off``)
    - 상수: ``INTERACTION_KIND_ID``, ``EDGE_TYPE_ID``, ``RENDERER``
"""

from agent_console_example_interactions.sign_off import (
    EDGE_TYPE_ID,
    INTERACTION_KIND_ID,
    RENDERER,
    SIGN_OFF,
    AskSignOffEdge,
)

__all__ = ["EDGE_TYPE_ID", "INTERACTION_KIND_ID", "RENDERER", "SIGN_OFF", "AskSignOffEdge"]
