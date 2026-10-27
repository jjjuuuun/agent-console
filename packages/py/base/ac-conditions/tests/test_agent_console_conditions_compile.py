"""빠른 판정(compile_conditions·conditions_hold·compile_pointer)과 근거 API의 차등 테스트(5.5R.35).

근거 API(`evaluate_conditions`)는 바꾸지 않았다. 빠른 경로가 같은 연산자로 같은 결과(참·거짓)를
내는지 무작위 조건·대상으로 비교한다. 연산자 플러그인(X22)은 빠른 판정 능력이 없거나(None·예외)
있어도 같은 결과여야 한다.
"""

from __future__ import annotations

import math
import random
from typing import Any

import pytest

from agent_console_conditions import (
    MISSING,
    CompilableOperator,
    ConditionOperator,
    builtin_operators,
    compile_condition_item,
    compile_conditions,
    compile_pointer,
    conditions_hold,
    evaluate_conditions,
    resolve_pointer,
)
from agent_console_contracts import ConditionItem, ConditionOperatorDescriptor, ConditionSpec

BUILTIN = {op.descriptor.id: op for op in builtin_operators()}


def _descriptor(op_id: str) -> ConditionOperatorDescriptor:
    return ConditionOperatorDescriptor(id=op_id, title=op_id)


class LongerThan:
    """플러그인: 빠른 판정 능력 없음(evaluate만)."""

    descriptor = _descriptor("longer_than")

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, actual: Any, expected: Any) -> bool:
        self.calls += 1
        if not isinstance(actual, str | list) or not isinstance(expected, int):
            return False
        return len(actual) > expected


class DeclinesFast(LongerThan):
    """플러그인: 능력은 있으나 빠른 판정을 못 만든다(None)."""

    descriptor = _descriptor("declines_fast")

    def compile_expected(self, expected: Any) -> None:
        return None


class FastFails(LongerThan):
    """플러그인: 빠른 판정을 만들다 예외 → 기존 경로."""

    descriptor = _descriptor("fast_fails")

    def compile_expected(self, expected: Any) -> Any:
        raise RuntimeError("cannot compile")


class AlwaysRaises:
    """플러그인: 판정이 늘 예외(= 거짓)."""

    descriptor = _descriptor("always_raises")

    def evaluate(self, actual: Any, expected: Any) -> bool:
        raise ValueError("boom")


class FastStartsWith:
    """플러그인: 빠른 판정 능력이 있다. 기대 값이 문자열이 아니면 빠른 판정이 예외를 낸다."""

    descriptor = _descriptor("starts_with")

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, actual: Any, expected: Any) -> bool:
        self.calls += 1
        if not isinstance(expected, str):
            raise TypeError("expected must be text")
        return isinstance(actual, str) and actual.startswith(expected)

    def compile_expected(self, expected: Any) -> Any:
        def check(actual: Any) -> bool:
            if not isinstance(expected, str):
                raise TypeError("expected must be text")
            return isinstance(actual, str) and actual.startswith(expected)

        return check


def _operators() -> dict[str, ConditionOperator]:
    ops: dict[str, ConditionOperator] = dict(BUILTIN)
    for plugin in (LongerThan(), DeclinesFast(), FastFails(), AlwaysRaises(), FastStartsWith()):
        ops[plugin.descriptor.id] = plugin
    return ops


SCALARS: list[Any] = [
    None,
    True,
    False,
    0,
    1,
    1.0,
    2,
    -3.5,
    10**20,
    math.inf,
    "",
    "a",
    "ab",
    "PASS",
    "abc PASS",
    "1",
    "true",
    "é",
]
PATTERNS: list[Any] = ["^a", "b+", "PASS$", "", "[", "(a+)+$", "(?i)pass"]
PATHS = [
    "",
    "/a",
    "/b",
    "/s",
    "/n",
    "/a/b",
    "/a/0",
    "/list/0",
    "/list/1",
    "/list/01",
    "/list/-",
    "/x~1y",
    "/m~0n",
    "/obj/k",
    "/obj/k/0",
    "/missing",
    "/²",
]
KEYS = ["a", "b", "s", "n", "list", "x/y", "m~n", "obj", "k", "0", "²"]


def _value(rng: random.Random, depth: int = 0) -> Any:
    roll = rng.random()
    if depth >= 2 or roll < 0.6:
        return rng.choice(SCALARS)
    if roll < 0.8:
        return [_value(rng, depth + 1) for _ in range(rng.randint(0, 3))]
    return {rng.choice(KEYS): _value(rng, depth + 1) for _ in range(rng.randint(0, 3))}


def _subject(rng: random.Random) -> Any:
    if rng.random() < 0.05:
        return _value(rng)  # 객체가 아닌 판단 대상
    return {key: _value(rng) for key in KEYS if rng.random() < 0.6}


def _expected(rng: random.Random, op: str) -> Any:
    if op == "matches":
        return rng.choice([*PATTERNS, None, 3])
    if op == "in":
        return rng.choice([[_value(rng) for _ in range(rng.randint(0, 4))], "a", None])
    if op in ("longer_than", "declines_fast", "fast_fails"):
        return rng.choice([0, 1, 2, "x"])
    if op == "starts_with":
        return rng.choice(["a", "", "PA", 1])
    return _value(rng)


def _item(rng: random.Random, ops: list[str]) -> ConditionItem:
    op = rng.choice(ops)
    return ConditionItem(path=rng.choice(PATHS), op=op, value=_expected(rng, op))


