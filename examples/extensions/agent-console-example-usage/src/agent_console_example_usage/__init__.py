"""agent-console-example-usage: 예제 사용량 출처 플러그인(직접 적는 사용량).

엔진·서버에는 entry point(`agent_console.usage_sources`)로만 등록된다. 공개 계약
(`agent_console_contracts`)과 사용량 출처 인터페이스(`agent_console_usage`)만 사용한다.

공개 API:
    - 출처: ``ManualCountSource`` (id ``example.manual_count``)
    - 순수 함수: ``windows_from_config``, 상수: ``SOURCE_ID``, ``TRUST``
"""

from agent_console_example_usage.manual_count import (
    SOURCE_ID,
    TRUST,
    ManualCountSource,
    windows_from_config,
)

__all__ = ["SOURCE_ID", "TRUST", "ManualCountSource", "windows_from_config"]
