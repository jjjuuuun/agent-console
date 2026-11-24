"""기본 연산자 11개: 참·거짓·경계·형식 불일치(= 거짓)·값 없음(MISSING)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_conditions import MISSING, builtin_operators
from agent_console_conditions.builtin import MATCHES, MatchesOperator, builtin_descriptors
from agent_console_safe_regex import UnsafeRegexError

OPS = {op.descriptor.id: op for op in builtin_operators()}


def test_builtin_operators_from_data() -> None:
    assert list(OPS) == [
        "eq",
        "ne",
        "in",
        "contains",
        "matches",
        "exists",
        "gt",
        "gte",
        "lt",
        "lte",
        "any_item",
    ]
    assert list(builtin_descriptors()) == list(OPS)
    assert all(op.descriptor.title for op in OPS.values())


CASES: list[tuple[str, Any, Any, bool]] = [
    # eq / ne: JSON 같음(숫자는 값으로, 참거짓은 숫자와 다름)
    ("eq", "PASS", "PASS", True),
    ("eq", "PASS", "pass", False),
    ("eq", 1, 1.0, True),
    ("eq", True, 1, False),
    ("eq", 1, "1", False),
    ("eq", None, None, True),
    ("eq", {"a": [1, 2]}, {"a": [1, 2.0]}, True),
    ("eq", [1, 2], [2, 1], False),
    ("ne", "a", "b", True),
    ("ne", "a", "a", False),
    ("ne", 1, "1", True),
    # in
    ("in", "ok", ["ok", "pass"], True),
    ("in", "fail", ["ok", "pass"], False),
    ("in", 2, [1.0, 2.0], True),
    ("in", "ok", "ok", False),  # 기대 값이 목록이 아니면 거짓
    ("in", True, [1], False),
    # contains
    ("contains", "all tests PASS (12)", "PASS", True),
    ("contains", "all tests pass", "PASS", False),
    ("contains", ["a", "b"], "b", True),
    ("contains", ["a", "b"], "c", False),
    ("contains", 123, "1", False),  # 형식 불일치
    ("contains", "abc", 1, False),
    ("contains", {"PASS": 1}, "PASS", False),
    # matches
    ("matches", "build #42 ok", r"#\d+ ok$", True),
    ("matches", "build ok", r"#\d+", False),
    ("matches", 42, r"\d+", False),
    # exists(값 무시)
    ("exists", None, None, True),
    ("exists", "", None, True),
    # 숫자 비교: 경계
    ("gt", 3, 2, True),
    ("gt", 2, 2, False),
    ("gte", 2, 2, True),
    ("gte", 1.9, 2, False),
    ("lt", 1, 2, True),
    ("lt", 2, 2, False),
    ("lte", 2, 2.0, True),
    ("lte", 2.1, 2, False),
    # 숫자 비교: 형식 불일치
    ("gt", "3", 2, False),
    ("gt", 3, "2", False),
    ("gte", True, 0, False),
    ("lt", None, 1, False),
    ("lte", [1], 2, False),
]


@pytest.mark.parametrize(("op", "actual", "expected", "want"), CASES)
def test_operator_cases(op: str, actual: Any, expected: Any, want: bool) -> None:
    assert OPS[op].evaluate(actual, expected) is want


@pytest.mark.parametrize("op", sorted(OPS))
def test_missing_is_false_except_nothing(op: str) -> None:
    # 경로에 값이 없으면 모두 거짓(exists도 '없음'이므로 거짓)
    assert OPS[op].evaluate(MISSING, "x") is False


def test_matches_rejects_unsafe_pattern_at_runtime_and_check() -> None:
    with pytest.raises(UnsafeRegexError):
        MATCHES.evaluate("aaaa", "(a+)+")
    assert MATCHES.check_value("(a+)+")
    assert MATCHES.check_value("[") != []
    assert MATCHES.check_value(r"\d+") == []


def test_matches_input_limit_and_cache() -> None:
    op = MatchesOperator(max_input_chars=5, cache_size=1)
    assert op.evaluate("abcdeX", "X") is False  # 입력 앞 5자만 본다
    assert op.evaluate("abX", "X") is True
    assert op.evaluate("abY", "Y") is True  # 캐시 크기 1에서 교체
    assert op.evaluate("abX", "X") is True


ITEMS = [{"kind": "rules", "path": "a"}, {"kind": "skill", "path": "b", "tags": ["x"]}]


@pytest.mark.parametrize(
    ("actual", "expected", "want"),
    [
        (ITEMS, {"/kind": ["skill", "spec"]}, True),
        (ITEMS, {"/kind": ["spec"]}, False),
        (ITEMS, {"/kind": ["rules"], "/path": ["a"]}, True),
        (ITEMS, {"/kind": ["rules"], "/path": ["b"]}, False),  # 한 항목에서 모두 맞아야 한다
        (ITEMS, {"/tags": [["x"]]}, True),
        (ITEMS, {"/missing": [None]}, False),
        (["a", "b"], {"": ["b"]}, True),
        ([1, 2], {"": [2.0]}, True),
        ([], {"/kind": ["skill"]}, False),
        ("skill", {"": ["skill"]}, False),  # 목록이 아니면 거짓
        ({"kind": "skill"}, {"/kind": ["skill"]}, False),
        (ITEMS, {}, False),  # 형식이 틀린 기대 값은 거짓
        (ITEMS, {"/kind": "skill"}, False),
        (ITEMS, {"kind": ["skill"]}, False),
        (ITEMS, ["skill"], False),
    ],
)
def test_any_item(actual: Any, expected: Any, want: bool) -> None:
    op = OPS["any_item"]
    assert op.evaluate(actual, expected) is want
    assert op.compile_expected(expected)(actual) is want


def test_any_item_value_schema_rejects_bad_values() -> None:
    from agent_console_conditions import condition_issues
    from agent_console_contracts import ConditionSpec

    spec = ConditionSpec.model_validate(
        {
            "all": [
                {"path": "/documents", "op": "any_item", "value": {"/kind": ["skill"]}},
                {"path": "/documents", "op": "any_item", "value": {"kind": ["skill"]}},
                {"path": "/documents", "op": "any_item", "value": {}},
                {"path": "/documents", "op": "any_item", "value": {"/kind": "skill"}},
            ]
        }
    )
    bad = [i.path for i in condition_issues(spec, OPS) if i.severity == "error"]
    assert bad == ["/all/1/value", "/all/2/value", "/all/3/value"]
