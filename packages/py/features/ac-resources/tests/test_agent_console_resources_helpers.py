"""도우미: 안전 치환, 비밀 참조, 설정 덮어쓰기, 전략 표, 단독 import."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from agent_console_contracts import Resource, ResourceAttachment
from agent_console_resources import (
    ATTACHMENT_STRATEGY,
    PREPEND_STRATEGY,
    InvalidConfigSchemaError,
    content_text,
    effective_resource,
    fill_value,
    find_plain_secrets,
    is_secret_ref,
    register_resource_strategies,
    render_template,
    resource_strategies,
    validate_config,
)
from agent_console_settings import DEFAULT_STRATEGIES, Layer, default_strategies, resolve_layers


def test_imports_standalone() -> None:
    module = importlib.import_module("agent_console_resources")
    for name in module.__all__:
        assert hasattr(module, name), name


def test_render_template_is_safe() -> None:
    class Obj:
        secret = "s"

    values = {"a": 1.234, "o": Obj(), "t": "{a}"}
    assert render_template("{a:.1f} {missing} {o.secret} {a:>99999}", values) == (
        "1.2 {missing} {o.secret} {a:>99999}"
    )
    assert render_template("{t}", values) == "{a}"  # 치환 결과를 다시 치환하지 않는다
    assert render_template("{t}{t}", values, max_chars=3) == "{a…"
    assert fill_value({"k": ["{a}", 2]}, values) == {"k": ["1.234", 2]}


def test_secret_helpers() -> None:
    assert is_secret_ref("secret://gh_token")
    assert not is_secret_ref("secret://")
    assert not is_secret_ref("plain")
    config = {"env": {"A": "secret://a", "B": "plain"}, "headers": {"x/y": "v"}, "other": 1}
    assert list(find_plain_secrets(config, ("env", "headers", "missing"))) == [
        "/env/B",
        "/headers/x~1y",
    ]


def test_effective_resource_and_content_text() -> None:
    res = Resource(id="r", type="t", name="n", config={"a": 1, "b": 2})
    assert effective_resource(res, None) is res
    eff = effective_resource(res, ResourceAttachment(ref="r", config_override={"b": 3}))
    assert eff.config == {"a": 1, "b": 3}
    assert res.config == {"a": 1, "b": 2}
    assert content_text(b"\xff") == "�"
    assert content_text(None) is None


def test_validate_config() -> None:
    assert validate_config({}, {"x": 1}) == []
    found = validate_config({"type": "object", "required": ["x"]}, {})
    assert found
    assert found[0].pointer == ""
    with pytest.raises(InvalidConfigSchemaError):
        validate_config({"type": 3}, {})
    with pytest.raises(InvalidConfigSchemaError):
        validate_config({"$ref": "https://example.invalid/s.json"}, {})


def test_strategy_tables() -> None:
    table = resource_strategies()
    assert {ATTACHMENT_STRATEGY, PREPEND_STRATEGY} <= set(table)
    assert ATTACHMENT_STRATEGY not in DEFAULT_STRATEGIES
    with pytest.raises(RuntimeError):
        register_resource_strategies(default_strategies().freeze())
    mine = default_strategies()
    mine.register(PREPEND_STRATEGY, DEFAULT_STRATEGIES["append"])  # 이미 있으면 두고 간다
    register_resource_strategies(mine)
    assert mine[PREPEND_STRATEGY] is DEFAULT_STRATEGIES["append"]


def test_keyed_attachments_reports_bad_input() -> None:
    table = resource_strategies()
    layers = [
        Layer("a", value={"r": [{"ref": "x"}, "junk", {"mode": "add"}]}),
        Layer("b", value={"r": "not-a-list"}),
    ]
    resolved = resolve_layers(layers, rules={"/r": ATTACHMENT_STRATEGY}, strategies=table)
    codes = [i.code for i in resolved.issues]
    assert codes.count("resource.invalid_attachment") == 2
    assert "type_mismatch" in codes
    assert resolved.value["r"] == "not-a-list"


def test_prepend_strategy() -> None:
    layers = [Layer("a", value={"l": [1]}), Layer("b", value={"l": [2, 3]})]
    resolved = resolve_layers(
        layers, rules={"/l": PREPEND_STRATEGY}, strategies=resource_strategies()
    )
    assert resolved.value["l"] == [2, 3, 1]
    assert resolved.source_of("/l/2") == "a"


@pytest.mark.parametrize(
    ("schema", "value", "validator"),
    [
        ({"type": "object"}, "sk-LEAK", "type"),
        ({"enum": ["a", "b"]}, "sk-LEAK", "enum"),
        ({"const": "a"}, "sk-LEAK", "const"),
        ({"type": "string", "pattern": "^x$"}, "sk-LEAK", "pattern"),
        ({"type": "string", "maxLength": 2}, "sk-LEAK", "maxLength"),
        (
            {"type": "object", "additionalProperties": False},
            {"sk-LEAK": "sk-LEAK"},
            "additionalProperties",
        ),
        ({"type": "array", "uniqueItems": True}, ["sk-LEAK", "sk-LEAK"], "uniqueItems"),
        ({"not": {"type": "string"}}, "sk-LEAK", "not"),
        ({"anyOf": [{"type": "integer"}]}, "sk-LEAK", "anyOf"),
    ],
)
def test_violation_messages_never_contain_input(
    schema: dict[str, Any], value: object, validator: str
) -> None:
    found = validate_config(schema, value)
    assert [v.validator for v in found] == [validator]
    assert "sk-LEAK" not in repr(found)


def test_violation_message_shows_expected_from_schema() -> None:
    schema = {"type": "object", "required": ["a", "b"], "properties": {"e": {"enum": ["x", "y"]}}}
    found = validate_config(schema, {"b": 1, "e": "secret"})
    messages = {v.pointer: v.message for v in found}
    assert "a" in messages[""]
    assert "b" not in messages[""].split(":")[-1]
    assert "x, y" in messages["/e"]
    assert "secret" not in repr(found)
