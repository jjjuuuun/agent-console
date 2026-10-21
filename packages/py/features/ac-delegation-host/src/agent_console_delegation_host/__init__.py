"""agent-console-delegation-host: 독립 위임 방식 `host`(X12, design §5R.6).

위임자 모델에게 위임 도구(플랫폼 도구 `HostTool`) 하나를 주고, 모델이 부르면 대상 노드를 엔진의
`ctx.invoke_node`로 **자기 NodeRun·세션·백엔드·설정**에서 실행해 결과를 도구 결과로 돌려준다.
다른 composable 방식(예: `sdk-subagents`)과 한 위임자에서 합쳐 실행할 수 있다(`contribute`).

공개 API:
    - ``HostDelegation``: 위임 방식 구현(`descriptor`·`validate`·`contribute`·`run`, entry point
      ``agent_console.delegation_strategies``의 ``host``)
    - ``host_descriptor``: 디스크립터(규칙은 값: 깊이 = 설정만, 흐름 내보내기 금지, 모든 설정 필드,
      되묻기 제한 없음, 백엔드 능력 ``host_tools``, composable)
    - ``HostDelegationConfig``: 방식 config(도구 이름·파라미터 이름·문구 — 스키마 기본값이 데이터)
    - ``HostDelegationCodes``: 이슈·오류 코드, ``HOST``·``DEFAULT_RESULT_KEY``·``RESULT_MODES``
    - ``fill``: 문구 템플릿 안전 치환
"""

from __future__ import annotations

from agent_console_delegation_host._config import RESULT_MODES, HostDelegationConfig, fill
from agent_console_delegation_host._strategy import (
    DEFAULT_RESULT_KEY,
    HOST,
    HostDelegation,
    HostDelegationCodes,
    host_descriptor,
)

__all__ = [
    "DEFAULT_RESULT_KEY",
    "HOST",
    "RESULT_MODES",
    "HostDelegation",
    "HostDelegationCodes",
    "HostDelegationConfig",
    "fill",
    "host_descriptor",
]
