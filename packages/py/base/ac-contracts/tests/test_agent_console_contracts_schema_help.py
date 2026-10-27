"""설정 폼 도움말 린트(schema_help)와 계약 폼 모델의 x-ui 데이터(ux-overhaul 설정 폼 분류표)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import X_UI, X_UI_TIERS, XUiKeys
from agent_console_contracts.schema import build_schema
from agent_console_contracts.schema_help import (
    HelpIssue,
    contract_form_roots,
    lint_contract_help,
    lint_schema_help,
    schema_help_rules_data,
)


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def _good(**extra: Any) -> dict[str, Any]:
    prop: dict[str, Any] = {
        "type": "string",
        "title": "이름",
        "description": "화면에 보일 이름입니다.",
        X_UI: {"tier": "basic", "example": "조사 팀원", "when": "이름을 바꾸고 싶을 때 바꾸세요."},
    }
    prop.update(extra)
    return prop


def _rules(issues: list[HelpIssue]) -> list[str]:
    return sorted(i.rule for i in issues)


# ---------------------------------------------------------------- 규칙 하나씩


def test_good_property_passes() -> None:
    assert lint_schema_help(_obj({"name": _good()})) == []


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ({"title": None}, "missing-title"),
        ({"description": None}, "missing-description"),
        ({"description": "  "}, "missing-description"),
        ({"description": "가" * 101}, "description-too-long"),
        ({"description": "이름."}, "description-same-as-title"),
        ({X_UI: {"example": "x"}}, "missing-tier"),
        ({X_UI: {"tier": "basic", "example": "x"}}, "missing-when"),
        ({X_UI: {"tier": "hidden", "example": "x"}}, "bad-tier"),
        ({X_UI: {"tier": "basic", "example": "x", "colour": "red"}}, "unknown-x-ui-key"),
        ({X_UI: {"tier": "basic"}}, "missing-example"),
        ({"description": "자세한 것은 design §5 참고."}, "forbidden-text"),
        ({"description": "백엔드 디스크립터 id입니다."}, "jargon"),
        ({X_UI: {"tier": "basic", "example": "x", "when": "Phase 2에서 바꿉니다."}}, "jargon"),
    ],
)
def test_each_rule_is_reported(change: dict[str, Any], rule: str) -> None:
    prop = _good()
    for key, value in change.items():
        if value is None:
            prop.pop(key)
        else:
            prop[key] = value
    issues = lint_schema_help(_obj({"name": prop}))
    assert rule in _rules(issues)
    assert all(i.path.startswith("#/properties/name") for i in issues)


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("공통 층 설정(`WorkspaceSettings.agent_defaults`)입니다.", "code-identifier"),
        ("WorkspaceSettings.agent_defaults와 같습니다.", "class-field-path"),
        ("필드는 AgentSettings와 같습니다.", "model-name"),
        ("값은 agent_defaults.backend에 저장됩니다.", "field-path"),
        ("5.2R.23부터 기본값이 바뀌었습니다.", "task-id"),
    ],
)
def test_internal_names_are_jargon(text: str, rule_id: str) -> None:
    issues = lint_schema_help(_obj({"name": _good(description=text)}))
    assert [i.rule for i in issues] == ["jargon"] * len(issues)
    assert any(f"({rule_id})" in i.message for i in issues), issues


@pytest.mark.parametrize(
    "text",
    [
        "기록할 hook(도구 실행 전후에 도는 명령) 이벤트 이름입니다(예: PreToolUse, Stop).",
        "셀 값입니다(예: events = 이벤트 수, tokens.total = 토큰 합계).",
        "사용자 홈(`~/.claude`가 있는 곳)입니다.",
        "결과에서 비교할 값의 위치입니다(예: /structured/verdict).",
    ],
)
def test_user_words_with_examples_are_not_jargon(text: str) -> None:
    assert lint_schema_help(_obj({"name": _good(description=text)})) == []


def test_object_descriptions_are_checked_only_when_asked() -> None:
    schema = {
        "$defs": {
            "Defaults": {
                **_obj({"name": _good()}),
                "description": "공통 층 설정(`WorkspaceSettings.agent_defaults`).",
            }
        }
    }
    assert lint_schema_help(schema) == []
    issues = lint_schema_help(schema, objects=True)
    assert issues
    assert {i.path for i in issues} == {"#/$defs/Defaults/description"}
    assert lint_schema_help(schema, roots=["Defaults"], objects=True) != []


def test_example_rule_accepts_default_examples_null_marker_required_and_choices() -> None:
    base = {"title": "값", "description": "비교할 값입니다.", X_UI: {"tier": "advanced"}}
    cases = {
        "with_default": {**base, "type": "integer", "default": 3},
        "with_examples": {**base, "type": "number", "examples": [0.8]},
        # 예시 없음을 명시(null): 목록에서 고르는 값
        "explicit_null": {**base, "type": "string", X_UI: {"tier": "advanced", "example": None}},
        "enum": {
            **base,
            X_UI: {"tier": "advanced", "enum_labels": {"a": "가", "b": "나"}},
            "anyOf": [{"enum": ["a", "b"]}, {"type": "null"}],
            "default": None,
        },
        "ref": {**base, "anyOf": [{"$ref": "#/$defs/Mode"}, {"type": "null"}], "default": None},
        "required": {**base, "type": "string"},
        "boolean": {**base, "type": "boolean"},
        "list": {**base, "type": "array", "items": {"type": "string"}},
    }
    assert lint_schema_help(_obj(cases, required=["required"])) == []
    null_default = {**base, "anyOf": [{"type": "string"}, {"type": "null"}], "default": None}
    assert _rules(lint_schema_help(_obj({"n": null_default}))) == ["missing-example"]


def test_enum_values_need_labels() -> None:
    base = {"title": "값", "description": "고를 값입니다.", "default": "a"}
    defs = {"Mode": {"enum": ["a", "b"], "type": "string"}}

    def check(prop: dict[str, Any]) -> list[str]:
        schema = {**_obj({"m": prop}), "$defs": defs}
        return [i.rule for i in lint_schema_help(schema) if i.rule == "missing-enum-labels"]

    plain = {**base, "enum": ["a", "b"], X_UI: {"tier": "advanced"}}
    assert check(plain) == ["missing-enum-labels"]
    via_ref = {**base, "$ref": "#/$defs/Mode", X_UI: {"tier": "advanced"}}
    assert check(via_ref) == ["missing-enum-labels"]
    half = {**plain, X_UI: {"tier": "advanced", "enum_labels": {"a": "가"}}}
    assert check(half) == ["missing-enum-labels"]
    full = {**plain, X_UI: {"tier": "advanced", "enum_labels": {"a": "가", "b": "나"}}}
    assert check(full) == []
    titled = {**base, "oneOf": [{"const": "a", "title": "가"}, {"const": "b", "title": "나"}]}
    assert check({**titled, X_UI: {"tier": "advanced"}}) == []


def test_enum_labels_cover_nested_choices() -> None:
    """배열 ``items``(다중 선택)·``anyOf``·``oneOf``·``$ref`` 안의 enum도 라벨을 본다."""
    base = {"title": "값", "description": "고를 값입니다.", X_UI: {"tier": "advanced"}}
    defs = {"Mode": {"enum": ["a", "b"], "type": "string"}}
    labels = {"a": "가", "b": "나"}

    def check(prop: dict[str, Any]) -> list[str]:
        schema = {**_obj({"m": prop}, required=["m"]), "$defs": defs}
        return [i.rule for i in lint_schema_help(schema) if i.rule == "missing-enum-labels"]

    cases: dict[str, dict[str, Any]] = {
        "items": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}},
        "items-ref": {"type": "array", "items": {"$ref": "#/$defs/Mode"}},
        "nullable-items": {
            "anyOf": [{"type": "array", "items": {"enum": ["a", "b"]}}, {"type": "null"}]
        },
        "oneOf-ref": {"oneOf": [{"$ref": "#/$defs/Mode"}, {"type": "null"}]},
        "anyOf-enum": {"anyOf": [{"enum": ["a"]}, {"enum": ["b"]}]},
    }
    for name, shape in cases.items():
        assert check({**base, **shape}) == ["missing-enum-labels"], name
        labelled = {**base, **shape, X_UI: {"tier": "advanced", "enum_labels": labels}}
        assert check(labelled) == [], name
    # 라벨은 배열 필드에 둔다(다중 선택 위젯이 배열 스키마를 읽는다). items 쪽 라벨은 덮지 못한다.
    on_items = {
        **base,
        "type": "array",
        "items": {"enum": ["a", "b"], X_UI: {"enum_labels": labels}},
    }
    assert check(on_items) == ["missing-enum-labels"]
    # 배열 안 객체의 enum 필드는 그 필드 자리에서 따로 본다(배열 필드에는 걸지 않는다).
    objects = {
        **base,
        "type": "array",
        "items": {"type": "object", "properties": {"k": {**base, "enum": ["a", "b"]}}},
    }
    found = [
        i.path
        for i in lint_schema_help(_obj({"m": objects}, required=["m"]))
        if i.rule == "missing-enum-labels"
    ]
    assert found == ["#/properties/m/items/properties/k"]


def test_x_ui_helper_carries_enum_labels() -> None:
    from agent_console_contracts import x_ui

    assert x_ui(enum_labels={"a": "가"})[X_UI] == {"enum_labels": {"a": "가"}}


def test_when_is_required_only_for_basic_tier() -> None:
    advanced = _good()
    advanced[X_UI] = {"tier": "advanced", "example": "x"}
    assert lint_schema_help(_obj({"a": advanced})) == []
    basic = _good()
    basic[X_UI] = {"tier": "basic", "example": "x"}
    issues = lint_schema_help(_obj({"b": basic}))
    assert [(i.rule, i.severity) for i in issues] == [("missing-when", "error")]


def test_hard_terms_are_warnings_and_explanations_silence_them() -> None:
    plain = _good(description="비우면 위 층 값을 씁니다.")
    issues = lint_schema_help(_obj({"p": plain}))
    assert [(i.rule, i.severity) for i in issues] == [("hard-term", "warning")]
    hook = _good(description="hook을 걸 대상입니다.")  # 조사가 붙은 낱말은 경계가 아니다
    assert lint_schema_help(_obj({"h": hook})) == []
    bare = _good(description="실행 전 hook 이름입니다.")
    assert _rules(lint_schema_help(_obj({"h": bare}))) == ["hard-term"]
    explained = _good(description="실행 전 hook(도구 실행 전후에 도는 명령) 이름입니다.")
    assert lint_schema_help(_obj({"h": explained})) == []
    # when의 용어는 같은 필드 설명의 풀이로 충분하다
    when_only = _good(description="hook(도구 실행 전후에 도는 명령) 이름입니다.")
    when_only[X_UI] = {**when_only[X_UI], "when": "특정 hook만 볼 때 바꾸세요."}
    assert lint_schema_help(_obj({"w": when_only})) == []


def test_const_properties_are_skipped() -> None:
    assert lint_schema_help(_obj({"kind": {"const": "agent", "default": "agent"}})) == []


def test_walks_nested_items_anyof_and_defs() -> None:
    schema = {
        "type": "object",
        "properties": {
            "rows": {**_good(type="array"), "items": _obj({"bad": {"type": "boolean"}})},
            "opt": {**_good(), "anyOf": [{"$ref": "#/$defs/Inner"}, {"type": "null"}]},
        },
        "$defs": {"Inner": _obj({"x": {"type": "boolean"}})},
    }
    paths = {i.path for i in lint_schema_help(schema, path="node-types/agent")}
    assert paths == {
        "node-types/agent/properties/rows/items/properties/bad",
        "node-types/agent/$defs/Inner/properties/x",
    }


def test_roots_limit_to_reference_closure() -> None:
    schema = {
        "$defs": {
            "Form": _obj({"inner": {**_good(), "$ref": "#/$defs/Inner"}}),
            "Inner": _obj({"ok": _good()}),
            "Response": _obj({"raw": {"type": "string"}}),
        }
    }
    assert lint_schema_help(schema, roots=["Form"]) == []
    assert _rules(lint_schema_help(schema, roots=["Response"])) == [
        "missing-description",
        "missing-example",
        "missing-tier",
        "missing-title",
    ]


def test_rules_data_and_jargon_patterns_load() -> None:
    data = schema_help_rules_data()
    assert data["max_description_length"] == 100
    assert data["when_required_tiers"] == ["basic"]
    assert data["severity"]["by_rule"]["hard-term"] == "warning"
    assert {t["id"] for t in data["hard_terms"]} >= {"layer", "sdk", "hook", "mcp"}
    ids = [r["id"] for r in data["jargon"]]
    assert ids
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------- 계약 데이터(수용 기준)


def test_contract_form_models_have_complete_help() -> None:
    issues = lint_contract_help()
    assert issues == [], "\n".join(f"{i.rule} {i.path} {i.message}" for i in issues)


def test_form_model_descriptions_are_user_words() -> None:
    """모델 설명은 폼 머리말로 보인다: 내부 클래스 이름·필드 경로가 없다."""
    defs = build_schema()["$defs"]
    agent_defaults = defs["AgentDefaults"]["description"]
    assert "WorkspaceSettings" not in agent_defaults
    assert "AgentSettings" not in agent_defaults
    assert "`" not in agent_defaults
    editor = defs["EditorSettings"]["properties"]
    for key in ("default_edge_shape", "default_direction"):
        assert "연결선이 노드를 피해 감" in editor[key]["description"], key


def test_form_roots_are_definition_models_not_api_dtos() -> None:
    roots = set(contract_form_roots())
    assert {"Agent", "Graph", "Resource", "Project", "WorkspaceSettings"} <= roots
    assert not roots & {"ErrorResponse", "ResourceSummary", "NodeTypeDescriptor", "ProjectUpdate"}


def _tiers(model: str) -> dict[str, str]:
    props = build_schema()["$defs"][model]["properties"]
    return {k: v[X_UI][XUiKeys.TIER] for k, v in props.items() if X_UI in v}


def _basic(model: str) -> set[str]:
    return {k for k, t in _tiers(model).items() if t == "basic"}


def test_agent_form_basic_fields_follow_table() -> None:
    assert _basic("Agent") == {
        "name",
        "role",
        "description",
        "system_prompt",
        "model",
        "resources",
        "project",
    }
    tiers = _tiers("Agent")
    for advanced in ("backend", "tools", "disallowed_tools", "limits", "working_directory"):
        assert tiers[advanced] == "advanced", advanced
    assert all(t in X_UI_TIERS for t in tiers.values())


def test_team_settings_are_all_advanced_with_groups() -> None:
    props = build_schema()["$defs"]["GraphSettings"]["properties"]
    assert {v[X_UI][XUiKeys.TIER] for v in props.values()} == {"advanced"}
    assert props["model"][X_UI][XUiKeys.GROUP] == "agent"
    assert props["model"][X_UI][XUiKeys.GROUP_TITLE] == "에이전트 기본값"
    assert props["chat"][X_UI][XUiKeys.GROUP] == "chat"
    # 에이전트 폼(같은 필드 정의)은 바뀌지 않는다
    assert _tiers("AgentSettings")["model"] == "basic"


def test_settings_sections_follow_table() -> None:
    assert _basic("ChatSettings") == {"reply_display", "send_key", "title"}
    assert _basic("EditorSettings") == set()
    assert _basic("InteractionSettings") == {"timeout_seconds"}
    assert _basic("NotificationSettings") == {"enabled", "sound"}
    assert _basic("UsageIndicatorSettings") == {"enabled", "placement", "value_mode"}
    assert _basic("LogSettings") == {"sources"}
    assert _basic("Resource") == {"type", "name", "description", "config", "content", "project"}
    assert _basic("EdgeSpec") == {"kind", "label", "config"}


def test_basic_fields_say_when_in_user_words() -> None:
    props = build_schema()["$defs"]["AgentSettings"]["properties"]
    assert props["model"][X_UI][XUiKeys.WHEN].endswith("세요.")
    for name in ("backend", "model", "system_prompt", "limits", "resources"):
        assert "층" not in props[name]["description"], name


def test_units_and_examples_reach_schema() -> None:
    defs = build_schema()["$defs"]
    timeout = defs["InteractionSettings"]["properties"]["timeout_seconds"][X_UI]
    assert timeout[XUiKeys.UNIT] == "초"
    assert timeout[XUiKeys.EXAMPLE] == 600
    prompt = defs["AgentSettings"]["properties"]["prompt_template"][X_UI]
    assert prompt[XUiKeys.GROUP] == "prompt"
    assert "{inputs}" in prompt[XUiKeys.EXAMPLE]


def test_agent_defaults_promote_backend_without_changing_agent_form() -> None:
    defs = build_schema()["$defs"]
    assert defs["WorkspaceSettings"]["properties"]["agent_defaults"]["$ref"].endswith(
        "/AgentDefaults"
    )
    backend = defs["AgentDefaults"]["properties"]["backend"][X_UI]
    assert backend[XUiKeys.TIER] == "basic"
    assert backend[XUiKeys.WHEN].endswith("세요.")
    assert _tiers("AgentSettings")["backend"] == "advanced"
    assert _tiers("Agent")["backend"] == "advanced"
    assert _tiers("GraphSettings")["backend"] == "advanced"
    assert set(defs["AgentDefaults"]["properties"]) == set(defs["AgentSettings"]["properties"])


def test_workspace_settings_accept_agent_settings_and_keep_unset() -> None:
    from agent_console_contracts import AgentDefaults, AgentSettings, WorkspaceSettings

    ws = WorkspaceSettings.model_validate({"agent_defaults": AgentSettings(model="m")})
    assert isinstance(ws.agent_defaults, AgentDefaults)
    assert ws.agent_defaults.model_dump(exclude_unset=True) == {"model": "m"}
    raw = {"agent_defaults": {"backend": "b", "custom": 1}}
    again = WorkspaceSettings.model_validate(raw)
    assert again.model_dump(exclude_unset=True)["agent_defaults"] == {"backend": "b", "custom": 1}
