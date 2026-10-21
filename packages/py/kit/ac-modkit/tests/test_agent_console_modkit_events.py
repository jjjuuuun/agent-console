"""EventBus(구독자 예외 격리)·Hub·PortKey/Topic."""

from __future__ import annotations

import asyncio
import logging

import pytest

from agent_console_modkit import EventBus, Hub, PortKey, Topic

SAID: Topic[str] = Topic("echo.said")


def test_sync_handlers_and_exception_isolation(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    seen: list[str] = []

    def broken(_: str) -> None:
        raise ValueError("boom")

    bus.subscribe(SAID, broken)
    bus.subscribe(SAID, seen.append)
    with caplog.at_level(logging.ERROR):
        bus.publish(SAID, "hi")
    assert seen == ["hi"]
    assert bus.errors == 1
    assert "echo.said" in caplog.text


def test_unsubscribe_is_idempotent() -> None:
    bus = EventBus()
    seen: list[str] = []
    off = bus.subscribe(SAID, seen.append)
    assert bus.subscriber_count(SAID) == 1
    off()
    off()
    bus.publish(SAID, "x")
    assert seen == []
    assert bus.subscriber_count() == 0


async def test_async_handlers_publish_drain_and_deliver() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def slow(item: str) -> None:
        await asyncio.sleep(0)
        seen.append(f"slow {item}")

    async def failing(_: str) -> None:
        raise RuntimeError("x")

    bus.subscribe(SAID, slow)
    bus.subscribe(SAID, failing)
    bus.publish(SAID, "a")
    assert seen == []  # 막히지 않음
    await bus.drain()
    assert seen == ["slow a"]
    await bus.deliver(SAID, "b")
    assert seen == ["slow a", "slow b"]
    assert bus.errors == 2


def test_async_handler_without_running_loop_is_counted() -> None:
    bus = EventBus()

    async def handler(_: str) -> None:
        return None

    bus.subscribe(SAID, handler)
    bus.publish(SAID, "x")
    assert bus.errors == 1


async def test_hub_fanout_and_close() -> None:
    hub: Hub[str] = Hub(maxsize=1)
    sub = hub.subscribe("t")
    hub.publish("t", "one")
    hub.publish("t", "two")  # 큐가 차서 버림
    assert sub.dropped == 1
    assert await sub.get() == "one"
    assert hub.subscriber_count("t") == 1
    sub.close()
    assert hub.subscriber_count() == 0
    assert await sub.get() is None


def test_port_and_topic_identity_is_the_name() -> None:
    assert PortKey("a", "설명") == PortKey("a", multi=False)
    assert hash(PortKey("a")) == hash(PortKey("a", "다른 설명"))
    assert PortKey("a") != PortKey("b")
    with pytest.raises(ValueError, match="비어"):
        PortKey("")
    with pytest.raises(ValueError, match="비어"):
        Topic("")
