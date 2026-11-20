"""`OpenCache`: 이름 → 열린 값(오래 안 쓴 순서·유휴·상한·종료, 프로젝트 공간 풀 공용)."""

from __future__ import annotations

import pytest

from agent_console_store import CacheShut, OpenCache


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_get_touches_and_peek_does_not() -> None:
    clock = Clock()
    cache: OpenCache[str] = OpenCache(lambda _v: None, clock=clock)
    cache.put("a", "A")
    cache.put("b", "B")
    assert cache.names() == ["a", "b"]
    clock.now = 10
    assert cache.peek("a") == "A"
    assert cache.names() == ["a", "b"]  # peek은 순서를 바꾸지 않는다
    assert cache.idle(5) == [("a", "A"), ("b", "B")]
    assert cache.get("a") == "A"
    assert cache.names() == ["b", "a"]
    assert cache.idle(5) == [("b", "B")]
    assert cache.idle(0) == []  # 0 = 유휴 판정 끔
    assert cache.get("zz") is None


def test_over_pops_oldest_without_closing() -> None:
    closed: list[str] = []
    cache: OpenCache[str] = OpenCache(closed.append)
    for name in "abc":
        cache.put(name, name.upper())
    assert cache.over(1) == [("a", "A"), ("b", "B")]
    assert cache.names() == ["c"]
    assert closed == []  # 닫기는 호출자가 정한다


def test_drop_clear_close_and_cache_stays_usable() -> None:
    closed: list[str] = []
    cache: OpenCache[str] = OpenCache(closed.append)
    cache.put("a", "A")
    cache.put("b", "B")
    cache.drop("a")
    cache.drop("missing")
    assert closed == ["A"]
    assert cache.pop("b") == "B"
    assert closed == ["A"]  # pop은 닫지 않는다
    cache.put("c", "C")
    cache.clear()
    assert closed == ["A", "C"]
    cache.put("d", "D")  # clear 뒤에도 쓸 수 있다
    assert cache.names() == ["d"]


def test_shutdown_closes_all_and_refuses_new_values() -> None:
    closed: list[str] = []
    cache: OpenCache[str] = OpenCache(closed.append)
    cache.put("a", "A")
    cache.shutdown()
    cache.shutdown()  # 여러 번 불러도 된다
    assert cache.shut
    assert closed == ["A"]
    with pytest.raises(CacheShut):
        cache.put("b", "B")
    assert cache.names() == []
