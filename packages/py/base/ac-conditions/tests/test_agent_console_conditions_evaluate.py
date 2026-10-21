"""evaluate_conditions(all·any·negate·근거)와 condition_issues(저장 전 검사)."""

from __future__ import annotations

from typing import Any

from agent_console_conditions import (
    ConditionIssueCodes,
    ConditionOperator,
    ConditionReasons,
    builtin_operators,
    condition_issues,
    evaluate_conditions,
    resolve_pointer,
    shorten_actual,
)
from agent_console_conditions._values import MISSING
from agent_console_contracts import ConditionOperatorDescriptor, ConditionSpec

OPS = {op.descriptor.id: op for op in builtin_operators()}
SUBJECT: dict[str, Any] = {
    "output": "all tests PASS (12)",
    "structured": {"verdict": "fail", "score": 0.4, "a/b": 1, "m~n": 2},
    "status": "succeeded",
    "iteration": 2,
    "list": [10, 20],
}


def spec(data: dict[str, Any]) -> ConditionSpec:
    return ConditionSpec.model_validate(data)


def test_resolve_pointer() -> None:
    assert resolve_pointer(SUBJECT, "") is SUBJECT
    assert resolve_pointer(SUBJECT, "/structured/verdict") == "fail"
    assert resolve_pointer(SUBJECT, "/structured/a~1b") == 1
    assert resolve_pointer(SUBJECT, "/structured/m~0n") == 2
    assert resolve_pointer(SUBJECT, "/list/1") == 20
    assert resolve_pointer(SUBJECT, "/list/2") is MISSING
    assert resolve_pointer(SUBJECT, "/list/01") is MISSING
    assert resolve_pointer(SUBJECT, "/list/x") is MISSING
    assert resolve_pointer(SUBJECT, "/output/0") is MISSING
    assert resolve_pointer(SUBJECT, "/nope") is MISSING
    assert resolve_pointer(SUBJECT, "output") is MISSING


def test_all_true_and_evidence() -> None:
    out = evaluate_conditions(
        spec({"all": [{"path": "/output", "op": "contains", "value": "PASS"}]}), SUBJECT, OPS
    )
    assert out.result is True
    assert out.combinator == "all"
    assert out.negate is None
    assert out.items is not None
    item = out.items[0]
    assert (item.path, item.op, item.value, item.result) == ("/output", "contains", "PASS", True)
    assert item.actual == "all tests PASS (12)"
    assert item.mode is None
    assert item.reason is None


def test_all_evaluates_every_item() -> None:
    out = evaluate_conditions(
        spec(
            {
                "all": [
                    {"path": "/structured/verdict", "op": "eq", "value": "ok"},
                    {"path": "/iteration", "op": "gte", "value": 2},
                ]
            }
        ),
        SUBJECT,
        OPS,
    )
    assert out.result is False
    assert [i.result for i in out.items or []] == [False, True]


def test_any_and_negate() -> None:
    data: dict[str, Any] = {
        "any": [
            {"path": "/structured/verdict", "op": "eq", "value": "ok"},
            {"path": "/iteration", "op": "gte", "value": 2},
        ]
    }
    assert evaluate_conditions(spec(data), SUBJECT, OPS).result is True
    out = evaluate_conditions(spec({**data, "negate": True}), SUBJECT, OPS)
    assert out.result is False
    assert out.negate is True
    assert out.combinator == "any"


def test_all_and_any_together_need_both() -> None:
    data = {
        "all": [{"path": "/status", "op": "eq", "value": "succeeded"}],
        "any": [{"path": "/iteration", "op": "lt", "value": 1}],
    }
    out = evaluate_conditions(spec(data), SUBJECT, OPS)
    assert out.result is False
    assert out.combinator is None
    assert [i.mode for i in out.items or []] == ["all", "any"]


def test_empty_is_true() -> None:
    empties: list[dict[str, Any]] = [{}, {"all": []}, {"any": []}]
    for data in empties:
        out = evaluate_conditions(spec(data), SUBJECT, OPS)
        assert out.result is True
        assert out.items == []
    assert evaluate_conditions(spec({"negate": True}), SUBJECT, OPS).result is False


