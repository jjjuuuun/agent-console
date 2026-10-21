"""agent-console-example-condition: 예제 조건 연산자 플러그인(텍스트 단어 수 비교).

평가기·엔진에는 entry point(`agent_console.condition_operators`)로만 등록된다. 이 패키지는 공개 계약
(`agent_console_contracts`)만 사용한다.

공개 API:
    - 조건 연산자: ``WordCountAtLeast`` (id ``example.word_count_at_least``)
    - 도우미: ``word_count``, 상수: ``OPERATOR_ID``
"""

from agent_console_example_condition.word_count import OPERATOR_ID, WordCountAtLeast, word_count

__all__ = ["OPERATOR_ID", "WordCountAtLeast", "word_count"]
