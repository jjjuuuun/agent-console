"""수집 예약 디바운스: 창 동안 모으기, 루프 없으면 바로, 닫기."""

from __future__ import annotations

import asyncio
from collections.abc import Collection

import pytest

from agent_console_link_logs_runs import ScanDebouncer


def _collector() -> tuple[list[set[str]], ScanDebouncer]:
    calls: list[set[str]] = []

    def flush(ids: Collection[str]) -> None:
        calls.append(set(ids))

    return calls, ScanDebouncer(flush, delay=0.05)


async def test_marks_within_window_flush_once() -> None:
    calls, deb = _collector()
    deb.mark("r1")
    deb.mark("r2")
    deb.mark("r1")
    assert calls == []
    assert deb.pending == {"r1", "r2"}
    await asyncio.sleep(0.1)
    assert calls == [{"r1", "r2"}]
    deb.mark("r3")
    await asyncio.sleep(0.1)
    assert calls == [{"r1", "r2"}, {"r3"}]


def test_without_running_loop_flushes_immediately() -> None:
    calls, deb = _collector()
    deb.mark("r1")
    deb.mark("")
    assert calls == [{"r1"}]


async def test_zero_delay_and_close() -> None:
    calls: list[set[str]] = []
    deb = ScanDebouncer(lambda ids: calls.append(set(ids)), delay=0)
    deb.mark("r1")
    assert calls == [{"r1"}]
    slow = ScanDebouncer(lambda ids: calls.append(set(ids)), delay=0.05)
    slow.mark("r2")
    slow.close()
    slow.mark("r3")
    await asyncio.sleep(0.1)
    assert calls == [{"r1"}]


def test_negative_delay_rejected() -> None:
    with pytest.raises(ValueError, match="delay"):
        ScanDebouncer(lambda ids: None, delay=-1)
