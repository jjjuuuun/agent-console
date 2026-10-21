"""사용량 표시기 설정(작업 2R.25, usage-everywhere §6.1·§11 C-1)."""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    UiPreferences,
    UsageIndicatorColorRule,
    UsageIndicatorSettings,
    WorkspaceSettings,
    build_schema,
)

SPEC_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "placement": "sidebar-bottom",
    "windows": [],
    "max_items": 2,
    "fields": ["label", "value", "gauge"],
    "value_mode": "used",  # 0.8.0에서 remaining → used(사용자 지시)
    # 5.2R.56: 기본 색 규칙 3줄(0 초록 / 0.7 노랑 / 0.9 빨강)
    "color_rules": [
        {"at": 0.0, "tone": "success"},
        {"at": 0.7, "tone": "warning"},
        {"at": 0.9, "tone": "danger"},
    ],
    "hide_when_empty": False,
    "also_in_title": False,
}


def test_defaults_match_spec() -> None:
    assert UsageIndicatorSettings().model_dump() == SPEC_DEFAULTS
    assert UiPreferences().usage_indicator == UsageIndicatorSettings()


def test_schema_defaults_match_model_defaults() -> None:
    """웹은 기본값을 스키마에서 읽는다. 모든 키의 스키마 default가 모델 기본값과 같다."""
    props = build_schema()["$defs"]["UsageIndicatorSettings"]["properties"]
    assert set(props) == set(SPEC_DEFAULTS)
    for key, value in SPEC_DEFAULTS.items():
        assert props[key]["default"] == value, key
        assert props[key].get("title"), key
    assert props["fields"]["examples"]
    assert props["max_items"]["minimum"] == 1
    assert props["max_items"]["maximum"] == 6
    ui = build_schema()["$defs"]["UiPreferences"]["properties"]
    assert "usage_indicator" in ui


def test_window_ids_and_placement_are_open_strings() -> None:
    """창 id·배치·항목·색은 계약에 고정 목록이 없다(열린 문자열)."""
    props = build_schema()["$defs"]["UsageIndicatorSettings"]["properties"]
    assert "enum" not in props["placement"]
    assert "enum" not in props["windows"]["items"]
    assert "enum" not in props["fields"]["items"]
    rule = build_schema()["$defs"]["UsageIndicatorColorRule"]["properties"]
    assert "enum" not in rule["tone"]
    s = UsageIndicatorSettings.model_validate(
        {
            "placement": "my-custom-spot",
            "windows": ["any_window", "weekly_opus"],
            "fields": ["label", "future_field"],
            "color_rules": [{"at": 0.5, "tone": "custom-tone"}],
        }
    )
    assert s.placement == "my-custom-spot"
    assert s.windows == ["any_window", "weekly_opus"]
    assert s.fields == ["label", "future_field"]


@pytest.mark.parametrize(
    "doc",
    [
        {},
        {"ui": {}},
        {"ui": {"notifications": {"enabled": True}}},
        {"ui": {"keybindings": {"usage.peek": "Ctrl+U"}}},
    ],
)
def test_old_settings_without_key_read_defaults(doc: dict[str, Any]) -> None:
    ws = WorkspaceSettings.model_validate(doc)
    assert ws.ui.usage_indicator == UsageIndicatorSettings()
    # 생략 = 상속: 저장 형식에 기본값이 새로 끼어들지 않는다
    assert "usage_indicator" not in ws.ui.model_dump(exclude_unset=True)


def test_omitted_keys_are_not_dumped() -> None:
    assert UsageIndicatorSettings.model_validate({}).model_dump(exclude_unset=True) == {}
    partial = UsageIndicatorSettings.model_validate({"value_mode": "used"})
    assert partial.model_dump(exclude_unset=True) == {"value_mode": "used"}
    ws = WorkspaceSettings.model_validate({"ui": {"usage_indicator": {"enabled": False}}})
    assert ws.model_dump(exclude_unset=True) == {"ui": {"usage_indicator": {"enabled": False}}}


def test_round_trip_full() -> None:
    doc = {
        "enabled": False,
        "placement": "float-bottom-right",
        "windows": ["five_hour", "seven_day"],
        "max_items": 6,
        "fields": ["value", "label"],
        "value_mode": "used",
        "color_rules": [{"at": 0.8, "tone": "warning"}, {"at": 1.0, "tone": "danger"}],
        "hide_when_empty": True,
        "also_in_title": True,
    }
    s = UsageIndicatorSettings.model_validate(doc)
    assert s.model_dump(exclude_unset=True) == doc
    assert UsageIndicatorSettings.model_validate(s.model_dump()) == s


def test_unknown_keys_preserved() -> None:
    s = UsageIndicatorSettings.model_validate({"later_key": 1})
    assert s.model_dump(exclude_unset=True) == {"later_key": 1}


@pytest.mark.parametrize(
    "doc",
    [
        {"max_items": 0},
        {"max_items": 7},
        {"value_mode": "both"},
        {"placement": ""},
        {"windows": [""]},
        {"fields": [""]},
        {"color_rules": [{"at": -0.1, "tone": "warning"}]},
        {"color_rules": [{"at": 1.01, "tone": "warning"}]},
        {"color_rules": [{"at": 0.5, "tone": ""}]},
        {"color_rules": [{"at": 0.5}]},
        {"color_rules": [{"at": 0.8, "tone": "warning"}, {"at": 0.8, "tone": "danger"}]},
    ],
)
def test_range_errors(doc: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        UsageIndicatorSettings.model_validate(doc)


def test_range_boundaries_accepted() -> None:
    for n in (1, 6):
        assert UsageIndicatorSettings(max_items=n).max_items == n
    rules = [
        UsageIndicatorColorRule(at=0, tone="info"),
        UsageIndicatorColorRule(at=1, tone="danger"),
    ]
    assert len(UsageIndicatorSettings(color_rules=rules).color_rules) == 2


def test_duplicate_rule_error_is_reported_through_workspace() -> None:
    with pytest.raises(ValidationError) as exc:
        WorkspaceSettings.model_validate(
            {"ui": {"usage_indicator": {"color_rules": [{"at": 0.8, "tone": "a"}] * 2}}}
        )
    locs = [e["loc"] for e in exc.value.errors()]
    assert ("ui", "usage_indicator", "color_rules") in locs
