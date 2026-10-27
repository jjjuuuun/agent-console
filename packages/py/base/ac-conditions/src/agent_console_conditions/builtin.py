"""기본 조건 연산자 10개(X22의 첫 플러그인, design §5R.3).

디스크립터(제목·설명·값 스키마·`applies_to`)는 데이터 파일 `data/builtin_operators.json`에 있고,
이 모듈은 같은 id의 비교 동작만 가진다. 등록은 다른 플러그인과 같은 길(entry point
`agent_console.condition_operators`)로 한다. 엔진·평가기는 이 id들을 모른다.

`matches`는 `ac-safe-regex`만 쓴다(입력 길이·시간 상한, 위험 패턴 거부). 다른 정규식 엔진을
쓰지 않는다.

모든 기본 연산자는 선택 능력 `CompilableOperator`(`compile_expected`)를 가진다. 기대 값의 형식을
한 번만 보고 그 형식에 맞는 좁은 비교 함수를 돌려준다(결과는 `evaluate`와 같다 — 차등 테스트).
"""

from __future__ import annotations

import json
import operator
from collections import OrderedDict
from collections.abc import Callable
from functools import cache
from importlib.resources import files
from typing import Any, Final

from agent_console_contracts import ConditionOperatorDescriptor
from agent_console_safe_regex import (
    SafePattern,
    UnsafeRegexError,
    check_user_regex,
    compile_user_regex,
)

from ._protocol import ActualPredicate
from ._values import MISSING, is_number, json_equal, json_type

_DATA_FILE: Final = "builtin_operators.json"


@cache
def builtin_descriptors() -> dict[str, ConditionOperatorDescriptor]:
    """데이터 파일의 기본 연산자 디스크립터(id → 디스크립터, 파일 순서)."""
    raw = json.loads(files(__package__).joinpath("data", _DATA_FILE).read_text(encoding="utf-8"))
    found = [ConditionOperatorDescriptor.model_validate(item) for item in raw["operators"]]
    return {d.id: d for d in found}


def _never(_actual: Any) -> bool:
    return False


class _Operator:
    """디스크립터(데이터) + 비교 함수(코드) 하나.

    Args:
        op_id: 디스크립터 id(데이터 파일).
        compare: `(실제 값, 기대 값) → 참·거짓`(실제 값은 `MISSING`이 아니다).
        fast: 선택. 기대 값 → 좁은 판정 함수(`MISSING`도 받는다) 또는 None(일반 경로).
    """

    def __init__(
        self,
        op_id: str,
        compare: Callable[[Any, Any], bool],
        fast: Callable[[Any], ActualPredicate | None] | None = None,
    ) -> None:
        self.descriptor = builtin_descriptors()[op_id]
        self._compare = compare
        self._fast = fast

    def evaluate(self, actual: Any, expected: Any) -> bool:
        """`actual`이 `MISSING`이면 거짓, 아니면 비교 함수."""
        if actual is MISSING:
            return False
        return self._compare(actual, expected)

    def compile_expected(self, expected: Any) -> ActualPredicate:
        """`expected`를 묶은 판정 함수(`CompilableOperator`). 결과는 `evaluate`와 같다."""
        if self._fast is not None:
            found = self._fast(expected)
            if found is not None:
                return found
        compare = self._compare
        return lambda actual: actual is not MISSING and compare(actual, expected)

    def __repr__(self) -> str:
        return f"<condition operator {self.descriptor.id}>"


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str):
        return isinstance(expected, str) and expected in actual
    if json_type(actual) == "array":
        return any(json_equal(item, expected) for item in actual)
    return False


def _in(actual: Any, expected: Any) -> bool:
    if json_type(expected) != "array":
        return False
    return any(json_equal(actual, item) for item in expected)


def _numeric(compare: Callable[[float, float], bool]) -> Callable[[Any, Any], bool]:
    def check(actual: Any, expected: Any) -> bool:
        return is_number(actual) and is_number(expected) and compare(actual, expected)

    return check


def _numeric_fast(
    compare: Callable[[float, float], bool],
) -> Callable[[Any], ActualPredicate]:
    def build(expected: Any) -> ActualPredicate:
        if not is_number(expected):
            return _never
        return lambda a: (
            isinstance(a, int | float) and not isinstance(a, bool) and compare(a, expected)
        )

    return build


def _eq_fast(expected: Any) -> ActualPredicate | None:
    """`json_equal(actual, expected)`를 기대 값의 형식별로 좁힌 것(`MISSING`은 거짓).

    목록·객체 같은 나머지 형식은 None(일반 경로).
    """
    if expected is None:
        return lambda a: a is None
    if isinstance(expected, bool):
        return lambda a: isinstance(a, bool) and a == expected
    if isinstance(expected, str):
        return lambda a: isinstance(a, str) and a == expected
    if is_number(expected):
        return lambda a: isinstance(a, int | float) and not isinstance(a, bool) and a == expected
    if type(expected) is list:
        size = len(expected)
        items = tuple(expected)

        def same_list(a: Any) -> bool:
            if type(a) is list:  # json_equal(목록, 목록)과 같다: 길이 + 항목별 json_equal
                return len(a) == size and all(
                    json_equal(x, y) for x, y in zip(a, items, strict=True)
                )
            return a is not MISSING and json_equal(a, expected)

        return same_list
    return None


def _ne_fast(expected: Any) -> ActualPredicate | None:
    same = _eq_fast(expected)
    if same is None:
        return None
    return lambda a: a is not MISSING and not same(a)


