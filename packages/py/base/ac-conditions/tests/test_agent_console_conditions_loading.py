"""연산자 레지스트리 로딩(X22): 설치된 기본 연산자, 테스트 연산자 entry point 주입, 검사기."""

from __future__ import annotations

import sys
import types
from importlib.metadata import EntryPoint
from typing import Any

import pytest

from agent_console_conditions import (
    CONDITION_OPERATORS_GROUP,
    as_condition_operator,
    condition_issues,
    default_operators,
    evaluate_conditions,
    load_condition_operators,
    new_operator_registry,
    operator_descriptors,
    operator_map,
)
from agent_console_contracts import ConditionOperatorDescriptor, ConditionSpec
from agent_console_registry import InvalidExtensionError

BUILTIN = ["contains", "eq", "exists", "gt", "gte", "in", "lt", "lte", "matches", "ne"]


class WordCountAtLeast:
    """테스트 연산자: 텍스트 단어 수 >= 기대 값."""

    descriptor = ConditionOperatorDescriptor(
        id="words_at_least",
        title="단어 수 이상",
        value_schema={"type": "integer", "minimum": 0},
        applies_to=["string"],
    )

    def evaluate(self, actual: Any, expected: Any) -> bool:
        return (
            isinstance(actual, str)
            and isinstance(expected, int)
            and (len(actual.split()) >= expected)
        )


@pytest.fixture
def plugin_module(monkeypatch: pytest.MonkeyPatch) -> str:
    mod = types.ModuleType("ac_conditions_test_plugin")
    mod.WordCountAtLeast = WordCountAtLeast  # type: ignore[attr-defined]
    mod.not_an_operator = object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, mod.__name__, mod)
    return mod.__name__


def test_installed_entry_points_bring_builtin_operators() -> None:
    ops, reports = default_operators()
    assert all(r.ok for r in reports)
    assert sorted(k for k in ops if k in BUILTIN) == BUILTIN
    assert [d.id for d in operator_descriptors(ops) if d.id in BUILTIN] == BUILTIN


def test_injected_test_operator_entry_point(plugin_module: str) -> None:
    eps = [
        EntryPoint(
            "words_at_least", f"{plugin_module}:WordCountAtLeast", CONDITION_OPERATORS_GROUP
        ),
        EntryPoint("broken", f"{plugin_module}:not_an_operator", CONDITION_OPERATORS_GROUP),
        EntryPoint("ignored", f"{plugin_module}:WordCountAtLeast", "other.group"),
    ]
    registry = new_operator_registry()
    reports = load_condition_operators(registry, entry_points=eps)
    assert [(r.key, r.status) for r in reports] == [
        ("broken", "failed"),
        ("words_at_least", "loaded"),
    ]
    ops = operator_map(registry)
    assert list(ops) == ["words_at_least"]
    spec = ConditionSpec.model_validate(
        {"all": [{"path": "/output", "op": "words_at_least", "value": 3}]}
    )
    assert evaluate_conditions(spec, {"output": "a b c"}, ops).result is True
    assert evaluate_conditions(spec, {"output": "a b"}, ops).result is False
    bad = ConditionSpec.model_validate(
        {"all": [{"path": "/output", "op": "words_at_least", "value": -1}]}
    )
    assert [i.code for i in condition_issues(bad, ops)] == ["condition.invalid_value"]
    # 플러그인을 지우면(레지스트리에 없음) 저장 warning·실행 거짓
    assert [i.severity for i in condition_issues(spec, {})] == ["warning"]
    assert evaluate_conditions(spec, {"output": "a b c"}, {}).result is False


def test_enabled_filter_and_validator() -> None:
    registry = new_operator_registry()
    eps = [
        EntryPoint("eq", "agent_console_conditions.builtin:EQ", CONDITION_OPERATORS_GROUP),
        EntryPoint("ne", "agent_console_conditions.builtin:NE", CONDITION_OPERATORS_GROUP),
    ]
    reports = load_condition_operators(registry, enabled={"eq"}, entry_points=eps)
    assert [(r.key, r.status) for r in reports] == [("eq", "loaded"), ("ne", "skipped")]
    with pytest.raises(InvalidExtensionError):
        registry.register("x", object())  # type: ignore[arg-type]
    assert isinstance(as_condition_operator(WordCountAtLeast), WordCountAtLeast)
    with pytest.raises(TypeError):
        as_condition_operator(object())


def test_operator_consumer_is_a_structural_capability() -> None:
    """연산자를 쓰는 확장이 앱 레지스트리를 받는 선택 능력(`OperatorConsumer`, 5R.13)."""
    from agent_console_conditions import OperatorConsumer, OperatorProvider, operator_map

    class Uses:
        def __init__(self) -> None:
            self.source: OperatorProvider | None = None

        def use_operators(self, source: OperatorProvider) -> None:
            self.source = source

    registry = new_operator_registry()
    item = Uses()
    assert isinstance(item, OperatorConsumer)
    assert not isinstance(object(), OperatorConsumer)
    item.use_operators(lambda: operator_map(registry))
    assert item.source is not None
    assert item.source() == {}
