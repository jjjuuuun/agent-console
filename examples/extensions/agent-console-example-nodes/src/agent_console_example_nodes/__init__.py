"""agent-console-example-nodes: 예제 노드 타입 플러그인(텍스트 변환).

엔진에는 entry point(`agent_console.node_types`)로만 등록된다. 이 패키지는 공개 계약
(`agent_console_contracts`)과 실행 엔진 인터페이스(`agent_console_runtime`)만 사용한다.

공개 API:
    - 노드 타입: ``TextTransformNode`` (id ``example.text_transform``)
    - config 모델: ``TextTransformConfig``, 변환 함수 ``transform_text``
    - 상수: ``NODE_TYPE_ID``, ``IN_PORT``, ``OUT_PORT``, ``TEAM_ROLE``, ``ExampleErrorCodes``
"""

from agent_console_example_nodes.text_transform import (
    IN_PORT,
    NODE_TYPE_ID,
    OUT_PORT,
    TEAM_ROLE,
    ExampleErrorCodes,
    TextTransformConfig,
    TextTransformNode,
    transform_text,
)

__all__ = [
    "IN_PORT",
    "NODE_TYPE_ID",
    "OUT_PORT",
    "TEAM_ROLE",
    "ExampleErrorCodes",
    "TextTransformConfig",
    "TextTransformNode",
    "transform_text",
]
