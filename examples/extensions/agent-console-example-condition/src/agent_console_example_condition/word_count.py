"""조건 연산자 `example.word_count_at_least`: 텍스트의 단어 수가 기대 값 이상인가.

조건 연산자(X22)는 두 가지만 갖추면 된다.

1. ``descriptor`` — 편집기 조건 위젯·저장 전 검사가 이 값을 쓴다.
   - ``value_schema``: 조건 값의 JSON Schema(저장 전 검사 ``condition.invalid_value``의 근거).
   - ``applies_to``: 어떤 JSON 형식의 값에 쓰는 연산자인지(화면 안내용).
2. ``evaluate(actual, expected)`` — 판정만 한다(부작용 없음). 형식이 맞지 않거나 경로에 값이 없으면
   (평가기의 ``MISSING`` 표시) 예외 대신 거짓.

단어는 공백(줄바꿈 포함)으로 나눈 조각이다. 동작은 결정적이다(외부 호출·시간·환경에 의존하지
않는다).
"""

from __future__ import annotations

from typing import Any, Final

from agent_console_contracts import ConditionOperatorDescriptor, UiHints

OPERATOR_ID: Final = "example.word_count_at_least"
"""디스크립터 id. pyproject의 entry point 이름·조건 항목 `op` 값과 같다."""


def word_count(text: str) -> int:
    """공백으로 나눈 단어 수."""
    return len(text.split())


class WordCountAtLeast:
    """조건 연산자 `example.word_count_at_least`(X22 예제 구현)."""

    descriptor = ConditionOperatorDescriptor(
        id=OPERATOR_ID,
        title="단어 수 이상",
        description="텍스트를 공백으로 나눈 단어 수가 기대 값 이상이다(예제 확장).",
        value_schema={"type": "integer", "minimum": 0},
        applies_to=["string"],
        ui_hints=UiHints(icon="#"),
    )

    def evaluate(self, actual: Any, expected: Any) -> bool:
        """`actual`이 텍스트이고 기대 값이 0 이상 정수이면 단어 수 비교, 아니면 거짓."""
        if not isinstance(actual, str):
            return False  # 경로에 값이 없을 때(MISSING)도 여기서 거짓
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
            return False
        return word_count(actual) >= expected