def _contains_fast(expected: Any) -> ActualPredicate | None:
    if not isinstance(expected, str):
        return None

    def check(actual: Any) -> bool:
        if isinstance(actual, str):
            return expected in actual
        if type(actual) is list:  # 문자열 기대 값은 문자열 항목하고만 같다(json_equal)
            return expected in actual and any(
                isinstance(item, str) and item == expected for item in actual
            )
        return actual is not MISSING and _contains(actual, expected)

    return check


def _in_fast(expected: Any) -> ActualPredicate:
    if json_type(expected) != "array":
        return _never
    texts = frozenset(item for item in expected if isinstance(item, str))
    others = tuple(item for item in expected if not isinstance(item, str))

    def check(actual: Any) -> bool:
        if isinstance(actual, str):  # 문자열은 문자열 항목하고만 같을 수 있다(json_equal)
            return actual in texts
        if actual is MISSING:
            return False
        return any(json_equal(actual, item) for item in others)

    return check


class ExistsOperator(_Operator):
    """`exists`: 경로에 값이 있으면 참(null 포함). 기대 값은 쓰지 않는다."""

    def __init__(self) -> None:
        super().__init__("exists", lambda _a, _e: True)

    def evaluate(self, actual: Any, expected: Any) -> bool:
        """`actual`이 `MISSING`이 아니면 참."""
        return actual is not MISSING

    def compile_expected(self, expected: Any) -> ActualPredicate:
        """기대 값과 상관없이 `actual is not MISSING`."""
        return lambda actual: actual is not MISSING


class MatchesOperator(_Operator):
    """`matches`: 텍스트가 사용자 정규식과 일치(`ac-safe-regex`, 컴파일 결과는 작은 LRU 캐시).

    Args:
        timeout: 매치 1회 시간 상한(초). 생략 = `ac-safe-regex` 기본값.
        max_input_chars: 검사할 입력 앞부분 길이. 생략 = `ac-safe-regex` 기본값.
        cache_size: 컴파일한 패턴을 기억할 개수.

    시간 상한을 넘으면 `RegexTimeoutError`가 그대로 올라가고 평가기가 그 항목을 거짓
    (`reason = "error"`)으로 기록한다. 위험한 패턴은 `UnsafeRegexError`(저장 전 검사가 먼저 알린다).
    """

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_input_chars: int | None = None,
        cache_size: int = 64,
    ) -> None:
        super().__init__("matches", self._match)
        self._options: dict[str, Any] = {}
        if timeout is not None:
            self._options["timeout"] = timeout
        if max_input_chars is not None:
            self._options["max_input_chars"] = max_input_chars
        self._cache: OrderedDict[str, SafePattern] = OrderedDict()
        self._cache_size = max(1, cache_size)

    def _pattern(self, source: str) -> SafePattern:
        found = self._cache.get(source)
        if found is None:
            found = compile_user_regex(source, **self._options)
            self._cache[source] = found
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(source)
        return found

    def _match(self, actual: Any, expected: Any) -> bool:
        if not isinstance(actual, str) or not isinstance(expected, str) or not expected:
            return False
        return self._pattern(expected).search(actual) is not None

    def compile_expected(self, expected: Any) -> ActualPredicate:
        """패턴을 한 번만 꺼내 묶는다. 위험한 패턴이면 `UnsafeRegexError`(평가기가 일반 경로로)."""
        if not isinstance(expected, str) or not expected:
            return _never
        pattern = self._pattern(expected)
        return lambda actual: isinstance(actual, str) and pattern.search(actual) is not None

    def check_value(self, expected: Any) -> list[str]:
        """위험하거나 문법이 틀린 정규식이면 사유 한 줄(`ValueChecker`)."""
        if not isinstance(expected, str):
            return []
        try:
            check_user_regex(expected)
        except UnsafeRegexError as exc:
            return [str(exc)]
        return []


EQ: Final = _Operator("eq", json_equal, _eq_fast)
"""`eq`: JSON 값이 같다."""
NE: Final = _Operator("ne", lambda a, e: not json_equal(a, e), _ne_fast)
"""`ne`: JSON 값이 다르다(경로에 값이 없으면 거짓)."""
IN: Final = _Operator("in", _in, _in_fast)
"""`in`: 목록 중 하나와 같다."""
CONTAINS: Final = _Operator("contains", _contains, _contains_fast)
"""`contains`: 텍스트 포함 또는 목록 항목 포함."""
MATCHES: Final = MatchesOperator()
"""`matches`: 안전한 정규식 일치."""
EXISTS: Final = ExistsOperator()
"""`exists`: 경로에 값이 있다."""
GT: Final = _Operator("gt", _numeric(operator.gt), _numeric_fast(operator.gt))
"""`gt`: 숫자 >."""
GTE: Final = _Operator("gte", _numeric(operator.ge), _numeric_fast(operator.ge))
"""`gte`: 숫자 >=."""
LT: Final = _Operator("lt", _numeric(operator.lt), _numeric_fast(operator.lt))
"""`lt`: 숫자 <."""
LTE: Final = _Operator("lte", _numeric(operator.le), _numeric_fast(operator.le))
"""`lte`: 숫자 <=."""


def builtin_operators() -> list[_Operator]:
    """기본 연산자 10개(entry point 없이 바로 쓰고 싶을 때). 순서 = 데이터 파일 순서."""
    by_id = {
        op.descriptor.id: op for op in (EQ, NE, IN, CONTAINS, MATCHES, EXISTS, GT, GTE, LT, LTE)
    }
    return [by_id[i] for i in builtin_descriptors() if i in by_id]