def _spec(rng: random.Random, ops: list[str]) -> ConditionSpec:
    def group() -> list[ConditionItem] | None:
        roll = rng.random()
        if roll < 0.3:
            return None
        if roll < 0.4:
            return []
        return [_item(rng, ops) for _ in range(rng.randint(1, 4))]

    return ConditionSpec(all=group(), any=group(), negate=rng.choice([None, False, True]))


OP_NAMES = [*BUILTIN, "longer_than", "declines_fast", "fast_fails", "always_raises", "starts_with"]


@pytest.mark.parametrize("seed", range(8))
def test_fast_path_matches_evidence_api(seed: int) -> None:
    rng = random.Random(seed)
    ops = _operators()
    names = [*OP_NAMES, "unknown_op"]
    for _ in range(400):
        spec = _spec(rng, names)
        compiled = compile_conditions(spec, ops)
        for _ in range(6):
            subject = _subject(rng)
            expected = evaluate_conditions(spec, subject, ops).result
            assert compiled(subject) is expected, (spec, subject)
            assert conditions_hold(spec, subject, ops) is expected


@pytest.mark.parametrize("seed", range(4))
def test_each_item_matches_evidence_item(seed: int) -> None:
    rng = random.Random(1000 + seed)
    ops = _operators()
    for _ in range(1500):
        item = _item(rng, [*OP_NAMES, "unknown_op"])
        check = compile_condition_item(item, ops)
        subject = _subject(rng)
        outcome = evaluate_conditions(ConditionSpec(all=[item]), subject, ops)
        assert outcome.items is not None
        assert check(subject) is outcome.items[0].result, (item, subject)


@pytest.mark.parametrize("seed", range(4))
def test_builtin_compiled_expected_matches_evaluate(seed: int) -> None:
    rng = random.Random(2000 + seed)
    for _ in range(3000):
        op_id = rng.choice(list(BUILTIN))
        op = BUILTIN[op_id]
        assert isinstance(op, CompilableOperator)
        expected = _expected(rng, op_id)
        actual = rng.choice([MISSING, _value(rng)])
        try:
            want: bool | str = op.evaluate(actual, expected)
        except Exception:
            want = "error"
        try:
            fast = op.compile_expected(expected)
        except Exception:
            continue  # 만들지 못하면 평가기가 evaluate 경로로 판정한다(위 차등 테스트)
        try:
            got: bool | str = bool(fast(actual))
        except Exception:
            got = "error"
        assert got == want, (op_id, actual, expected)


def test_compile_pointer_matches_resolve_pointer() -> None:
    rng = random.Random(7)
    pointers = [*PATHS, "a", "list/0", "/list/1/", "//", "/obj/k/a~1b"]
    for _ in range(3000):
        document = _subject(rng)
        pointer = rng.choice(pointers)
        got, want = compile_pointer(pointer)(document), resolve_pointer(document, pointer)
        assert got is want or got == want, (pointer, document)


def test_superscript_index_is_missing_not_error() -> None:
    # "²".isdigit()는 참이지만 int()가 실패한다 — 목록 위치가 아니므로 MISSING(전에는 예외였다).
    assert resolve_pointer({"list": [1, 2, 3]}, "/list/²") is MISSING
    assert resolve_pointer({"²": 5}, "/²") == 5


def test_plugin_without_fast_path_uses_evaluate() -> None:
    plain, declines, fails = LongerThan(), DeclinesFast(), FastFails()
    ops: dict[str, ConditionOperator] = {"a": plain, "b": declines, "c": fails}
    for name, plugin in (("a", plain), ("b", declines), ("c", fails)):
        compiled = compile_conditions(
            ConditionSpec(all=[ConditionItem(path="/s", op=name, value=2)]), ops
        )
        assert compiled({"s": "abc"}) is True
        assert compiled({"s": "ab"}) is False
        assert plugin.calls == 2


def test_plugin_fast_path_skips_evaluate_and_error_is_false() -> None:
    plugin = FastStartsWith()
    ops: dict[str, ConditionOperator] = {"starts_with": plugin}
    ok = compile_conditions(
        ConditionSpec(all=[ConditionItem(path="/s", op="starts_with", value="ab")]), ops
    )
    assert ok({"s": "abc"}) is True
    assert ok({"s": "xbc"}) is False
    assert plugin.calls == 0
    bad = compile_conditions(
        ConditionSpec(any=[ConditionItem(path="/s", op="starts_with", value=1)]), ops
    )
    assert bad({"s": "abc"}) is False


def test_short_circuit_and_operator_snapshot() -> None:
    plugin = LongerThan()
    ops: dict[str, ConditionOperator] = {"eq": BUILTIN["eq"], "longer_than": plugin}
    spec = ConditionSpec(
        all=[
            ConditionItem(path="/a", op="eq", value=1),
            ConditionItem(path="/s", op="longer_than", value=0),
        ]
    )
    compiled = compile_conditions(spec, ops)
    assert compiled({"a": 2, "s": "x"}) is False
    assert plugin.calls == 0  # all의 첫 거짓에서 멈춘다(근거가 필요 없음)
    ops.pop("longer_than")  # 컴파일할 때 찾은 연산자를 쓴다
    assert compiled({"a": 1, "s": "x"}) is True
    # 다시 컴파일하면 모르는 연산자(거짓)
    assert compile_conditions(spec, ops)({"a": 1, "s": "x"}) is False


def test_empty_and_negate() -> None:
    assert compile_conditions(ConditionSpec(), {})(None) is True
    assert compile_conditions(ConditionSpec(all=[], any=[], negate=True), {})({}) is False
