"""계약 memory 후속(5.7R.28): 설정 위젯 이름·기본 단계, 정리 계획 상세 필드, 조건 경로 제안."""

from __future__ import annotations

from typing import Any

from agent_console_contracts.memory import (
    MEMORY_RETENTION_CONDITION_WIDGET,
    MEMORY_RETENTION_RULES_WIDGET,
    MEMORY_RETENTION_SUBJECT_PATHS,
    MEMORY_SCOPE_KINDS_WIDGET,
    MemoryAccessConfig,
    MemoryRetentionCondition,
    MemoryRetentionPlan,
    MemoryRetentionPlanItem,
    MemoryRetentionRule,
    MemoryScopeRef,
    MemorySettings,
)
from agent_console_contracts.runs import ConditionSpec


def _xui(schema: dict[str, Any], key: str) -> dict[str, Any]:
    found: dict[str, Any] = schema["properties"][key].get("x-ui", {})
    return found


def test_settings_schema_names_widgets_and_basic_tiers() -> None:
    schema = MemorySettings.model_json_schema()
    assert (
        _xui(schema, "scope_kinds")["widget"] == MEMORY_SCOPE_KINDS_WIDGET == "memory-scope-kinds"
    )
    assert _xui(schema, "retention")["widget"] == MEMORY_RETENTION_RULES_WIDGET
    assert MEMORY_RETENTION_RULES_WIDGET == "memory-retention-rules"
    assert _xui(schema, "secrets")["tier"] == "basic"
    assert _xui(schema, "max_versions_per_entry")["tier"] == "basic"


def test_plan_item_detail_fields_are_optional_and_round_trip() -> None:
    scope = MemoryScopeRef(kind="notes", id="g")
    bare = MemoryRetentionPlanItem(
        entry_id="e", scope=scope, key="k", version=1, rule="r", action="archive"
    )
    assert (bare.updated_at, bare.bytes) == (None, None)
    full = bare.model_copy(update={"updated_at": 12.5, "bytes": 30})
    plan = MemoryRetentionPlan(items=[full], count=1, excluded_pinned=3)
    again = MemoryRetentionPlan.model_validate(plan.model_dump(mode="json"))
    assert again == plan
    assert MemoryRetentionPlan(count=0).excluded_pinned == 0


def test_retention_condition_is_condition_spec_with_path_examples() -> None:
    raw = {"all": [{"path": "/tags", "op": "contains", "value": "tmp"}], "negate": False}
    rule = MemoryRetentionRule.model_validate({"id": "r", "when": raw})
    assert isinstance(rule.when, MemoryRetentionCondition)
    assert isinstance(rule.when, ConditionSpec)
    assert rule.model_dump(mode="json", exclude_unset=True)["when"] == raw
    schema = MemoryRetentionRule.model_json_schema()
    assert schema["properties"]["when"]["x-ui"]["widget"] == MEMORY_RETENTION_CONDITION_WIDGET
    item = schema["$defs"]["MemoryRetentionConditionItem"]["properties"]["path"]
    assert item["examples"] == list(MEMORY_RETENTION_SUBJECT_PATHS)
    # 연결 조건(공용 ConditionItem)에는 정리 경로 제안이 새지 않는다.
    shared = ConditionSpec.model_json_schema()["$defs"]["ConditionItem"]["properties"]["path"]
    assert "examples" not in shared


def test_access_ops_array_carries_enum_labels() -> None:
    schema = MemoryAccessConfig.model_json_schema()
    access = schema["$defs"]["MemoryScopeAccess"]["properties"]["access"]
    assert set(access["x-ui"]["enum_labels"]) == set(access["items"]["enum"])
