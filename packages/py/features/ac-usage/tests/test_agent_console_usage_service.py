"""X13 로더·UsageService: 출처 이름을 모르고 데이터(설정)로만 동작, 값을 지어내지 않음."""

from __future__ import annotations

import asyncio
import builtins
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from agent_console_contracts import (
    ErrorCodes,
    KnownUsageTrust,
    RunEvent,
    TokenRollupRow,
    Usage,
    UsageSettings,
    UsageSourceDescriptor,
    UsageSourceSetting,
    UsageWindowSnapshot,
)
from agent_console_registry import Registry
from agent_console_usage import (
    SOURCE_FAILED,
    SOURCE_TIMEOUT,
    USAGE_SOURCES_GROUP,
    FakeUsageSource,
    UsageService,
    UsageSource,
    UsageSourceContext,
    as_usage_source,
    list_descriptors,
    load_usage_sources,
    new_usage_sources,
)

NOW = 1_800_000_000.0


def clock() -> float:
    return NOW


class PluginSource:
    """테스트 전용 출처: 처음 보는 창 이름·신뢰 등급. 주어진 값만 낸다."""

    descriptor = UsageSourceDescriptor(
        id="whatever-id",
        title="플러그인",
        trust="community",
        auto_enable=True,
        config_schema={
            "type": "object",
            "properties": {"ratio": {"type": "number"}},
            "additionalProperties": False,
        },
    )

    def __init__(self) -> None:
        self.contexts: list[UsageSourceContext] = []

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        self.contexts.append(ctx)
        return [
            UsageWindowSnapshot(
                source="wrong-name",  # 서비스가 레지스트리 key로 바로잡는다
                window="lunar_cycle",
                used_ratio=ctx.config.get("ratio"),
                observed_at=ctx.now - 1,
            ),
            UsageWindowSnapshot(
                source="x",
                window="old_window",
                used_ratio=0.9,
                resets_at=ctx.now - 1,
                observed_at=ctx.now - 7200,
            ),
        ]


