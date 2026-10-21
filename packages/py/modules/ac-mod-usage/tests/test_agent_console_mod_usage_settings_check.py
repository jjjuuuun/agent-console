"""mod-usage가 주는 ``definitions.checks``(공통 설정 저장 전 출처 설정 검증)와 설정 오류 경고.

정의 모듈 없이 조립한다: 저장 쪽 대신 포트로 받은 검사를 직접 부르고, ``workspace.settings``는
가짜 모듈이 준다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from agent_console_contracts import (
    UsageSettings,
    UsageSourceDescriptor,
    UsageWindowSnapshot,
    WorkspaceSettings,
)
from agent_console_mod_usage import (
    DEFINITION_CHECKS,
    SERVER_WARNINGS,
    UsageSettingsCheck,
    module,
    usage_settings_of,
)
from agent_console_modkit import BaseServices, ModulesConfig, PortKey, assemble
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_usage import (
    SOURCE_CONFIG_INVALID,
    FakeUsageSource,
    UsageService,
    UsageSource,
    UsageSourceContext,
    as_usage_source,
)

FIXED = datetime(2026, 10, 18, tzinfo=UTC)
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


class Budgeted:
    def __init__(self, source_id: str) -> None:
        self.descriptor = UsageSourceDescriptor(
            id=source_id, title=source_id, trust="estimated", config_schema=SCHEMA
        )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        return []


class _Registries:
    def __init__(self) -> None:
        self.extensions: dict[str, Registry[Any]] = {}

    def extension(self, name: str, *, validator: Any = None) -> Registry[Any]:
        if name not in self.extensions:
            self.extensions[name] = Registry(name, validator=validator)
        return self.extensions[name]


def _base() -> BaseServices:
    regs = _Registries()
    sources: Registry[UsageSource] = regs.extension("usage_sources", validator=as_usage_source)
    sources.register("fake", FakeUsageSource())
    return BaseServices(clock=lambda: FIXED, registries=regs)


LINK_SOURCES: PortKey[Any] = PortKey("usage.sources", "런타임 사용량 출처", multi=True)
LINK_NEEDS_SERVICE: PortKey[Any] = PortKey("usage.service", "사용량 서비스")
SETTINGS_PORT: PortKey[Any] = PortKey("workspace.settings", "지금 워크스페이스 설정")


def _link() -> Any:
    return fake_module(
        "link-x",
        kind="link",
        provides=[LINK_SOURCES],
        requires=[LINK_NEEDS_SERVICE],
        on_build=lambda ctx: ctx.provide(LINK_SOURCES, Budgeted("local-x")),
    )


def _settings_module(document: dict[str, Any]) -> Any:
    current = WorkspaceSettings.model_validate(document)
    return fake_module(
        "defs-x",
        provides=[SETTINGS_PORT],
        on_build=lambda ctx: ctx.provide(SETTINGS_PORT, lambda: current),
    )


def _doc(*items: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return {"usage": {"sources": [{"id": i, "config": c} for i, c in items]}}


def _check(*extra: Any, config: ModulesConfig | None = None) -> Any:
    assembly = assemble([module, *extra], config, base=_base())
    [check] = assembly.ports(DEFINITION_CHECKS)
    return check


def test_module_provides_check() -> None:
    assert DEFINITION_CHECKS.name in {p.name for p in module.descriptor.provides}
    assert DEFINITION_CHECKS.multi


def test_registry_source_unknown_key_is_error() -> None:
    issues = list(_check().issues("settings", _doc(("fake", {"nope": 1}))))
    [issue] = issues
    assert issue.severity == "error"
    assert issue.code == SOURCE_CONFIG_INVALID
    assert issue.path == "/usage/sources/0/config"


def test_runtime_source_bad_budget_is_error_without_value() -> None:
    doc = _doc(("fake", {}), ("local-x", {"budgets": {"five": -5}}))
    [issue] = list(_check(_link()).issues("settings", doc))
    assert issue.path == "/usage/sources/1/config/budgets/five"
    assert issue.details == {"source": "local-x", "validator": "exclusiveMinimum"}
    assert "-5" not in json.dumps(issue.model_dump(mode="json"))


def test_valid_config_and_other_kinds_pass() -> None:
    check = _check(_link())
    assert list(check.issues("settings", _doc(("local-x", {"budgets": {"five": 5}})))) == []
    assert list(check.issues("agent", _doc(("local-x", {"budgets": {"five": -5}})))) == []
    assert list(check.issues("settings", {"usage": "not-an-object"})) == []
    assert list(check.issues("settings", {})) == []


def test_runtime_source_absent_is_not_checked() -> None:
    check = _check(_link(), config=ModulesConfig(disabled=["link-x"]))
    assert list(check.issues("settings", _doc(("local-x", {"budgets": {"five": -5}})))) == []


def test_check_accepts_model_document() -> None:
    reg: Registry[UsageSource] = Registry("usage_sources", validator=as_usage_source)
    reg.register("local-x", Budgeted("local-x"))
    check = UsageSettingsCheck(UsageService(reg, clock=lambda: 0.0))
    model = WorkspaceSettings.model_validate(_doc(("local-x", {"budgets": {"five": 0}})))
    [issue] = list(check.issues("settings", model))
    assert issue.path == "/usage/sources/0/config/budgets/five"
    assert usage_settings_of(object()) is None
    found = usage_settings_of(model)
    assert isinstance(found, UsageSettings)
    assert found.sources[0].id == "local-x"


def test_saved_bad_config_is_server_warning_when_source_present() -> None:
    bad = _doc(("local-x", {"budgets": {"five": -5}}))
    assembly = assemble([module, _link(), _settings_module(bad)], base=_base())
    issues = [i for provider in assembly.ports(SERVER_WARNINGS) for i in provider()]
    [warning] = [i for i in issues if i.code == SOURCE_CONFIG_INVALID]
    assert warning.severity == "warning"
    assert warning.path == "/usage/sources/0/config/budgets/five"

    off = assemble(
        [module, _link(), _settings_module(bad)],
        ModulesConfig(disabled=["link-x"]),
        base=_base(),
    )
    issues = [i for provider in off.ports(SERVER_WARNINGS) for i in provider()]
    assert [i for i in issues if i.code == SOURCE_CONFIG_INVALID] == []
