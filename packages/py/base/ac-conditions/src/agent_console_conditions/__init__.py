"""agent-console-conditions: 선언형 조건 평가와 조건 연산자 확장 지점(X22, design §5R.3·§5R.5).

조건은 표현식 언어가 아니라 데이터다(계약 `ConditionSpec{all?, any?, negate?}` +
`ConditionItem{path, op, value?}`). 이 패키지는 조건을 판단 대상(JSON)에 적용하고 근거
(`ConditionOutcome`)를 만들며, 저장 전 검사 이슈를 낸다. 연산자 이름은 모른다 — 모든 연산자는
레지스트리(entry point `agent_console.condition_operators`)로 들어오고, 기본 10개(`builtin`)도 같은
길로 등록된다. 서버·엔진 없이 단독으로 쓸 수 있다.

공개 API:
    - 평가: ``evaluate_conditions(spec, subject, operators, *, redact, max_actual_chars)``,
      ``shorten_actual``, ``DEFAULT_MAX_ACTUAL_CHARS``, ``ConditionReasons``
    - 저장 전 검사: ``condition_issues(spec, operators, *, base_path, edge_id, node_id)``,
      ``ConditionIssueCodes``
    - 확장 지점: ``ConditionOperator``(프로토콜), ``ValueChecker``(선택 능력),
      ``OperatorConsumer``·``OperatorProvider``(연산자를 쓰는 확장이 앱 레지스트리를 받는 선택
      능력), ``RedactorConsumer``·``Redactor``(판정 근거를 자르기 전에 앱 가림 함수를 거는 선택
      능력),
      ``CONDITION_OPERATORS_GROUP``, ``as_condition_operator``, ``new_operator_registry``,
      ``load_condition_operators``, ``operator_map``, ``operator_descriptors``,
      ``default_operators``
    - 기본 연산자: ``builtin_operators()``(모듈 ``agent_console_conditions.builtin``)
    - JSON 도구: ``resolve_pointer``, ``MISSING``, ``json_equal``, ``json_type``
"""

from __future__ import annotations

from ._evaluate import (
    DEFAULT_MAX_ACTUAL_CHARS,
    ConditionIssueCodes,
    ConditionReasons,
    condition_issues,
    evaluate_conditions,
    shorten_actual,
)
from ._loading import (
    CONDITION_OPERATORS_EXTENSION,
    CONDITION_OPERATORS_GROUP,
    as_condition_operator,
    default_operators,
    load_condition_operators,
    new_operator_registry,
    operator_descriptors,
    operator_map,
)
from ._protocol import (
    ConditionOperator,
    OperatorConsumer,
    OperatorProvider,
    Redactor,
    RedactorConsumer,
    ValueChecker,
)
from ._values import MISSING, json_equal, json_type, resolve_pointer
from .builtin import builtin_operators

__all__ = [
    "CONDITION_OPERATORS_EXTENSION",
    "CONDITION_OPERATORS_GROUP",
    "DEFAULT_MAX_ACTUAL_CHARS",
    "MISSING",
    "ConditionIssueCodes",
    "ConditionOperator",
    "ConditionReasons",
    "OperatorConsumer",
    "OperatorProvider",
    "Redactor",
    "RedactorConsumer",
    "ValueChecker",
    "as_condition_operator",
    "builtin_operators",
    "condition_issues",
    "default_operators",
    "evaluate_conditions",
    "json_equal",
    "json_type",
    "load_condition_operators",
    "new_operator_registry",
    "operator_descriptors",
    "operator_map",
    "resolve_pointer",
    "shorten_actual",
]
