"""조건 미리 컴파일과 참·거짓만 내는 빠른 판정(design §5.5R.10 `[5.5R.35]`).

`evaluate_conditions`는 화면에 보일 근거(`ConditionOutcome`)를 만들려고 모든 항목을 평가하고
항목마다 계약 모델을 만든다. 같은 조건으로 많은 대상을 판정하면서 결과(참·거짓)만 필요할 때
(예: 구조도가 이벤트 수만 개를 칸·연결에 나눌 때)는 이 모듈을 쓴다.

- 경로 해석(`compile_pointer`)과 연산자 찾기는 컴파일할 때 한 번만 한다.
- 연산자가 선택 능력 `CompilableOperator`를 가지면 기대 값을 묶은 판정 함수를 쓰고, 없거나 None을
  돌려주거나 만들다 예외가 나면 `evaluate(actual, expected)`를 부르는 기존 경로로 판정한다.
- 결과는 같은 연산자로 부른 `evaluate_conditions(...).result`와 같다(차등 테스트). 근거를 만들지
  않으므로 `all`은 처음 거짓에서, `any`는 처음 참에서 멈춘다(연산자는 부작용이 없다 — 프로토콜
  계약).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent_console_contracts import ConditionItem, ConditionSpec

from ._protocol import ActualPredicate, CompilableOperator, ConditionOperator
from ._values import MISSING, _parse_pointer, compile_pointer

type SubjectPredicate = Callable[[Any], bool]
"""판단 대상 → 참·거짓."""


def _never(_subject: Any) -> bool:
    return False


def _always(_subject: Any) -> bool:
    return True


def _fast_predicate(op: ConditionOperator, expected: Any) -> ActualPredicate | None:
    if not isinstance(op, CompilableOperator):
        return None
    try:
        return op.compile_expected(expected)
    except Exception:  # 빠른 판정을 못 만들면 기존 경로(evaluate)로 — 결과는 같다
        return None


def _item_predicate(item: ConditionItem, op: ConditionOperator) -> SubjectPredicate:
    get = compile_pointer(item.path)
    test = _fast_predicate(op, item.value)
    if test is None:
        evaluate = op.evaluate
        expected = item.value

        def slow(subject: Any) -> bool:
            actual = get(subject)
            try:
                return bool(evaluate(actual, expected))
            except Exception:
                return False

        return slow

    fast = test
    tokens = _parse_pointer(item.path)
    if tokens is not None and len(tokens) == 1:
        key = tokens[0][0]

        def top(subject: Any) -> bool:  # 흔한 경우(최상위 키 하나)는 경로 함수를 부르지 않는다
            actual = subject.get(key, MISSING) if type(subject) is dict else get(subject)
            try:
                return bool(fast(actual))
            except Exception:
                return False

        return top

    def check(subject: Any) -> bool:
        actual = get(subject)
        try:
            return bool(fast(actual))
        except Exception:
            return False

    return check


def compile_condition_item(
    item: ConditionItem, operators: Mapping[str, ConditionOperator]
) -> SubjectPredicate:
    """조건 항목 하나 → `판단 대상 → 참·거짓` 함수.

    모르는 연산자는 늘 거짓, 연산자 예외는 그 판정만 거짓이다(`evaluate_conditions`와 같다).

    Args:
        item: 조건 항목(`path`·`op`·`value`).
        operators: 연산자 id → 연산자. 컴파일할 때 한 번 찾는다(뒤에 등록이 바뀌면 다시
            컴파일한다).
    """
    op = operators.get(item.op)
    return _never if op is None else _item_predicate(item, op)


def _combine(
    all_items: tuple[SubjectPredicate, ...] | None,
    any_items: tuple[SubjectPredicate, ...] | None,
    negate: bool,
) -> SubjectPredicate:
    """묶음 규칙(all·any·negate)을 함수 하나로. 흔한 모양은 감싸는 단계를 줄인다."""
    if all_items is None and any_items is None:
        return _never if negate else _always
    if not negate:
        if any_items is None and all_items is not None:
            if len(all_items) == 1:
                return all_items[0]
            if len(all_items) == 2:
                first, second = all_items
                return lambda subject: first(subject) and second(subject)
        if all_items is None and any_items is not None and len(any_items) == 1:
            return any_items[0]

    def holds(subject: Any) -> bool:
        result = True
        if all_items is not None:
            for check in all_items:
                if not check(subject):
                    result = False
                    break
        if result and any_items is not None:
            for check in any_items:
                if check(subject):
                    break
            else:
                result = False
        return not result if negate else result

    return holds


class CompiledConditions:
    """미리 컴파일한 조건 묶음. 부르면 참·거짓만 돌려준다(근거 없음).

    `compile_conditions`로 만든다. 상태가 없어 여러 스레드에서 함께 불러도 된다(연산자가 그렇다면).

    Attributes:
        predicate: `판단 대상 → 참·거짓` 함수 자체(많이 부를 때 메서드 호출 한 단계를 줄인다).
    """

    __slots__ = ("predicate",)

    def __init__(self, predicate: SubjectPredicate) -> None:
        self.predicate = predicate

    def __call__(self, subject: Any) -> bool:
        """`subject`가 조건을 만족하면 참(`evaluate_conditions(...).result`와 같다)."""
        return self.predicate(subject)

    holds = __call__


def compile_conditions(
    spec: ConditionSpec, operators: Mapping[str, ConditionOperator]
) -> CompiledConditions:
    """조건 묶음을 미리 컴파일한다(경로 해석·연산자 찾기·기대 값 묶기를 한 번만).

    Args:
        spec: 조건 데이터(`all`·`any`·`negate`, 규칙은 `evaluate_conditions`와 같다).
        operators: 연산자 id → 연산자. 컴파일할 때 한 번 찾는다.

    Returns:
        `CompiledConditions` — `compiled(subject) -> bool`.
    """

    def compile_group(items: list[ConditionItem] | None) -> tuple[SubjectPredicate, ...] | None:
        if not items:
            return None
        return tuple(compile_condition_item(item, operators) for item in items)

    return CompiledConditions(
        _combine(compile_group(spec.all), compile_group(spec.any), bool(spec.negate))
    )


def necessary_items(
    spec: ConditionSpec, operators: Mapping[str, ConditionOperator]
) -> tuple[tuple[str, SubjectPredicate], ...]:
    """조건 묶음이 참이려면 반드시 참이어야 하는 "최상위 키 하나" 항목들: (키, 항목 판정).

    `all`의 항목 전부와 `any`의 항목이 하나뿐이면 그 항목이 해당한다(`negate`면 없음). 경로가
    `/키` 하나인 항목만 낸다. 항목 판정의 결과는 판단 대상(JSON 객체)의 그 키 값에만 달렸다(같은
    값이면 같은 결과 — 연산자는 부작용이 없다는 프로토콜 계약). 많은 대상을 판정하는 쪽이 키 값별로
    결과를 기억해 맞을 수 없는 조건 묶음을 미리 걸러 낼 때 쓴다.

    Args:
        spec: 조건 데이터.
        operators: 연산자 id → 연산자(`compile_condition_item`과 같다).

    Returns:
        (최상위 키, 항목 판정 `판단 대상 → 참·거짓`)들. 없으면 빈 튜플.
    """
    if spec.negate:
        return ()
    items = list(spec.all or [])
    if spec.any and len(spec.any) == 1:
        items.append(spec.any[0])
    out: list[tuple[str, SubjectPredicate]] = []
    for item in items:
        tokens = _parse_pointer(item.path)
        if tokens is None or len(tokens) != 1:
            continue
        out.append((tokens[0][0], compile_condition_item(item, operators)))
    return tuple(out)


def condition_keys(spec: ConditionSpec) -> frozenset[str] | None:
    """조건 묶음이 읽는 판단 대상의 최상위 키들(경로 `/a/b`는 `a`를 읽는다).

    판정 결과는 판단 대상(JSON 객체)의 이 키들 값에만 달렸다(같은 값이면 같은 결과 — 연산자는
    부작용이 없다는 프로토콜 계약). `/`로 시작하지 않는 경로는 아무것도 읽지 않는다(늘 `MISSING`).

    Returns:
        키 집합. 문서 전체(`""`)를 읽는 항목이 있으면 None(모든 키에 달렸다).
    """
    keys: set[str] = set()
    for item in (*(spec.all or ()), *(spec.any or ())):
        tokens = _parse_pointer(item.path)
        if tokens is None:
            continue
        if not tokens:
            return None
        keys.add(tokens[0][0])
    return frozenset(keys)


def conditions_hold(
    spec: ConditionSpec, subject: Any, operators: Mapping[str, ConditionOperator]
) -> bool:
    """한 번만 판정할 때: 근거 없이 참·거짓만(`compile_conditions(spec, operators)(subject)`).

    같은 조건을 여러 번 쓰면 `compile_conditions` 결과를 기억해 두고 부른다.
    """
    return compile_conditions(spec, operators)(subject)
