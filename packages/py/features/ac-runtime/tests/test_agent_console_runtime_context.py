"""NodeContext: 이벤트·라우팅 기록·서비스·비밀, 레지스트리 묶음·로딩, 이벤트 버스."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

import pytest

from agent_console_contracts import NodeTypeDescriptor
from agent_console_registry import load_plugins
from agent_console_runtime import (
    REDACTED,
    EnvSecretProvider,
    InMemoryEventBus,
    MissingServiceError,
    Registries,
    SecretNotFoundError,
    SecretResolver,
    ServiceKey,
    Services,
    as_node_type,
    load_registries,
    sum_usage,
)
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


async def test_reserved_event_types_are_rejected(h: Harness, b: Builders) -> None:
    run = await h.make().run(b.graph([b.node("a", forbidden=True)], [], entries=["a"]))
    nr = h.recorder.runs.list_node_runs(run.id)[0]
    assert nr.status == "failed"
    assert nr.error is not None
    assert "엔진 전용" in nr.error.message


async def test_secrets_are_resolved_and_redacted_in_events(h: Harness, b: Builders) -> None:
    secrets = SecretResolver([EnvSecretProvider({"API_KEY": "sk-very-secret"})])
    run = await h.make(secrets=secrets).run(
        b.graph([b.node("a", secret="secret://api_key")], [], entries=["a"])
    )
    ev = next(e for e in h.recorder.events.list(run.id) if e.type == "test.secret")
    assert ev.payload == {"value": REDACTED, "text": f"key={REDACTED}"}
    assert all("sk-very-secret" not in e.model_dump_json() for e in h.recorder.events.list(run.id))


async def test_missing_secret_fails_node_without_leaking(h: Harness, b: Builders) -> None:
    run = await h.make().run(b.graph([b.node("a", secret="secret://nope")], [], entries=["a"]))
    nr = h.recorder.runs.list_node_runs(run.id)[0]
    assert nr.status == "failed"
    assert nr.error is not None
    assert "nope" in nr.error.message


def test_secret_resolver_helpers() -> None:
    env = {"PFX_token": "abcd", "PFX_OTHER": "wxyz"}
    resolver = SecretResolver([EnvSecretProvider(env, prefix="PFX_")])
    assert resolver.resolve("secret://token") == "abcd"
    assert resolver.resolve("other") == "wxyz"
    assert resolver.resolve_refs({"a": ["secret://token", 1], "b": "plain"}) == {
        "a": ["abcd", 1],
        "b": "plain",
    }
    with pytest.raises(SecretNotFoundError) as info:
        resolver.resolve("secret://missing")
    assert "missing" in str(info.value)
    assert resolver.redact({"t": "abcd-wxyz"}) == {"t": f"{REDACTED}-{REDACTED}"}


def test_services_typed_lookup() -> None:
    key = ServiceKey[int]("n")
    other = ServiceKey[str]("s")
    services = Services({key: 3})
    assert services.get(key) == 3
    assert services.get(other) is None
    assert services.get(other, "d") == "d"
    with pytest.raises(MissingServiceError):
        services.require(other)
    more = services.with_(other, "x")
    assert more.require(other) == "x"
    assert other not in services
    assert other in more
    assert list(more.names()) == ["n", "s"]


async def test_per_run_services_override(h: Harness, b: Builders) -> None:
    rt = h.make(services=Services())
    await rt.run(b.graph([b.node("a")], [], entries=["a"]))
    assert h.probe.calls == []  # 기본 서비스에 probe 없음
    await rt.run(
        b.graph([b.node("a")], [], entries=["a"]), services=Services({b.probe_key: h.probe})
    )
    assert [c[0] for c in h.probe.calls] == ["a"]


def test_registries_extension_and_plugin_target() -> None:
    regs = Registries()
    classifiers = regs.extension("example_classifiers")
    assert regs.extension("example_classifiers") is classifiers

    class Plugin:
        @staticmethod
        def register(target: Registries) -> None:
            target.extension("example_classifiers").register("rule", object())

    import types

    module = types.ModuleType("fake_plugin_mod")
    module.plugin = Plugin  # type: ignore[attr-defined]
    reports = load_plugins(["fake_plugin_mod:plugin"], regs, import_module=lambda _n: module)
    assert reports[0].ok
    assert "rule" in classifiers


def test_load_registries_from_entry_points(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    module = types.ModuleType("ac_rt_test_plugin")
    module.Step = type(h.registries.node_types.get("t.step"))  # type: ignore[attr-defined]
    module.Flow = type(h.registries.edge_types.get("t.flow"))  # type: ignore[attr-defined]
    module.bad = object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ac_rt_test_plugin", module)
    eps = [
        EntryPoint("t.step", "ac_rt_test_plugin:Step", "agent_console.node_types"),
        EntryPoint("t.flow", "ac_rt_test_plugin:Flow", "agent_console.edge_types"),
        EntryPoint("bad", "ac_rt_test_plugin:bad", "agent_console.backends"),
        EntryPoint("other", "ac_rt_test_plugin:Step", "agent_console.unrelated"),
    ]
    regs = Registries()
    reports = load_registries(regs, entry_points=eps)
    assert [(r.key, r.status) for r in reports] == [
        ("t.step", "loaded"),
        ("t.flow", "loaded"),
        ("bad", "failed"),
    ]
    assert "t.step" in regs.node_types
    assert "t.flow" in regs.edge_types
    assert len(regs.backends) == 0
    # 엔트리 포인트를 빼면 그 타입은 없고, 엔진은 그대로 만들어진다.
    empty = Registries()
    assert load_registries(empty, entry_points=[]) == []
    assert len(empty.node_types) == 0


def test_as_node_type_rejects_non_node() -> None:
    with pytest.raises(TypeError):
        as_node_type(object())

    class Fake:
        descriptor = NodeTypeDescriptor(id="f", title="f", version=2)

        def resolve_ports(self, config: Any) -> Any: ...

        def validate(self, config: Any, ctx: Any) -> Any: ...

        async def execute(self, ctx: Any, inputs: Any) -> Any: ...

    assert isinstance(as_node_type(Fake), Fake)


def test_sum_usage() -> None:
    assert sum_usage([None, None]) is None


async def test_event_bus_subscriptions(h: Harness, b: Builders) -> None:
    bus = InMemoryEventBus()
    from agent_console_runtime import GraphRuntime

    rt = GraphRuntime(h.registries, h.recorder, bus, services=Services())
    sub_all = bus.subscribe()
    sub_nodes = bus.subscribe(accept=lambda e: e.type.startswith("node."))
    run = await rt.run(b.graph([b.node("a")], [], entries=["a"]), run_id="R")
    sub_other = bus.subscribe(run_id="other")
    assert bus.subscriber_count == 3
    sub_all.close()
    got = [e async for e in sub_all]
    assert got[0].type == "run.created"
    assert got[-1].type == "run.completed"
    assert all(e.run_id == run.id for e in got)
    sub_nodes.close()
    assert {e.type for e in [e async for e in sub_nodes]} <= {
        "node.queued",
        "node.started",
        "node.completed",
    }
    sub_other.close()
    assert await sub_other.get() is None
    assert bus.subscriber_count == 0
