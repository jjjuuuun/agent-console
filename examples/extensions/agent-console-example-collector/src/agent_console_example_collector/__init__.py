"""agent-console-example-collector: 예제 관측 수집기(X7) 플러그인(도구 호출 수).

claude-sdk 백엔드에는 entry point(`agent_console.collectors`)로만 등록된다. 공개 API
(`agent_console_backend_claude_sdk.collectors`)와 SDK 메시지 타입만 쓴다.

공개 API:
    - 수집기: ``ToolCountCollector`` (id ``example.tool_count``), 설정 모델 ``ToolCountConfig``
    - 순수 함수: ``count_tool_uses``, ``merge_counts``
    - 상수: ``COLLECTOR_ID``, ``EVENT_TYPE``, ``DEFAULT_BACKEND``
"""

from agent_console_example_collector.tool_count import (
    COLLECTOR_ID,
    DEFAULT_BACKEND,
    EVENT_TYPE,
    ToolCountCollector,
    ToolCountConfig,
    count_tool_uses,
    merge_counts,
)

__all__ = [
    "COLLECTOR_ID",
    "DEFAULT_BACKEND",
    "EVENT_TYPE",
    "ToolCountCollector",
    "ToolCountConfig",
    "count_tool_uses",
    "merge_counts",
]
