"""assemble: 위상 정렬·상태 5종·bindings·multi 목록·실패 격리(가짜 모듈 3개 이상)."""

from __future__ import annotations

import asyncio
import importlib.metadata
from typing import Any

import pytest
from pydantic import BaseModel

from agent_console_modkit import (
    BaseServices,
    ModuleContext,
    ModuleParts,
    ModulesConfig,
    ModuleState,
    PortKey,
    Topic,
    assemble,
    load_installed_modules,
)
from agent_console_modkit.testing import FakeModule, fake_module

STORE = PortKey[str]("definitions.store")
LAUNCHER = PortKey[str]("chat.turn_launcher")
CHECKS = PortKey[str]("definitions.checks", multi=True)


def three() -> tuple[FakeModule, FakeModule, FakeModule]:
    """definitions(포트 제공)·chat(필수 store, 선택 launcher)·link(launcher 제공, store 필수)."""
    definitions = fake_module("mod-definitions", provides=[STORE], optional=[CHECKS])
    chat = fake_module("mod-chat", requires=[STORE], optional=[LAUNCHER])
    link = fake_module("link-chat-runs", kind="link", provides=[LAUNCHER, CHECKS], requires=[STORE])
    return definitions, chat, link


def states(assembly: Any) -> dict[str, str]:
    return {r.id: r.state.value for r in assembly.report}


def test_topological_order_and_ports() -> None:
    definitions, chat, link = three()
    assembly = assemble([chat, link, definitions])
    assert states(assembly) == {
        "link-chat-runs": "active",
        "mod-chat": "active",
        "mod-definitions": "active",
    }
    order = assembly.order
    # 제공자가 소비자보다 먼저(선택 포트 포함): definitions → link → chat
    assert order.index("link-chat-runs") < order.index("mod-chat")
    assert order.index("mod-definitions") < order.index("link-chat-runs")
    assert order == ["mod-definitions", "link-chat-runs", "mod-chat"]
    chat_ctx = chat.contexts[0]
    assert chat_ctx.port(STORE) == "mod-definitions/definitions.store"
    assert chat_ctx.port(LAUNCHER) == "link-chat-runs/chat.turn_launcher"
    assert assembly.port(STORE) == "mod-definitions/definitions.store"
    assert assembly.provided_ports()["chat.turn_launcher"] == ["link-chat-runs"]


def test_optional_cycle_is_broken_definitions_reads_checks_after() -> None:
    # definitions는 선택 포트 CHECKS를 link에서, link는 store를 definitions에서 받는다(선택 순환).
    seen_at_build: list[list[str]] = []

    def definitions_build(ctx: ModuleContext) -> ModuleParts:
        seen_at_build.append(ctx.ports(CHECKS))
        ctx.provide(STORE, "store")
        return ModuleParts()

    definitions = fake_module(
        "mod-definitions", provides=[STORE], optional=[CHECKS], on_build=definitions_build
    )
    # chat은 순환 밖이라 선택 포트 간선(chat → zlink)이 남는다(id 순이면 chat이 먼저였을 것).
    chat = fake_module("mod-chat", requires=[STORE], optional=[LAUNCHER])
    link = fake_module("zlink", kind="link", provides=[LAUNCHER, CHECKS], requires=[STORE])
    assembly = assemble([definitions, chat, link])
    assert all(r.active for r in assembly.report)
    assert assembly.order == ["mod-definitions", "zlink", "mod-chat"]
    # 순환 안의 선택 간선만 뺐으므로 definitions는 zlink보다 먼저 build되어 CHECKS가 아직 없다.
    assert seen_at_build == [[]]
    assert assembly.ports(CHECKS) == ["zlink/definitions.checks"]
    assert chat.contexts[0].port(LAUNCHER) == "zlink/chat.turn_launcher"


def test_disabled_makes_dependents_unsatisfied_with_missing_port() -> None:
    definitions, chat, link = three()
    assembly = assemble([definitions, chat, link], ModulesConfig(disabled=["mod-definitions"]))
    report = {r.id: r for r in assembly.report}
    assert report["mod-definitions"].state is ModuleState.DISABLED
    assert report["mod-chat"].state is ModuleState.UNSATISFIED
    assert report["mod-chat"].missing == ("definitions.store",)
    assert report["link-chat-runs"].missing == ("definitions.store",)
    assert assembly.parts == {}
    assert chat.contexts == []


