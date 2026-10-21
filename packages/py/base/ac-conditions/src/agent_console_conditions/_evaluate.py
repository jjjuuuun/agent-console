"""조건 평가(`evaluate_conditions`)와 저장 전 검사(`condition_issues`), design §5R.5."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Final

import jsonschema
import referencing

from agent_console_contracts import (
    ConditionItem,
    ConditionItemOutcome,
    ConditionMode,
    ConditionOutcome,
    ConditionSpec,
    Issue,
)

from ._protocol import ConditionOperator, ValueChecker
from ._values import MISSING, resolve_pointer

DEFAULT_MAX_ACTUAL_CHARS: Final = 200
"""판정 근거의 `actual`을 자를 길이(문자). 화면 명세는 길이 상한을 서버가 정한다고 둔다."""

_ELLIPSIS: Final = "…"


class ConditionIssueCodes:
    """이 패키지가 내는 이슈 코드(문서 상수, 열린 문자열).

    `UNKNOWN_OPERATOR`·`INVALID_VALUE`는 계약 `KnownIssueCodes`의 같은 이름 값과 같다.
    """

    UNKNOWN_OPERATOR: Final = "condition.unknown_operator"
    """등록되지 않은 연산자(warning, 실행 시 그 항목은 거짓). `details.op`."""
    INVALID_VALUE: Final = "condition.invalid_value"
    """값이 연산자 `value_schema`(또는 연산자 자체 검사)에 맞지 않음(error). `details.op`."""
    EMPTY: Final = "condition.empty"
    """조건 항목이 하나도 없음(warning, 항상 참)."""


class ConditionReasons:
    """판정 근거 항목의 `reason` 값(문서 상수, 계약 `ConditionItemOutcome.reason`의 알려진 값)."""

    MISSING: Final = "missing"
    UNKNOWN_OPERATOR: Final = "unknown_operator"
    INVALID_VALUE: Final = "invalid_value"
    ERROR: Final = "error"


def _groups(spec: ConditionSpec) -> list[tuple[ConditionMode, list[ConditionItem]]]:
    groups: list[tuple[ConditionMode, list[ConditionItem]]] = []
    if spec.all:
        groups.append(("all", list(spec.all)))
    if spec.any:
        groups.append(("any", list(spec.any)))
    return groups


def shorten_actual(value: Any, max_chars: int = DEFAULT_MAX_ACTUAL_CHARS) -> Any:
    """판정 근거용 실제 값: 문자열은 `max_chars`에서 자르고(…), 긴 목록·객체는 잘린 JSON 문자열.

    짧은 목록·객체·숫자·참거짓·null은 그대로 둔다. `MISSING`은 None.
    """
    if value is MISSING:
        return None
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + _ELLIPSIS
    if isinstance(value, Mapping | list | tuple):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
        if len(text) <= max_chars:
            return value
        return text[:max_chars] + _ELLIPSIS
    return value


def evaluate_conditions(
    spec: ConditionSpec,
    subject: Any,
    operators: Mapping[str, ConditionOperator],
    *,
    redact: Callable[[Any], Any] | None = None,
    max_actual_chars: int = DEFAULT_MAX_ACTUAL_CHARS,
) -> ConditionOutcome:
    """조건 묶음을 판단 대상에 적용해 결과와 근거를 돌려준다.

    - 각 항목: `path`(JSON Pointer)로 값을 꺼내 연산자 `op`로 `value`와 비교한다. 경로에 값이 없으면
      연산자는 `MISSING`을 받는다(`exists` 같은 존재 검사가 아니면 거짓, 근거 `reason = "missing"`).
    - 모르는 연산자는 거짓(`reason = "unknown_operator"`), 연산자 예외는 거짓(`reason = "error"`).
    - `all`은 모두 참, `any`는 하나라도 참, 둘 다 있으면 둘 다 만족해야 참. 둘 다 없거나 비면 참.
    - `negate`면 최종 결과를 뒤집는다. 근거를 위해 모든 항목을 평가한다(단락 평가 없음).

    Args:
        spec: 조건 데이터.
        subject: 판단 대상(JSON 호환 값, 보통 객체).
        operators: 연산자 id → 연산자.
        redact: 선택. 근거의 실제 값을 자르기 **전에** 거는 가림 함수(비밀 값 가리기).
        max_actual_chars: 근거 `actual`의 길이 상한.

    Returns:
        `ConditionOutcome`(계약). `combinator`는 한 목록만 있을 때 그 이름, 둘 다 있으면 null
        (항목의 `mode`로 구분).
    """
    groups = _groups(spec)
    both = len(groups) > 1
    items: list[ConditionItemOutcome] = []
    verdicts: list[bool] = []
    for mode, entries in groups:
        results = [
            _evaluate_item(
                item, subject, operators, redact, max_actual_chars, mode if both else None
            )
            for item in entries
        ]
        items.extend(results)
        flags = [r.result for r in results]
        verdicts.append(all(flags) if mode == "all" else any(flags))
    result = all(verdicts)
    negate = bool(spec.negate)
    return ConditionOutcome(
        result=not result if negate else result,
        combinator=None if len(groups) != 1 else groups[0][0],
        negate=True if negate else None,
        items=items,
    )


def _evaluate_item(
    item: ConditionItem,
    subject: Any,
    operators: Mapping[str, ConditionOperator],
    redact: Callable[[Any], Any] | None,
    max_chars: int,
    mode: ConditionMode | None,
) -> ConditionItemOutcome:
    actual = resolve_pointer(subject, item.path)
    shown = actual if redact is None or actual is MISSING else redact(actual)
    reason: str | None = None
    op = operators.get(item.op)
    if op is None:
        result, reason = False, ConditionReasons.UNKNOWN_OPERATOR
    else:
        try:
            result = bool(op.evaluate(actual, item.value))
        except Exception:
            result, reason = False, ConditionReasons.ERROR
        if not result and reason is None and actual is MISSING:
            reason = ConditionReasons.MISSING
    return ConditionItemOutcome(
        path=item.path,
        op=item.op,
        value=item.value,
        actual=shorten_actual(shown, max_chars),
        result=result,
        mode=mode,
        reason=reason,
    )


def _forbids_value(schema: Mapping[str, Any]) -> bool:
    return schema.get("not") == {} and len(schema) == 1


_OFFLINE: referencing.Registry[Any] = referencing.Registry()


def _schema_problems(schema: Mapping[str, Any], value: Any) -> list[str]:
    if _forbids_value(schema):
        return [] if value is None else ["이 연산자는 값을 받지 않습니다"]
    if not schema:
        return []
    cls = jsonschema.validators.validator_for(dict(schema))
    try:
        validator = cls(dict(schema), registry=_OFFLINE)
        return [str(e.message) for e in validator.iter_errors(value)]
    except Exception as exc:  # 잘못된 value_schema(플러그인 버그)도 저장을 막지 않고 알린다
        return [f"연산자 값 스키마를 해석할 수 없습니다: {exc}"]


def condition_issues(
    spec: ConditionSpec,
    operators: Mapping[str, ConditionOperator],
    *,
    base_path: str = "",
    edge_id: str | None = None,
    node_id: str | None = None,
) -> list[Issue]:
    """저장 전 검사. 모르는 연산자 = warning, 값 문제 = error, 항목 없음 = warning.

    Args:
        spec: 조건 데이터.
        operators: 연산자 id → 연산자(등록된 것).
        base_path: 이슈 `path` 앞에 붙일 JSON Pointer(예: 연결 config 안 `"/conditions"`).
        edge_id / node_id: 이슈 대상(선택).

    Returns:
        이슈 목록(`path` = `base_path` + `/all/<i>/op` 또는 `/value`). 값 검사는 연산자의
        `value_schema`(JSON Schema, `{"not": {}}` = 값 없음)와 선택 능력 `ValueChecker`.
    """
    issues: list[Issue] = []
    groups = _groups(spec)
    if not groups:
        issues.append(
            Issue(
                severity="warning",
                code=ConditionIssueCodes.EMPTY,
                message="조건이 비어 있어 항상 통과합니다",
                path=base_path,
                edge_id=edge_id,
                node_id=node_id,
            )
        )
    for mode, entries in groups:
        for index, item in enumerate(entries):
            where = f"{base_path}/{mode}/{index}"
            op = operators.get(item.op)
            if op is None:
                issues.append(
                    Issue(
                        severity="warning",
                        code=ConditionIssueCodes.UNKNOWN_OPERATOR,
                        message=(
                            f"조건 연산자 {item.op!r}이(가) 등록되어 있지 않습니다. "
                            "실행 때 이 항목은 거짓입니다"
                        ),
                        path=f"{where}/op",
                        details={"op": item.op},
                        edge_id=edge_id,
                        node_id=node_id,
                    )
                )
                continue
            problems = _schema_problems(op.descriptor.value_schema, item.value)
            if not problems and isinstance(op, ValueChecker):
                problems = list(op.check_value(item.value))
            if problems:
                issues.append(
                    Issue(
                        severity="error",
                        code=ConditionIssueCodes.INVALID_VALUE,
                        message=(
                            f"조건 {index + 1}의 값이 연산자 {op.descriptor.title!r}에 "
                            f"맞지 않습니다: {'; '.join(problems)}"
                        ),
                        path=f"{where}/value",
                        details={"op": item.op},
                        edge_id=edge_id,
                        node_id=node_id,
                    )
                )
    return issues
