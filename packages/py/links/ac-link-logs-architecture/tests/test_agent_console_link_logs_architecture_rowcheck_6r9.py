"""6R.9 M-1: `arch` 필터의 행 기준 미리 거르기 — 결과 차등 0, 판정 재사용 시 본문을 읽지 않는다.

구조도를 그린 범위(판정 캐시가 찬 범위)에서 모든 클릭 대상(칸·묶음·관측 연결·분류 안 됨, 출처
제한 포함)의 표 질의를 미리 거르기 켠 경로와 끈 경로(옛 경로)로 돌려 같은 이벤트·전체 수인지 본다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from agent_console_architecture import ProfileMatcher
from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_link_logs_architecture.scopes import MemoMatcher
from agent_console_link_logs_architecture.testing import (
    LogArchitectureHarness,
    click_targets,
    selector_params,
)
from agent_console_logs import QueryContext, row_check_of
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.sqlite import _clauses as clauses
from agent_console_logs.testing import ScaleLayout, build_scale_index

CTX = QueryContext(error_categories=frozenset({"error"}))
MAIN = 1_200


def _profile() -> ArchitectureProfile:
    def eq(path: str, value: Any) -> dict[str, Any]:
        return {"all": [{"path": path, "op": "eq", "value": value}]}

    return ArchitectureProfile.model_validate(
        {
            "cells": {
                "calls": {"when": eq("/category", "tool_call"), "group_by": "/thread"},
                "llm": {"when": eq("/category", "llm")},
                "main": {"when": eq("/thread", "main"), "group_by": "/tool"},
            },
            "edges": [
                {
                    "id": "e1",
                    "from": "calls",
                    "to": "llm",
                    "kind": "observed",
                    "when": eq("/category", "llm"),
                },
                {"id": "e2", "from": "llm", "to": "main", "kind": "structural"},
            ],
            "unassigned": True,
        }
    )


@pytest.fixture(scope="module")
def big(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[SqliteLogIndex, ScaleLayout]]:
    index = open_log_index(tmp_path_factory.mktemp("rowcheck") / "i.sqlite3")
    layout = build_scale_index(index, main_events=MAIN, noise_events=MAIN, noise_sessions=20)
    yield index, layout
    index.close()


def _targets(h: LogArchitectureHarness, session: str) -> tuple[Any, list[dict[str, Any]]]:
    view = h.project(session=session)
    out = []
    for _name, selector, _count in click_targets(view):
        params = {"session": session, **selector_params(selector), "max_seq": view.max_seq}
        out.append(params)
        sources = ",".join(sorted({"platform-runs", "nope"}))
        out.append({**params, "arch_sources": sources})
    return view, out


def test_row_path_matches_old_path(
    big: tuple[SqliteLogIndex, ScaleLayout], monkeypatch: pytest.MonkeyPatch
) -> None:
    index, layout = big
    h = LogArchitectureHarness(index, profiles={"p": _profile()}, ctx=CTX, cache_events=MAIN * 4)
    view, targets = _targets(h, layout.main_session)
    assert len(targets) >= 10

    def run() -> list[tuple[list[str], int | None]]:
        out = []
        for params in targets:
            flt = h.query.parse_filter({**params, "limit": 40})
            page = h.query.events(flt, with_total=True)
            out.append(([e.uid for e in page.items], page.total))
        return out

    matchers: list[MemoMatcher] = []
    h.arch_filter._on_matcher = matchers.append
    new = run()
    assert sum(m.misses for m in matchers) == 0  # 모두 캐시(행 기준)로 답했다
    monkeypatch.setattr(clauses, "row_check_of", lambda _p: None)
    old = run()
    assert new == old
    assert any(total for _uids, total in new)
    assert view.event_total == layout.main_events


def test_predicate_shapes() -> None:
    """출처 제한·캐시 판정기가 있을 때만 미리 거르기를 가진다. 늘 거짓 판정은 행으로 답한다."""
    from agent_console_architecture import selector_predicate
    from agent_console_conditions import default_operators
    from agent_console_contracts.architecture import ArchitectureSelector

    operators = default_operators()[0]
    profile = _profile()
    plain = selector_predicate(
        profile, ArchitectureSelector(arch="p:cell:llm"), profile_id="p", operators=operators
    )
    assert row_check_of(plain) is None
    limited = selector_predicate(
        profile,
        ArchitectureSelector(arch="p:cell:llm", arch_sources=["a"]),
        profile_id="p",
        operators=operators,
    )
    found = row_check_of(limited)
    assert found is not None
    assert found[0] == frozenset({"seq", "source"})
    assert found[1]({"seq": 1, "source": "b"}) is False
    assert found[1]({"seq": 1, "source": "a"}) is None  # 기본 판정기는 열 값으로 모른다
    never = selector_predicate(
        profile, ArchitectureSelector(arch="p:edge:e2"), profile_id="p", operators=operators
    )
    found = row_check_of(never)
    assert found is not None
    assert found[1]({"seq": 1}) is False
    assert ProfileMatcher(profile, operators).match_row({"seq": 1, "uid": "u"}) is None
