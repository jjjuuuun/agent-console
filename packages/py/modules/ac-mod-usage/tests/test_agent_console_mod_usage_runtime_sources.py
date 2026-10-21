"""mod-usage 선택 multi 포트 ``usage.sources``(런타임 출처, design §4R.8)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import UsageSourceDescriptor, UsageWindowSnapshot
from agent_console_mod_usage import (
    SERVER_WARNINGS,
    SOURCE_CONFLICT,
    USAGE_SERVICE,
    USAGE_SOURCES,
    module,
    runtime_usage_sources,
)
from agent_console_modkit import BaseServices, ModulesConfig, PortKey, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_usage import FakeUsageSource, UsageSource, UsageSourceContext, as_usage_source

FIXED = datetime(2026, 10, 17, tzinfo=UTC)


class RuntimeSource:
    def __init__(self, source_id: str, window: str) -> None:
        self.descriptor = UsageSourceDescriptor(
            id=source_id, title=window, trust="estimated", auto_enable=True
        )
        self.window = window

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        return [UsageWindowSnapshot(source=ctx.source_id, window=self.window, observed_at=ctx.now)]


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


# 연동 모듈 쪽 선언(모양만 맞춘다 — mod-usage의 ports를 import하지 않는 것과 같다)
LINK_SOURCES: PortKey[Any] = PortKey("usage.sources", "런타임 사용량 출처", multi=True)
LINK_NEEDS_SERVICE: PortKey[Any] = PortKey("usage.service", "사용량 서비스")


def _link(module_id: str, *sources: Any) -> Any:
    """``usage.service``를 필수로 받고 ``usage.sources``를 주는 연동(선택 포트 순환을 만든다)."""

    def build(ctx: Any) -> None:
        for source in sources:
            ctx.provide(LINK_SOURCES, source)

    return fake_module(
        module_id,
        kind="link",
        provides=[LINK_SOURCES],
        requires=[LINK_NEEDS_SERVICE],
        on_build=build,
    )


def test_port_is_optional_multi() -> None:
    assert USAGE_SOURCES.multi
    assert USAGE_SOURCES.name in {p.name for p in module.descriptor.optional}
    assert SERVER_WARNINGS.name in {p.name for p in module.descriptor.provides}


def test_runtime_source_from_later_link_is_listed_and_collected() -> None:
    assembly = assemble([module, _link("link-x", RuntimeSource("local-x", "w"))], base=_base())
    assert assembly.status("link-x") is not None
    service = assembly.port(USAGE_SERVICE)
    assert service is not None
    assert [s.descriptor.id for s in service.sources()] == ["fake", "local-x"]
    report = asyncio.run(service.report(["windows"]))
    assert report.windows is not None
    assert [(w.source, w.window) for w in report.windows] == [("local-x", "w")]


def test_link_off_means_source_absent() -> None:
    link = _link("link-x", RuntimeSource("local-x", "w"))
    assembly = assemble([module, link], ModulesConfig(disabled=["link-x"]), base=_base())
    service = assembly.port(USAGE_SERVICE)
    assert service is not None
    assert [s.descriptor.id for s in service.sources()] == ["fake"]
    warnings = assembly.ports(SERVER_WARNINGS)
    assert [w() for w in warnings] == [[]]


def test_conflicts_keep_registry_and_first_runtime_source_and_warn() -> None:
    assembly = assemble(
        [
            module,
            _link("link-a", RuntimeSource("fake", "shadowed"), RuntimeSource("dup", "first")),
            _link("link-b", RuntimeSource("dup", "second")),
        ],
        base=_base(),
    )
    service = assembly.port(USAGE_SERVICE)
    assert service is not None
    infos = service.sources()
    assert [i.descriptor.id for i in infos] == ["fake", "dup"]
    assert infos[0].descriptor.title == FakeUsageSource().descriptor.title
    assert infos[1].descriptor.title == "first"
    issues = [issue for provider in assembly.ports(SERVER_WARNINGS) for issue in provider()]
    assert [(i.code, i.details["source"]) for i in issues] == [
        (SOURCE_CONFLICT, "dup"),
        (SOURCE_CONFLICT, "fake"),
    ]


def test_runtime_usage_sources_skips_non_sources() -> None:
    found, duplicates = runtime_usage_sources(
        [RuntimeSource("a", "w"), object(), RuntimeSource("a", "v")]
    )
    assert list(found) == ["a"]
    assert duplicates == ["a"]


def test_http_sources_route_lists_runtime_source() -> None:
    assembly = assemble([module, _link("link-x", RuntimeSource("local-x", "w"))], base=_base())
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        body = client.get("/api/v1/usage/sources").json()
    assert [s["descriptor"]["id"] for s in body] == ["fake", "local-x"]
    assert body[1]["descriptor"]["trust"] == "estimated"