def test_enabled_list_and_optional_port_missing_is_none() -> None:
    definitions, chat, link = three()
    assembly = assemble(
        [definitions, chat, link], ModulesConfig(enabled=["mod-definitions", "mod-chat"])
    )
    assert states(assembly)["link-chat-runs"] == "disabled"
    assert assembly.status("link-chat-runs").reason == "modules.enabled에 없음"  # type: ignore[union-attr]
    assert chat.contexts[0].port(LAUNCHER) is None  # 선택 포트 없음 → 그 부분만 끔


def test_conflict_reports_both_and_bindings_choose() -> None:
    a = fake_module("mod-a", provides=[STORE])
    b = fake_module("mod-b", provides=[STORE])
    consumer = fake_module("mod-c", requires=[STORE])
    assembly = assemble([a, b, consumer])
    report = {r.id: r for r in assembly.report}
    assert report["mod-a"].state is ModuleState.CONFLICT
    assert report["mod-b"].conflicts == ("definitions.store",)
    assert "modules.bindings" in (report["mod-b"].reason or "")
    assert report["mod-c"].state is ModuleState.UNSATISFIED
    assert assembly.port(STORE) is None

    bound = assemble(
        [fake_module("mod-a", provides=[STORE]), fake_module("mod-b", provides=[STORE]), consumer],
        ModulesConfig(bindings={"definitions.store": "mod-b"}),
    )
    assert states(bound) == {"mod-a": "active", "mod-b": "active", "mod-c": "active"}
    assert bound.port(STORE) == "mod-b/definitions.store"
    assert bound.provided_ports()["definitions.store"] == ["mod-b"]


def test_multi_port_collects_in_module_id_order_without_conflict() -> None:
    consumer = fake_module("mod-a", requires=[CHECKS])
    z = fake_module("link-z", provides=[CHECKS])
    b = fake_module("link-b", provides=[CHECKS])
    assembly = assemble([z, consumer, b])
    assert all(r.active for r in assembly.report)
    assert consumer.contexts[0].ports(CHECKS) == [
        "link-b/definitions.checks",
        "link-z/definitions.checks",
    ]
    with pytest.raises(TypeError):
        consumer.contexts[0].port(CHECKS)


def test_failed_build_is_isolated_and_hides_message() -> None:
    topic: Topic[str] = Topic("t")
    seen: list[str] = []

    def boom(ctx: ModuleContext) -> ModuleParts:
        ctx.subscribe(topic, seen.append)
        ctx.provide(STORE, "never")
        raise RuntimeError("secret detail sk-123")

    broken = fake_module("mod-definitions", provides=[STORE], on_build=boom)
    chat = fake_module("mod-chat", requires=[STORE])
    other = fake_module("mod-usage")
    base = BaseServices()
    assembly = assemble([broken, chat, other], base=base)
    report = {r.id: r for r in assembly.report}
    assert report["mod-definitions"].state is ModuleState.FAILED
    assert report["mod-definitions"].reason == "build 실패(RuntimeError)"
    assert "sk-123" not in str(assembly.report)
    assert report["mod-chat"].state is ModuleState.UNSATISFIED
    assert report["mod-usage"].state is ModuleState.ACTIVE
    # 실패한 모듈의 구독·제공은 되돌린다
    assert base.events.subscriber_count(topic) == 0
    assert assembly.port(STORE) is None


def test_settings_are_validated_per_module() -> None:
    class Opts(BaseModel):
        retention: int = 10

    good = fake_module("mod-usage", settings_schema=Opts)
    assemble([good], ModulesConfig(options={"mod-usage": {"retention": 5}}))
    settings = good.contexts[0].settings
    assert isinstance(settings, Opts)
    assert settings.retention == 5

    bad = fake_module("mod-usage", settings_schema=Opts)
    failed = assemble([bad], ModulesConfig(options={"mod-usage": {"retention": "x"}}))
    assert failed.report[0].state is ModuleState.FAILED
    assert failed.report[0].reason == "설정 검증 실패: retention"
    assert "x" not in (failed.report[0].reason or "").replace("retention", "")


def test_duplicate_module_ids_conflict() -> None:
    assembly = assemble([fake_module("mod-a"), fake_module("mod-a"), fake_module("mod-b")])
    assert [r.state.value for r in assembly.report] == ["conflict", "conflict", "active"]


def test_required_cycle_is_unsatisfied() -> None:
    x = PortKey[str]("x")
    y = PortKey[str]("y")
    a = fake_module("mod-a", provides=[x], requires=[y])
    b = fake_module("mod-b", provides=[y], requires=[x])
    c = fake_module("mod-c")
    assembly = assemble([a, b, c])
    report = {r.id: r for r in assembly.report}
    assert report["mod-a"].state is ModuleState.UNSATISFIED
    assert "cycle" in (report["mod-b"].reason or "")
    assert report["mod-c"].active


