"""약한 키 이름(5.7R.33y2): `input_key` 같은 이름은 값이 비밀 모양일 때만 의심한다."""

from __future__ import annotations

import pytest

from agent_console_secret_rules import (
    DEFAULT_WEAK_KEY_NAMES,
    InvalidSecretRuleError,
    SecretRules,
    default_rules,
)

HEX_KEY = "9f86d081884c7d659a2feaa0c55ad015"
UUID = "550e8400-e29b-41d4-a716-446655440000"


def _paths(rules: SecretRules, value: object) -> list[str]:
    return [f.path for f in rules.find_suspected(value)]


def test_default_weak_names_are_data() -> None:
    assert "key" in DEFAULT_WEAK_KEY_NAMES
    assert default_rules().weak_key_names == DEFAULT_WEAK_KEY_NAMES


@pytest.mark.parametrize("name", ["input_key", "inputKey", "sort_key", "primary_key", "key"])
def test_weak_name_with_plain_value_is_not_suspected(name: str) -> None:
    rules = default_rules()
    assert _paths(rules, {name: "question"}) == []
    assert _paths(rules, {name: "step_2_output_summary"}) == []
    assert _paths(rules, {name: 3}) == []


@pytest.mark.parametrize("value", [HEX_KEY, UUID, "sk-" + "ant-abcdef123456", "ghp_ABCDEF123456"])
def test_weak_name_with_secret_shaped_value_is_suspected(value: str) -> None:
    findings = default_rules().find_suspected({"input_key": value})
    assert [f.path for f in findings] == ["/input_key"]


@pytest.mark.parametrize("name", ["api_key", "API_KEY", "x-api-key", "secret_key", "privateKey"])
def test_strong_names_still_suspected_by_name_alone(name: str) -> None:
    assert _paths(default_rules(), {name: "abc"}) == [f"/{name}"]


def test_weak_name_inherited_by_children() -> None:
    rules = default_rules()
    assert _paths(rules, {"key": {"a": "plain", "b": HEX_KEY}}) == ["/key/b"]
    # 강한 이름 아래의 약한 이름은 강한 쪽을 이어받는다
    assert _paths(rules, {"token": {"input_key": "plain"}}) == ["/token/input_key"]


def test_flags_and_name_check_stay_strict() -> None:
    rules = default_rules()
    assert rules.name_suspected("input_key")
    assert _paths(rules, ["--key", "plain"]) == ["/1"]
    assert rules.redact_suspected("input_key=plain") == "input_key=[REDACTED]"


def test_user_can_turn_off_weak_names() -> None:
    rules = SecretRules(weak_key_names=())
    assert _paths(rules, {"input_key": "question"}) == ["/input_key"]


def test_user_added_name_overrides_weak_list() -> None:
    rules = default_rules().with_extra(key_names=["key"])
    assert "key" not in rules.weak_key_names
    assert _paths(rules, {"input_key": "question"}) == ["/input_key"]
    # 더한 것이 다른 이름이면 약한 이름은 그대로
    other = default_rules().with_extra(key_names=["deploy_key"])
    assert _paths(other, {"input_key": "question", "deploy_key": "x"}) == ["/deploy_key"]


def test_user_weak_rules_replace_defaults() -> None:
    rules = SecretRules(weak_key_names=["key", "auth"], weak_value_patterns=[r"^corp-[0-9]{4}$"])
    assert _paths(rules, {"auth": "oauth", "input_key": "corp-1234"}) == ["/input_key"]


def test_invalid_weak_rules_rejected() -> None:
    with pytest.raises(InvalidSecretRuleError) as info:
        SecretRules(weak_key_names=["--"], weak_value_patterns=["(a+)+"])
    assert {p.field for p in info.value.problems} == {"weak_key_names", "weak_value_patterns"}
