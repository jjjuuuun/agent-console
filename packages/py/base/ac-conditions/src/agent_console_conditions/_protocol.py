"""조건 연산자 프로토콜(X22, design §5R.3)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import ConditionOperatorDescriptor


@runtime_checkable
class ConditionOperator(Protocol):
    """조건 연산자 하나(X22). 등록 key = `descriptor.id`.

    `evaluate`는 판정만 한다(부작용 없음). 형식이 맞지 않거나 경로에 값이 없으면(`MISSING`)
    예외 대신 거짓을 돌려준다. 예외를 던지면 평가기가 그 항목을 거짓(`reason = "error"`)으로 둔다.
    """

    descriptor: ConditionOperatorDescriptor

    def evaluate(self, actual: Any, expected: Any) -> bool:
        """`actual`(판단 대상에서 꺼낸 값 또는 `MISSING`)을 `expected`(조건 데이터)와 비교한다."""
        ...


@runtime_checkable
class ValueChecker(Protocol):
    """선택 능력: `value_schema`로 못 잡는 값 문제(예: 위험한 정규식)를 저장 전에 알린다."""

    def check_value(self, expected: Any) -> list[str]:
        """문제 문장 목록(없으면 빈 목록). 값은 이미 `value_schema`를 통과했다."""
        ...


type OperatorProvider = Callable[[], Mapping[str, ConditionOperator]]
"""지금 쓸 연산자(id → 연산자)를 돌려주는 함수. 부를 때마다 최신 등록 상태를 읽는다."""


@runtime_checkable
class OperatorConsumer(Protocol):
    """선택 능력: 조건 연산자를 쓰는 확장(예: 조건 연결 종류)이 앱의 연산자 레지스트리를 받는다.

    앱(예: 실행 모듈)은 플러그인을 다 읽은 뒤 등록된 확장 중 이 능력이 있는 것에
    `use_operators(lambda: operator_map(registry))`를 부른다. 그러면 설정 `plugins.enabled`로
    끈 연산자나 명시 플러그인이 더한 연산자가 평가·저장 전 검사에 똑같이 반영된다.
    앱이 부르지 않으면 확장은 자기 기본값(설치된 entry point 등)을 쓴다.
    """

    def use_operators(self, source: OperatorProvider) -> None:
        """이후 평가·검사에 `source()`가 돌려주는 연산자를 쓴다."""
        ...


type Redactor = Callable[[Any], Any]
"""가림 함수: 값(문자열·JSON 값)을 받아 비밀을 가린 사본을 돌려준다(예: `SecretResolver.redact`)."""


@runtime_checkable
class RedactorConsumer(Protocol):
    """선택 능력: 판정 근거를 만드는 확장(예: 조건 연결 종류)이 앱의 가림 함수를 받는다.

    근거의 실제 값은 길이 상한에서 잘린다. 잘린 뒤에는 비밀 일부만 남아 저장 단계의 가림이
    알아보지 못하므로, 앱(예: 실행 모듈)이 엔진 비밀 해석기를 만든 뒤 이 능력이 있는 확장에
    `use_redactor(secrets.redact)`를 불러 **자르기 전에** 가리게 한다(design §5.2R.7).
    앱이 부르지 않으면 확장은 생성자에서 받은 값(없으면 가리지 않음)을 쓴다.
    """

    def use_redactor(self, redact: Redactor | None) -> None:
        """이후 판정 근거의 실제 값에 `redact`를 자르기 전에 건다(None = 가리지 않음)."""
        ...