def test_missing_unknown_and_error_reasons() -> None:
    class Boom:
        descriptor = ConditionOperatorDescriptor(id="boom", title="터짐")

        def evaluate(self, actual: Any, expected: Any) -> bool:
            raise RuntimeError("x")

    ops: dict[str, ConditionOperator] = {**OPS, "boom": Boom()}
    out = evaluate_conditions(
        spec(
            {
                "any": [
                    {"path": "/nope", "op": "eq", "value": 1},
                    {"path": "/output", "op": "gone", "value": 1},
                    {"path": "/output", "op": "boom"},
                    {"path": "/nope", "op": "exists"},
                ]
            }
        ),
        SUBJECT,
        ops,
    )
    assert out.result is False
    assert [(i.result, i.reason) for i in out.items or []] == [
        (False, ConditionReasons.MISSING),
        (False, ConditionReasons.UNKNOWN_OPERATOR),
        (False, ConditionReasons.ERROR),
        (False, ConditionReasons.MISSING),
    ]
    assert (out.items or [])[0].actual is None


def test_actual_is_redacted_then_shortened() -> None:
    secret = "sk-SECRET-VALUE"
    long_text = "x" * 190 + secret + "y" * 50
    out = evaluate_conditions(
        spec({"all": [{"path": "/t", "op": "contains", "value": "y"}]}),
        {"t": long_text},
        OPS,
        redact=lambda v: v.replace(secret, "[REDACTED]") if isinstance(v, str) else v,
        max_actual_chars=210,
    )
    actual = (out.items or [])[0].actual
    assert isinstance(actual, str)
    assert "SECRET" not in actual
    assert actual.startswith("x" * 190 + "[REDACTED]")
    assert actual.endswith("…")
    assert len(actual) == 211


def test_shorten_actual_shapes() -> None:
    assert shorten_actual(5) == 5
    assert shorten_actual([1, 2]) == [1, 2]
    big = {"k": "v" * 500}
    short = shorten_actual(big, 20)
    assert isinstance(short, str)
    assert short.endswith("…")
    assert len(short) == 21
    assert shorten_actual(MISSING) is None


# ---------------------------------------------------------------- condition_issues


def codes(issues: list[Any]) -> list[tuple[str, str, str | None]]:
    return [(i.severity, i.code, i.path) for i in issues]


def test_issues_unknown_operator_warning() -> None:
    issues = condition_issues(
        spec({"all": [{"path": "/output", "op": "fuzzy", "value": "x"}]}),
        OPS,
        base_path="/conditions",
        edge_id="e1",
    )
    assert codes(issues) == [
        ("warning", ConditionIssueCodes.UNKNOWN_OPERATOR, "/conditions/all/0/op")
    ]
    assert issues[0].details == {"op": "fuzzy"}
    assert issues[0].edge_id == "e1"


def test_issues_invalid_values() -> None:
    issues = condition_issues(
        spec(
            {
                "any": [
                    {"path": "/iteration", "op": "gt", "value": "3"},
                    {"path": "/output", "op": "in", "value": "ok"},
                    {"path": "/output", "op": "matches", "value": "(a+)+"},
                    {"path": "/output", "op": "exists", "value": True},
                    {"path": "/output", "op": "exists"},
                    {"path": "/iteration", "op": "gte"},
                    {"path": "/output", "op": "eq"},
                ]
            }
        ),
        OPS,
    )
    assert codes(issues) == [
        ("error", ConditionIssueCodes.INVALID_VALUE, "/any/0/value"),
        ("error", ConditionIssueCodes.INVALID_VALUE, "/any/1/value"),
        ("error", ConditionIssueCodes.INVALID_VALUE, "/any/2/value"),
        ("error", ConditionIssueCodes.INVALID_VALUE, "/any/3/value"),
        ("error", ConditionIssueCodes.INVALID_VALUE, "/any/5/value"),
    ]
    assert all(i.details == {"op": i.details["op"]} for i in issues)


def test_issues_empty_warning_and_clean() -> None:
    assert codes(condition_issues(spec({}), OPS, base_path="/conditions")) == [
        ("warning", ConditionIssueCodes.EMPTY, "/conditions")
    ]
    ok = spec({"all": [{"path": "/output", "op": "contains", "value": "PASS"}]})
    assert condition_issues(ok, OPS) == []
