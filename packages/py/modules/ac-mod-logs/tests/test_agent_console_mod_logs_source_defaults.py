"""mod-logs ``logs.source_defaults``(5.2R.27): 다른 모듈이 정한 출처 기본 켜기.

설정에 ``enabled``가 없는 출처에만 적용하고, 사용자가 적은 값(끔 포함)이 이긴다.
설정 원본은 그대로다.
출처는 ac-logs 기본 플러그인 ``normalized-v1``(디스크립터 기본 꺼짐)만 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_contracts.logs import LogSettings
from agent_console_mod_logs import (
    SOURCE_DEFAULTS,
    apply_source_defaults,
    collect_source_defaults,
    module,
)
from agent_console_mod_logs.testing import static_settings_module
from agent_console_modkit import (
    BaseServices,
    Module,
    ModuleContext,
    ModuleParts,
    ModulesConfig,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module

TOKEN = "t" * 32
SOURCE = "normalized-v1"
QUIET = {"startup_scan": False, "scan_interval_seconds": 0}


def _defaults_module(value: Callable[[], Mapping[str, bool]]) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(SOURCE_DEFAULTS, value)
        return ModuleParts()

    return fake_module("defaults-provider", kind="link", provides=[SOURCE_DEFAULTS], on_build=build)


def _enabled(settings: WorkspaceSettings, *extra: Module) -> bool:
    base = BaseServices(clock=lambda: datetime(2027, 1, 1, tzinfo=UTC))
    assembly = assemble(
        [module, static_settings_module(settings), *extra],
        ModulesConfig(options={"mod-logs": QUIET}),
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        rows: list[dict[str, Any]] = client.get("/api/v1/logs/sources").json()
    [row] = [r for r in rows if r["descriptor"]["id"] == SOURCE]
    return bool(row["enabled"])


def test_apply_keeps_explicit_values_and_original() -> None:
    original = LogSettings.model_validate(
        {"sources": [{"id": "a", "enabled": False}, {"id": "b", "config": {"x": 1}}]}
    )
    out = apply_source_defaults(original, {"a": True, "b": True, "c": True})
    assert out is not None
    assert out is not original
    assert [(s.id, s.enabled, s.config) for s in out.sources or []] == [
        ("a", False, None),
        ("b", True, {"x": 1}),
        ("c", True, None),
    ]
    assert [s.enabled for s in original.sources or []] == [False, None]  # 원본은 그대로
    assert apply_source_defaults(None, {}) is None
    assert apply_source_defaults(original, {"a": True}) is original  # 바뀐 것이 없으면 그대로


def test_collect_skips_failing_provider() -> None:
    def broken() -> Mapping[str, bool]:
        raise RuntimeError("boom")

    assert collect_source_defaults([broken, lambda: {"x": True}]) == {"x": True}


def test_port_turns_on_source_without_explicit_setting() -> None:
    assert _enabled(WorkspaceSettings()) is False  # 디스크립터 기본 꺼짐
    assert _enabled(WorkspaceSettings(), _defaults_module(lambda: {SOURCE: True})) is True


def test_user_explicit_off_wins_over_port() -> None:
    settings = WorkspaceSettings.model_validate(
        {"logs": {"sources": [{"id": SOURCE, "enabled": False}]}}
    )
    assert _enabled(settings, _defaults_module(lambda: {SOURCE: True})) is False


def test_port_is_read_each_time() -> None:
    state = {"on": False}
    provider = _defaults_module(lambda: {SOURCE: True} if state["on"] else {})
    base = BaseServices(clock=lambda: datetime(2027, 1, 1, tzinfo=UTC))
    assembly = assemble(
        [module, static_settings_module(WorkspaceSettings()), provider],
        ModulesConfig(options={"mod-logs": QUIET}),
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN

        def enabled() -> bool:
            rows = client.get("/api/v1/logs/sources").json()
            return bool(next(r for r in rows if r["descriptor"]["id"] == SOURCE)["enabled"])

        assert enabled() is False
        state["on"] = True  # 예: 그 로그 폴더가 나중에 생김
        assert enabled() is True
