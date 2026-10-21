"""UsageService(extra_sources=): 레지스트리 밖 출처(런타임 출처, design §4R.8 mod-usage 행)."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import pytest

from agent_console_contracts import (
    UsageSettings,
    UsageSourceDescriptor,
    UsageWindowSnapshot,
)
from agent_console_usage import UsageService, UsageSource, UsageSourceContext, new_usage_sources

NOW = 1_800_000_000.0


class Source:
    """주어진 창 하나를 내는 출처."""

    def __init__(self, window: str, *, trust: str = "estimated") -> None:
        self.window = window
        self.descriptor = UsageSourceDescriptor(
            id="anything", title=window, trust=trust, auto_enable=True
        )
        self.contexts: list[UsageSourceContext] = []

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        self.contexts.append(ctx)
        return [UsageWindowSnapshot(source="x", window=self.window, observed_at=ctx.now)]


def _service(extra: object, **registry: UsageSource) -> UsageService:
    reg = new_usage_sources()
    for key, item in registry.items():
        reg.register(key, item)
    return UsageService(reg, clock=lambda: NOW, extra_sources=extra)  # type: ignore[arg-type]


async def test_extra_sources_join_registry_after_registry_entries() -> None:
    service = _service({"zz-extra": Source("w1"), "aa-extra": Source("w2")}, reg=Source("w0"))
    assert [d.id for d in service.descriptors()] == ["reg", "aa-extra", "zz-extra"]
    windows = await service.collect()
    assert [(w.source, w.window) for w in windows] == [
        ("aa-extra", "w2"),
        ("reg", "w0"),
        ("zz-extra", "w1"),
    ]
    assert service.conflicts() == []


async def test_registry_wins_on_id_conflict_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    registry_source = Source("from_registry")
    extra_source = Source("from_extra")
    service = _service({"same": extra_source}, same=registry_source)
    with caplog.at_level(logging.WARNING, logger="agent_console_usage"):
        windows = await service.collect()
        await service.collect()
    assert [(w.source, w.window) for w in windows] == [("same", "from_registry")]
    assert extra_source.contexts == []
    assert service.conflicts() == ["same"]
    assert [i.descriptor.title for i in service.sources()] == ["from_registry"]
    # 경고는 id마다 한 번
    assert sum("same" in r.getMessage() for r in caplog.records) == 1


async def test_callable_extra_sources_are_read_on_every_call() -> None:
    current: dict[str, UsageSource] = {}

    def extras() -> Mapping[str, UsageSource]:
        return current

    service = _service(extras)
    assert await service.collect() == []
    current["late"] = Source("w")
    assert [w.source for w in await service.collect()] == ["late"]
    assert [i.descriptor.id for i in service.sources()] == ["late"]


async def test_extra_sources_follow_settings_like_registry_sources() -> None:
    extra = Source("w")
    extra.descriptor = extra.descriptor.model_copy(
        update={
            "config_schema": {
                "type": "object",
                "properties": {"k": {"type": "integer"}},
                "additionalProperties": False,
            }
        }
    )
    service = _service({"ext": extra})
    off = UsageSettings.model_validate({"sources": [{"id": "ext", "enabled": False}]})
    assert await service.collect(off) == []
    assert [(i.descriptor.id, i.enabled) for i in service.sources(off)] == [("ext", False)]

    bad = UsageSettings.model_validate({"sources": [{"id": "ext", "config": {"k": "x"}}]})
    assert await service.collect(bad) == []
    info = service.sources(bad)[0]
    assert info.error is not None
    assert info.error.code == "validation_failed"

    good = UsageSettings.model_validate({"sources": [{"id": "ext", "config": {"k": 3}}]})
    assert [w.source for w in await service.collect(good)] == ["ext"]
    assert extra.contexts[-1].config == {"k": 3}
    assert extra.contexts[-1].source_id == "ext"


async def test_no_extra_sources_keeps_previous_behaviour() -> None:
    service = _service(None, reg=Source("w0"))
    assert [d.id for d in service.descriptors()] == ["reg"]
    assert service.conflicts() == []
