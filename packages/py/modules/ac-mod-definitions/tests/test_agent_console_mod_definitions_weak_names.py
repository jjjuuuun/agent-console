"""설정 `secrets.weak_key_names`(계약 0.13.1, 5.7R.33y2 후속).

null이면 기본 데이터, 주면 그 목록으로 바꾼다.
"""

from __future__ import annotations

from agent_console_contracts import SecretRuleSettings, WorkspaceSettings
from agent_console_mod_definitions.workspace import (
    SecretRuleCheck,
    build_rules,
    settings_rule_issues,
)
from agent_console_secret_rules import DEFAULT_WEAK_KEY_NAMES, default_rules
from agent_console_store import SETTINGS_KIND

HEX_KEY = "9f86d081884c7d659a2feaa0c55ad015"


def _paths(settings: SecretRuleSettings, value: object) -> list[str]:
    return [f.path for f in build_rules(settings).find_suspected(value)]


def test_null_uses_default_data() -> None:
    settings = SecretRuleSettings()
    assert settings.weak_key_names is None
    rules = build_rules(settings)
    assert rules.weak_key_names == DEFAULT_WEAK_KEY_NAMES
    assert rules.key_names == default_rules().key_names
    assert _paths(settings, {"input_key": "question"}) == []
    assert _paths(settings, {"input_key": HEX_KEY}) == ["/input_key"]


def test_empty_list_turns_weak_names_off() -> None:
    settings = SecretRuleSettings(weak_key_names=[])
    assert build_rules(settings).weak_key_names == ()
    assert _paths(settings, {"input_key": "question"}) == ["/input_key"]


def test_custom_list_replaces_default() -> None:
    settings = SecretRuleSettings(weak_key_names=["token"])
    assert build_rules(settings).weak_key_names == ("token",)
    assert _paths(settings, {"token": "plain"}) == []
    assert _paths(settings, {"token": HEX_KEY}) == ["/token"]
    assert _paths(settings, {"input_key": "question"}) == ["/input_key"]  # 기본 `key`는 빠짐


def test_extra_key_names_still_win_over_weak_names() -> None:
    settings = SecretRuleSettings(weak_key_names=["token"], extra_key_names=["token"])
    assert build_rules(settings).weak_key_names == ()
    assert _paths(settings, {"token": "plain"}) == ["/token"]


def test_invalid_weak_names_are_dropped_and_reported() -> None:
    settings = SecretRuleSettings(weak_key_names=["token", "!!"])
    assert build_rules(settings).weak_key_names == ("token",)
    issues = settings_rule_issues(settings)
    assert [(i.code, i.path, i.severity) for i in issues] == [
        ("secret.invalid_rule", "/secrets/weak_key_names/1", "error")
    ]
    assert "!!" not in issues[0].message


def test_save_check_reads_weak_names_from_document() -> None:
    check = SecretRuleCheck()
    ok = WorkspaceSettings.model_validate({"secrets": {"weak_key_names": ["token"]}})
    assert check.issues(SETTINGS_KIND.name, ok) == []
    bad = {"secrets": {"weak_key_names": [" "]}}
    assert [i.path for i in check.issues(SETTINGS_KIND.name, bad)] == ["/secrets/weak_key_names/0"]


def test_weak_names_round_trip_only_when_set() -> None:
    assert "weak_key_names" not in SecretRuleSettings().model_dump(exclude_unset=True)
    dumped = SecretRuleSettings(weak_key_names=["key"]).model_dump(mode="json")
    assert dumped["weak_key_names"] == ["key"]
