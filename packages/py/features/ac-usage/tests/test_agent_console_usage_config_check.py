"""출처 설정 검증(`source_config_issues`·`config_error`·`UsageService.config_issues`)."""

from __future__ import annotations

import json
from typing import Any

from agent_console_contracts import (
    UsageSettings,
    UsageSourceDescriptor,
    UsageSourceSetting,
    UsageWindowSnapshot,
)
from agent_console_usage import (
    SOURCE_CONFIG_INVALID,
    SOURCE_SCHEMA_INVALID,
    UsageService,
    UsageSourceContext,
    config_error,
    new_usage_sources,
    source_config_issues,
)

NOW = 1_800_000_000.0

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "budgets": {
            "type": "object",
            "additionalProperties": {"type": "integer", "exclusiveMinimum": 0},
        }
    },
    "additionalProperties": False,
}


class Source:
    def __init__(self, schema: dict[str, Any] = SCHEMA) -> None:
        self.descriptor = UsageSourceDescriptor(
            id="budgeted",
            title="t",
            trust="estimated",
            config_schema=schema,
            auto_enable=True,
        )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        return [UsageWindowSnapshot(source=ctx.source_id, window="w", observed_at=ctx.now)]


def _settings(*items: tuple[str, dict[str, Any]], enabled: bool = True) -> UsageSettings:
    return UsageSettings(
        sources=[UsageSourceSetting(id=i, config=c, enabled=enabled) for i, c in items]
    )


DESCRIPTORS = {"budgeted": Source().descriptor}


def test_bad_value_reports_pointer_without_value() -> None:
    issues = source_config_issues(
        _settings(("other", {}), ("budgeted", {"budgets": {"five/h": -5}})), DESCRIPTORS
    )
    [issue] = issues
    assert issue.severity == "error"
    assert issue.code == SOURCE_CONFIG_INVALID
    assert issue.path == "/usage/sources/1/config/budgets/five~1h"
    assert issue.details == {"source": "budgeted", "validator": "exclusiveMinimum"}
    assert "-5" not in json.dumps(issue.model_dump(mode="json"))


def test_unknown_key_reports_object_path() -> None:
    [issue] = source_config_issues(_settings(("budgeted", {"secret-ish": "zz9"})), DESCRIPTORS)
    assert issue.path == "/usage/sources/0/config"
    assert issue.details["validator"] == "additionalProperties"
    assert "zz9" not in issue.message
    assert "secret-ish" not in issue.message


def test_valid_and_unknown_source_pass() -> None:
    settings = _settings(("budgeted", {"budgets": {"w": 10}}), ("absent", {"anything": -1}))
    assert source_config_issues(settings, DESCRIPTORS) == []


def test_base_path_and_severity_are_arguments() -> None:
    [issue] = source_config_issues(
        _settings(("budgeted", {"x": 1})), DESCRIPTORS, base_path="", severity="warning"
    )
    assert issue.path == "/0/config"
    assert issue.severity == "warning"


def test_broken_source_schema_is_not_a_user_issue() -> None:
    broken = {"budgeted": Source({"type": "no-such-type"}).descriptor}
    assert source_config_issues(_settings(("budgeted", {})), broken) == []
    error = config_error({}, {"type": "no-such-type"})
    assert error is not None
    assert error.code == SOURCE_SCHEMA_INVALID


def test_config_error_shape() -> None:
    assert config_error({"budgets": {"w": 1}}, SCHEMA) is None
    assert config_error({"x": 1}, None) is None
    error = config_error({"budgets": {"w": 0}}, SCHEMA)
    assert error is not None
    assert error.details == {"path": ["budgets", "w"], "validator": "exclusiveMinimum"}


def _service() -> UsageService:
    reg = new_usage_sources()
    reg.register("budgeted", Source())
    return UsageService(reg, clock=lambda: NOW, extra_sources={"runtime": Source()})


def test_service_config_issues_covers_registry_and_runtime_sources() -> None:
    service = _service()
    bad = _settings(("budgeted", {"x": 1}), ("runtime", {"budgets": {"w": -1}}), ("gone", {"x": 1}))
    issues = service.config_issues(bad)
    assert [i.details["source"] for i in issues] == ["budgeted", "runtime"]
    assert service.config_issues(None) == []


async def test_sources_shows_config_error_before_collect_and_clears_after_fix() -> None:
    service = _service()
    bad = _settings(("budgeted", {"budgets": {"w": -1}}))
    [info] = [s for s in service.sources(bad) if s.descriptor.id == "budgeted"]
    assert info.error is not None
    assert info.error.details["path"] == ["budgets", "w"]
    assert await service.collect(bad) == [
        UsageWindowSnapshot(source="runtime", window="w", observed_at=NOW)
    ]
    good = _settings(("budgeted", {"budgets": {"w": 1}}))
    [info] = [s for s in service.sources(good) if s.descriptor.id == "budgeted"]
    assert info.error is None
    # 꺼진 출처는 설정 오류를 보이지 않는다
    off = _settings(("budgeted", {"budgets": {"w": -1}}), enabled=False)
    [info] = [s for s in _service().sources(off) if s.descriptor.id == "budgeted"]
    assert info.error is None


async def test_broken_schema_fails_only_that_source() -> None:
    reg = new_usage_sources()
    reg.register("broken", Source({"type": "no-such-type"}))
    reg.register("ok", Source({}))
    service = UsageService(reg, clock=lambda: NOW)
    windows = await service.collect()
    assert [w.source for w in windows] == ["ok"]
    by_id = {s.descriptor.id: s for s in service.sources()}
    assert by_id["broken"].error is not None
    assert by_id["broken"].error.code == SOURCE_SCHEMA_INVALID
