"""agent-console-example-log-source: 예제 로그 출처(X5)·분류기(X6) 플러그인(텍스트 로그).

엔진·서버에는 entry point(`agent_console.log_sources`·`agent_console.log_classifiers`)로만
등록된다. 공개 계약(`agent_console_contracts`)과 로그 코어(`agent_console_logs`)의 공개 API만 쓴다.

공개 API:
    - 출처: ``TextLogSource``, 분류기: ``TextLogClassifier`` (id ``example.text_log``)
    - 순수 함수: ``parse_text_line``, 상수: ``FORMAT_ID``
"""

from agent_console_example_log_source.text_log import (
    FORMAT_ID,
    TextLogClassifier,
    TextLogSource,
    parse_text_line,
)

__all__ = ["FORMAT_ID", "TextLogClassifier", "TextLogSource", "parse_text_line"]