def test_undeclared_port_access_fails_the_module() -> None:
    def sneaky(ctx: ModuleContext) -> ModuleParts:
        ctx.port(STORE)  # requires·optional에 없음
        return ModuleParts()

    provider = fake_module("mod-definitions", provides=[STORE])
    assembly = assemble([provider, fake_module("mod-x", on_build=sneaky)])
    assert assembly.status("mod-x").reason == "build 실패(UndeclaredPortError)"  # type: ignore[union-attr]

    def provides_undeclared(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(STORE, "x")
        return ModuleParts()

    other = assemble([fake_module("mod-y", on_build=provides_undeclared)])
    assert other.report[0].state is ModuleState.FAILED


def test_ws_topic_key_clash_fails_later_module() -> None:
    async def handler(_: Any) -> None:
        return None

    def with_topic(ctx: ModuleContext) -> ModuleParts:
        return ModuleParts(ws_topics={"run:": handler})

    assembly = assemble(
        [fake_module("mod-a", on_build=with_topic), fake_module("mod-b", on_build=with_topic)]
    )
    assert states(assembly) == {"mod-a": "active", "mod-b": "failed"}
    assert "run:(mod-a)" in (assembly.status("mod-b").reason or "")  # type: ignore[union-attr]
    assert list(assembly.ws_topics()) == ["run:"]


def test_build_must_return_module_parts() -> None:
    class Bad:
        descriptor = fake_module("mod-bad").descriptor

        def build(self, ctx: ModuleContext) -> ModuleParts:
            return "nope"  # type: ignore[return-value]

    assembly = assemble([Bad()])
    assert assembly.report[0].reason == "build 실패(TypeError)"


def test_warnings_for_unknown_ids_and_bad_bindings() -> None:
    assembly = assemble(
        [fake_module("mod-a", provides=[STORE])],
        ModulesConfig(
            disabled=["mod-zzz"],
            bindings={"definitions.store": "mod-nope"},
            options={"mod-a": {"x": 1}},
        ),
    )
    text = " | ".join(assembly.warnings)
    assert "mod-zzz" in text
    assert "mod-nope" in text
    assert "설정을 받지 않습니다" in text
    assert assembly.report[0].active


async def test_start_stop_order_background_and_startup_failure() -> None:
    calls: list[str] = []
    gate = asyncio.Event()

    def parts_for(name: str, *, fail: bool = False) -> Any:
        async def start() -> None:
            calls.append(f"start {name}")
            if fail:
                raise RuntimeError("x")

        async def stop() -> None:
            calls.append(f"stop {name}")

        async def loop() -> None:
            calls.append(f"bg {name}")
            gate.set()
            await asyncio.sleep(3600)

        def build(ctx: ModuleContext) -> ModuleParts:
            if name == "mod-chat":
                ctx.port(STORE)
            else:
                ctx.provide(STORE, "s")
            return ModuleParts(startup=[start], shutdown=[stop], background=[loop])

        return build

    assembly = assemble(
        [
            fake_module("mod-chat", requires=[STORE], on_build=parts_for("mod-chat", fail=True)),
            fake_module("mod-definitions", provides=[STORE], on_build=parts_for("mod-definitions")),
        ]
    )
    await assembly.start()
    await asyncio.wait_for(gate.wait(), 5)
    assert calls[:2] == ["start mod-definitions", "start mod-chat"]
    assert assembly.status("mod-chat").state is ModuleState.FAILED  # type: ignore[union-attr]
    assert assembly.status("mod-chat").reason == "시작 실패(RuntimeError)"  # type: ignore[union-attr]
    await assembly.stop()
    assert "bg mod-chat" not in calls
    assert calls[-2:] == ["stop mod-chat", "stop mod-definitions"]  # 역순


def test_load_installed_modules_from_entry_points() -> None:
    eps = [
        importlib.metadata.EntryPoint(
            "echo", "agent_console_modkit.testing:echo_module", "agent_console.server_modules"
        ),
        importlib.metadata.EntryPoint(
            "cls", "agent_console_modkit.testing:EchoModule", "agent_console.server_modules"
        ),
        importlib.metadata.EntryPoint(
            "bad", "agent_console_modkit.testing:ECHO_SAID", "agent_console.server_modules"
        ),
    ]
    modules, reports = load_installed_modules(entry_points=eps)
    assert [m.descriptor.id for m in modules] == ["echo", "echo"]
    by_key = {r.key: r.status for r in reports}
    assert by_key == {"bad": "failed", "cls": "loaded", "echo": "loaded"}