class BrokenSource:
    descriptor = UsageSourceDescriptor(
        id="b", title="B", trust=KnownUsageTrust.UNOFFICIAL, auto_enable=True
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        raise RuntimeError("token=sk-secret-value leaked?")


class SlowSource:
    descriptor = UsageSourceDescriptor(
        id="s", title="S", trust=KnownUsageTrust.OBSERVED, auto_enable=True
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        await asyncio.sleep(5)
        return []


class Recorder:
    def __init__(self) -> None:
        self.recorded: list[UsageWindowSnapshot] = []
        self.pruned: list[float] = []

    def record(self, snapshot: UsageWindowSnapshot) -> None:
        self.recorded.append(snapshot)

    def prune(self, before: float) -> int:
        self.pruned.append(before)
        return 3


def _registry(**items: UsageSource) -> Registry[UsageSource]:
    reg = new_usage_sources()
    for key, item in items.items():
        reg.register(key, item)
    return reg


# ---------------------------------------------------------------- 로더


def test_loader_uses_entry_points_and_reports_failures() -> None:
    eps = [
        EntryPoint("fake", "agent_console_usage.sources.fake:FakeUsageSource", USAGE_SOURCES_GROUP),
        EntryPoint("bogus", "json:loads", USAGE_SOURCES_GROUP),
        EntryPoint("other", "json:dumps", "some.other.group"),
    ]
    reg = new_usage_sources()
    reports = load_usage_sources(reg, entry_points=eps)
    assert {(r.key, r.status) for r in reports} == {("fake", "loaded"), ("bogus", "failed")}
    assert [e.key for e in reg.list()] == ["fake"]


def test_installed_entry_points_register_defaults_and_can_be_filtered() -> None:
    reg = new_usage_sources()
    load_usage_sources(reg, enabled={"run-events", "statusline-file"})
    assert [e.key for e in reg.list()] == ["run-events", "statusline-file"]
    descs = list_descriptors(reg)
    assert [d.id for d in descs] == ["run-events", "statusline-file"]
    assert all(d.trust == KnownUsageTrust.OFFICIAL for d in descs)
    assert descs[1].docs_url
    assert descs[1].setup_help


def test_loader_modules_and_validation() -> None:
    reg = new_usage_sources()
    reports = load_usage_sources(
        reg, entry_points=[], modules=["mine=agent_console_usage.sources.fake:FakeUsageSource"]
    )
    assert [r.ok for r in reports] == [True]
    assert "mine" in reg
    with pytest.raises(TypeError):
        as_usage_source(object())


# ---------------------------------------------------------------- 서비스


async def test_unlisted_source_runs_with_key_as_id_and_drops_expired() -> None:
    plugin = PluginSource()
    rec = Recorder()
    service = UsageService(_registry(mine=plugin), clock=clock, observations=rec)
    snaps = await service.collect()
    assert [(s.source, s.window, s.used_ratio) for s in snaps] == [("mine", "lunar_cycle", None)]
    # 이력에는 그대로 남지만 현재 값에서는 초기화가 지난 창을 뺀다
    assert {s.window for s in rec.recorded} == {"lunar_cycle", "old_window"}
    assert all(s.source == "mine" for s in rec.recorded)
    (info,) = service.sources()
    assert info.descriptor.id == "mine"
    assert info.descriptor.trust == "community"
    assert info.enabled is True
    assert info.last_observed_at == NOW - 1
    assert info.error is None
    assert plugin.contexts[0].source_id == "mine"


async def test_settings_enable_config_and_disable() -> None:
    plugin = PluginSource()
    fake = FakeUsageSource()
    service = UsageService(_registry(mine=plugin, fake=fake), clock=clock)
    settings = UsageSettings(
        sources=[
            UsageSourceSetting(id="mine", config={"ratio": 0.25}),
            UsageSourceSetting(id="fake", enabled=False, config={"windows": [{"window": "w"}]}),
            UsageSourceSetting(id="not-installed"),
        ]
    )
    snaps = await service.collect(settings)
    assert [(s.source, s.window, s.used_ratio) for s in snaps] == [("mine", "lunar_cycle", 0.25)]
    infos = {i.descriptor.id: i for i in service.sources(settings)}
    assert set(infos) == {"mine", "fake"}
    assert infos["fake"].enabled is False
    assert infos["mine"].config == {"ratio": 0.25}


async def test_invalid_config_is_source_error_only() -> None:
    service = UsageService(_registry(mine=PluginSource(), fake=FakeUsageSource()), clock=clock)
    settings = UsageSettings(
        sources=[
            UsageSourceSetting(id="mine", config={"ratio": "secret-lots-1"}),
            UsageSourceSetting(
                id="fake", config={"windows": [{"window": "ok", "used_ratio": 0.5}]}
            ),
        ]
    )
    snaps = await service.collect(settings)
    assert [(s.source, s.window) for s in snaps] == [("fake", "ok")]
    infos = {i.descriptor.id: i for i in service.sources(settings)}
    error = infos["mine"].error
    assert error is not None
    assert error.code == ErrorCodes.VALIDATION_FAILED
    # 값·jsonschema 원문은 내보내지 않는다(위치와 규칙 키워드만, 1R.13 QA)
    dumped = error.model_dump_json()
    assert "secret-lots-1" not in dumped
    assert "is not of type" not in dumped
    assert error.details == {"path": ["ratio"], "validator": "type"}


async def test_failing_and_slow_sources_do_not_block_others() -> None:
    fake_cfg = UsageSettings(
        sources=[UsageSourceSetting(id="fake", config={"windows": [{"window": "w"}]})]
    )
    service = UsageService(
        _registry(broken=BrokenSource(), slow=SlowSource(), fake=FakeUsageSource()),
        clock=clock,
        timeout_seconds=0.05,
    )
    snaps = await service.collect(fake_cfg)
    assert [s.window for s in snaps] == ["w"]
    infos = {i.descriptor.id: i for i in service.sources(fake_cfg)}
    assert infos["broken"].error is not None
    assert infos["broken"].error.code == SOURCE_FAILED
    assert "sk-secret" not in infos["broken"].model_dump_json()  # 예외 문장은 내보내지 않는다
    assert infos["slow"].error is not None
    assert infos["slow"].error.code == SOURCE_TIMEOUT
    assert infos["fake"].error is None


async def test_error_clears_after_success() -> None:
    class Flaky:
        descriptor = UsageSourceDescriptor(id="f", title="F", trust="x", auto_enable=True)
        fail = True

        async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
            if self.fail:
                raise OSError("nope")
            return []

    flaky = Flaky()
    service = UsageService(_registry(f=flaky), clock=clock)
    await service.collect()
    assert service.sources()[0].error is not None
    flaky.fail = False
    await service.collect()
    assert service.sources()[0].error is None
    assert service.sources()[0].last_observed_at is None  # 관측이 없으면 시각도 없다


async def test_report_never_invents_values() -> None:
    service = UsageService(_registry(), clock=clock)
    report = await service.report()
    assert report.windows == []
    assert report.rollups == []
    assert report.generated_at == NOW
    rows = [TokenRollupRow(agent_id="a", usage=Usage(total_tokens=5))]
    service2 = UsageService(
        _registry(fake=FakeUsageSource()),
        clock=clock,
    )
    settings = UsageSettings(
        sources=[UsageSourceSetting(id="fake", config={"windows": [{"window": "five_hour"}]})]
    )
    report2 = await service2.report(settings, rollups=rows)
    assert report2.windows is not None  # 부분 조회(parts)가 아니면 null이 아니다
    (w,) = report2.windows
    assert (w.used_ratio, w.used_tokens, w.status, w.resets_at) == (None, None, None, None)
    assert report2.rollups == rows


async def test_context_gets_injected_dependencies(tmp_path: Path) -> None:
    plugin = PluginSource()

    class Events:
        def latest_by_type(
            self, type: str, *, run_id: str | None = None, actor: str | None = None, limit: int = 1
        ) -> builtins.list[RunEvent]:
            return []

    events = Events()
    service = UsageService(_registry(p=plugin), clock=clock, events=events, state_dir=tmp_path)
    await service.collect()
    ctx = plugin.contexts[0]
    assert ctx.events is events
    assert ctx.state_dir == tmp_path
    assert ctx.now == NOW


def test_prune_uses_clock() -> None:
    rec = Recorder()
    service = UsageService(_registry(), clock=clock, observations=rec)
    assert service.prune(keep_seconds=100) == 3
    assert rec.pruned == [NOW - 100]
    assert UsageService(_registry(), clock=clock).prune(keep_seconds=1) == 0
