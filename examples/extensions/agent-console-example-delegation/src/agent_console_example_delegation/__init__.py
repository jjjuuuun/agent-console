"""agent-console-example-delegation: 예제 위임 방식 플러그인(대상을 차례로 불러 결과 이어 붙이기).

엔진에는 entry point(`agent_console.delegation_strategies`)로만 등록된다. 이 패키지는 공개 계약
(`agent_console_contracts`)과 실행 엔진 인터페이스(`agent_console_runtime`)만 사용한다.

공개 API:
    - 위임 방식: ``RoundRobinDelegation`` (id ``example.round_robin``)
    - config 모델: ``RoundRobinConfig``, 코드: ``RoundRobinCodes``, 상수: ``STRATEGY_ID``
    - 안전 치환: ``fill``
"""

from agent_console_example_delegation.round_robin import (
    STRATEGY_ID,
    RoundRobinCodes,
    RoundRobinConfig,
    RoundRobinDelegation,
    fill,
)

__all__ = ["STRATEGY_ID", "RoundRobinCodes", "RoundRobinConfig", "RoundRobinDelegation", "fill"]
