"""테스트 도우미(공개): 공용 테스트 sink를 다시 내보낸다(`agent_console_runtime.testing_sink`).

- `ValidatingSink`: 계약으로 검증하며 기록한다. `node_path`(기본 `["n1"]`)는 이 sink가 흉내 내는
  노드 경로이고, `child_path`는 `NodeContext.child_path`와 같은 모양(`[*node_path, 대상]`)을 준다.
- `ListeningSink`: + 서브에이전트 결과 알림(`on_subagent_result`) 기록.
- `InteractiveSink`: + 상호작용(`request_input`) 기록·정해 둔 응답.
"""

from __future__ import annotations

from agent_console_runtime.testing_sink import InteractiveSink, ListeningSink, ValidatingSink

__all__ = ["InteractiveSink", "ListeningSink", "ValidatingSink"]
