"""호스트 확장 지점 기여(3R.16): 실행 레지스트리 묶음 공장과 실행 플러그인 로더."""

from __future__ import annotations

from typing import Any

from agent_console_contracts import EdgeTypeDescriptor
from agent_console_mod_runs.plugins import (
    CONDITION_OPERATORS_REPORT_GROUP,
    RUNTIME_REPORT_GROUP,
    bind_redactor,
    create_registries,
    load_plugins,
)
from agent_console_modkit import ExtensionRegistries, PluginLoadContext
from agent_console_runtime import SECRET_PROVIDERS_GROUP, Registries
from agent_console_runtime.testing import make_registries


def test_create_registries_is_runtime_bundle() -> None:
    assert isinstance(create_registries(), Registries)


def test_load_plugins_reports_runtime_and_secret_groups() -> None:
    registries = create_registries()
    reports = load_plugins(PluginLoadContext(registries=registries))
    assert {g for g, _ in reports} <= {
        RUNTIME_REPORT_GROUP,
        SECRET_PROVIDERS_GROUP,
        CONDITION_OPERATORS_REPORT_GROUP,
    }
    assert all(r.ok for _, r in reports)
    loaded = {r.key for _, r in reports if r.status == "loaded"}
    registered = {e.key for reg in registries.all() for e in reg.list()}
    assert loaded <= registered


def test_enabled_empty_skips_everything() -> None:
    reports = load_plugins(PluginLoadContext(registries=create_registries(), enabled=frozenset()))
    assert all(r.status == "skipped" for _, r in reports)


def test_other_bundle_is_a_failed_report() -> None:
    [(group, report)] = load_plugins(PluginLoadContext(registries=ExtensionRegistries()))
    assert (group, report.status) == (RUNTIME_REPORT_GROUP, "failed")


class _Consumer:
    """가림 함수를 받는 임의 이름 연결 종류(``RedactorConsumer``)."""

    descriptor = EdgeTypeDescriptor(id="zz.edge", title="근거", scheduling="flow")

    def __init__(self) -> None:
        self.got: list[Any] = []

    def use_redactor(self, redact: Any) -> None:
        self.got.append(redact)

    def activates(self, source: Any, edge: Any) -> None:
        return None


def test_bind_redactor_reaches_only_consumers_by_capability() -> None:
    """5.2R.43: 종류 이름이 아니라 능력(``RedactorConsumer``)으로 고른다."""
    registries = make_registries()  # 엔진 테스트 종류(가림 함수를 받지 않음)
    edge = _Consumer()
    registries.edge_types.register("zz.edge", edge)
    redact = str.upper
    assert bind_redactor(registries, redact) == 1
    assert edge.got == [redact]
    assert bind_redactor(registries, None) == 1
    assert edge.got[-1] is None
