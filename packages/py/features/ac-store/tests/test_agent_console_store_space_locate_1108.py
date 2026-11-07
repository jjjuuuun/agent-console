"""`SpaceLocator`(요청 11/08 후속): 기록 id → 그 기록이 있는 공간."""

from __future__ import annotations

from agent_console_store import SpaceLocator


def _rows() -> dict[str | None, set[str]]:
    return {None: {"host"}, "p1": {"one", "both"}, "p2": {"both", "two"}, "p3": {"three"}}


def test_finds_in_opened_listed_and_host() -> None:
    rows = _rows()
    loc = SpaceLocator(
        lambda place, key: key in rows[place], opened=lambda: ["p1"], project_ids=lambda: ["p2"]
    )
    assert loc.find("one") == ["p1"]
    assert loc.find("two") == ["p2"]
    assert loc.find("host") == [None]
    assert loc.find("both") == ["p1", "p2"]
    assert loc.find("three") == []  # p3는 목록에 없다


def test_candidates_order_dedupe_and_limit() -> None:
    loc = SpaceLocator(
        lambda _p, _k: False,
        opened=lambda: ["b", "a"],
        project_ids=lambda: ["a", "", "c", "d", "e"],
        limit=2,
    )
    assert loc.candidates() == ["b", "a", "c", "d", None]


def test_zero_limit_and_unspaced() -> None:
    loc = SpaceLocator(
        lambda _p, _k: False, opened=lambda: ["a"], project_ids=lambda: ["b"], limit=0
    )
    assert loc.candidates() == ["a", None]
    host_only = SpaceLocator(
        lambda _p, _k: False, opened=lambda: ["a"], project_ids=lambda: ["b"], spaced=lambda: False
    )
    assert host_only.candidates() == [None]


def test_remembers_single_place_and_rechecks_only_it() -> None:
    rows = _rows()
    calls: list[str | None] = []

    def has(place: str | None, key: str) -> bool:
        calls.append(place)
        return key in rows[place]

    loc = SpaceLocator(has, project_ids=lambda: ["p1", "p2", "p3"])
    assert loc.find("three") == ["p3"]
    calls.clear()
    assert loc.find("three") == ["p3"]
    assert calls == ["p3"]
    rows["p3"].discard("three")  # 지워지면 다시 모두 찾는다
    rows[None].add("three")
    assert loc.find("three") == [None]


def test_remember_cap_drops_oldest() -> None:
    rows: dict[str | None, set[str]] = {None: set(), "p1": {"a", "b", "c"}}
    calls: list[str | None] = []

    def has(place: str | None, key: str) -> bool:
        calls.append(place)
        return key in rows[place]

    loc = SpaceLocator(has, project_ids=lambda: ["p1"], remember=2)
    for key in ("a", "b", "c"):
        loc.find(key)
    calls.clear()
    assert loc.find("c") == ["p1"]
    assert calls == ["p1"]  # 기억한 자리만
    calls.clear()
    assert loc.find("a") == ["p1"]
    assert calls == ["p1", None]  # 잊혀서 후보를 모두 본다


def test_errors_are_skipped() -> None:
    def has(place: str | None, key: str) -> bool:
        if place == "bad":
            raise OSError("broken")
        return place is None

    def listing() -> list[str]:
        raise RuntimeError("no list")

    assert SpaceLocator(has, opened=lambda: ["bad"]).find("x") == [None]
    assert SpaceLocator(has, project_ids=listing).find("x") == [None]
