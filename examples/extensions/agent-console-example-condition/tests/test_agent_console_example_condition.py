"""예제 조건 연산자 `example.word_count_at_least`: entry point 선언·판정·평가기·저장 전 검사·
조건 연결(`when`) 실행·제거.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 평가기(ac-conditions)·조건 연결
(ac-nodes-core)·엔진 harness(ac-runtime)는 dev 의존이고, 이 연산자는 레지스트리에 직접 등록한다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from agent_console_conditions import (
    CONDITION_OPERATORS_GROUP,
    MISSING,
    ConditionIssueCodes,
    ConditionOperator,
    ConditionReasons,
    builtin_operators,
    condition_issues,
    evaluate_conditions,
    new_operator_registry,
    operator_descriptors,
    operator_map,
)
from agent_console_contracts import ConditionSpec, EdgeSpec, Endpoint, Graph, NodeSpec, Run
from agent_console_example_condition import OPERATOR_ID, WordCountAtLeast, word_count
from agent_console_nodes_core import WhenEdge
from agent_console_runtime.testing import entry, make_harness, with_entries

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def at_least(n: Any, path: str = "/output") -> ConditionSpec:
    return ConditionSpec.model_validate({"all": [{"path": path, "op": OPERATOR_ID, "value": n}]})


# ---------------------------------------------------------------- 등록·디스크립터·판정


def test_entry_point_declared_in_operator_group_with_descriptor_id() -> None:
    meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    eps = meta["project"]["entry-points"][CONDITION_OPERATORS_GROUP]
    assert eps == {OPERATOR_ID: "agent_console_example_condition:WordCountAtLeast"}


def test_descriptor_is_listed_after_registration() -> None:
    registry = new_operator_registry()
    registry.register(OPERATOR_ID, WordCountAtLeast())
    [desc] = operator_descriptors(registry)
    assert desc.id == OPERATOR_ID
    assert desc.value_schema == {"type": "integer", "minimum": 0}
    assert desc.applies_to == ["string"]


@pytest.mark.parametrize(
    ("actual", "expected", "result"),
    [
        ("하나 둘 셋", 3, True),
        ("하나  둘\n셋 넷", 3, True),
        ("하나 둘", 3, False),
        ("", 0, True),
        (["하나", "둘", "셋"], 1, False),  # 텍스트가 아니면 거짓
        (MISSING, 0, False),  # 경로에 값이 없으면 거짓
        ("하나 둘", "1", False),  # 기대 값 형식이 틀리면 거짓
        ("하나 둘", True, False),
        ("하나 둘", -1, False),
    ],
)
def test_evaluate(actual: Any, expected: Any, result: bool) -> None:
    assert WordCountAtLeast().evaluate(actual, expected) is result


def test_word_count() -> None:
    assert word_count(" a  b\tc\n") == 3


# -------------------------------------------------------- 평가기·저장 전 검사(ac-conditions)


def test_evaluator_uses_operator_with_builtins() -> None:
    operators: dict[str, ConditionOperator] = {op.descriptor.id: op for op in builtin_operators()}
    operators[OPERATOR_ID] = WordCountAtLeast()
    spec = ConditionSpec.model_validate(
        {
            "all": [
                {"path": "/output", "op": OPERATOR_ID, "value": 3},
                {"path": "/output", "op": "contains", "value": "검토"},
            ]
        }
    )
    outcome = evaluate_conditions(spec, {"output": "검토 결과 세 단어"}, operators)
    assert outcome.result is True
    short = evaluate_conditions(spec, {"output": "검토"}, operators)
    assert short.result is False
    assert [(i.op, i.result) for i in short.items or []] == [
        (OPERATOR_ID, False),
        ("contains", True),
    ]


def test_save_check_uses_value_schema() -> None:
    operators = operator_map(_registry())
    assert condition_issues(at_least(2), operators) == []
    [bad] = condition_issues(at_least("2"), operators, base_path="/conditions")
    assert (bad.severity, bad.code) == ("error", ConditionIssueCodes.INVALID_VALUE)
    assert bad.path == "/conditions/all/0/value"


def test_removed_operator_warns_on_save_and_is_false_on_run() -> None:
    """README 주장 고정: 제거(등록 없음)하면 조건 데이터는 남고, 저장 전 검사 warning·
    실행 시 거짓."""
    operators = operator_map(new_operator_registry())  # 이 연산자 없음
    [issue] = condition_issues(at_least(1), operators)
    assert (issue.severity, issue.code) == ("warning", ConditionIssueCodes.UNKNOWN_OPERATOR)
    outcome = evaluate_conditions(at_least(1), {"output": "아주 긴 글"}, operators)
    assert outcome.result is False
    [item] = outcome.items or []
    assert item.reason == ConditionReasons.UNKNOWN_OPERATOR


def _registry() -> Any:
    registry = new_operator_registry()
    registry.register(OPERATOR_ID, WordCountAtLeast())
    return registry


# ---------------------------------------------------------------- 조건 연결 실행(엔진)


def _graph(text: str, minimum: int) -> Graph:
    """a(결과 = text) ─when(단어 수 ≥ minimum)→ b."""
    edge = EdgeSpec(
        id="a.out->b.in",
        source=Endpoint(node="a", port="out"),
        target=Endpoint(node="b", port="in"),
        kind="when",
        config={"conditions": at_least(minimum).model_dump(exclude_none=True)},
    )
    nodes = [
        NodeSpec(id="a", type="t.step", config={"outputs": {"out": text}}),
        NodeSpec(id="b", type="t.step", config={}),
    ]
    return with_entries(Graph(id="g", name="g", nodes=nodes, edges=[edge]), entry("a"))


async def _run(text: str, minimum: int, *, installed: bool = True) -> tuple[Run, Any]:
    h = make_harness()
    operators = operator_map(_registry() if installed else new_operator_registry())
    h.registries.edge_types.register("when", WhenEdge(operators))
    run = await h.make().run(_graph(text, minimum), {"in": "x"})
    return run, h


@pytest.mark.parametrize(("text", "passes"), [("하나 둘 셋 넷", True), ("하나 둘", False)])
async def test_when_edge_passes_only_long_enough_text(text: str, passes: bool) -> None:
    run, h = await _run(text, 3)
    assert run.status == "completed", run.error
    assert any(node == "b" for node, _ in h.probe.calls) is passes


async def test_when_edge_without_plugin_blocks_with_warning() -> None:
    run, h = await _run("하나 둘 셋 넷", 3, installed=False)
    assert run.status == "completed", run.error
    assert all(node != "b" for node, _ in h.probe.calls)
