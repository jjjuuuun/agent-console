"""패키지 기본 프로필 `agent-architecture`(5.5R.8, design §5.5R.10 "기본 프로필 골든").

- 데이터가 화면 명세 §9 좌표 표(칸 16·연결 21·영역 3)와 같다.
- 프로필 검사 이슈 0건.
- 사용자가 끄고(`include_defaults: false`, id를 null로) 덮어쓸 수 있다(R0.1).
- 골든 2개: Claude Code 세션 표본, 같은 실행의 플랫폼 기록 + 세션 로그 표본(`testing.load_sample`).
- 이중 출처에서 도구 호출은 한 번만 센다(출처 우선순위), 클릭 필터도 같은 수를 고른다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_architecture import (
    load_default_profiles,
    merge_profiles,
    profile_issues,
    project_architecture,
    selector_predicate,
)
from agent_console_architecture.testing import load_sample, rename_profile_ids
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import (
    ArchitectureProfile,
    ArchitectureSettings,
    ArchitectureView,
)

Ops = dict[str, ConditionOperator]

PROFILE_ID = "agent-architecture"
ERROR_CATEGORIES = frozenset({"error"})  # 기본 분류 체계에서 오류로 표시한 범주(호출자가 넘기는 값)

# 화면 명세 §9.3(선언 순서 = Tab 순서): id, x, y, zone, tone
CELLS = [
    ("input", 130, 130, "local", "blue"),
    ("sdk", 470, 130, "local", "blue"),
    ("api", 810, 130, "local", "teal"),
    ("rules", 130, 280, "local", "gold"),
    ("instructions", 470, 280, "runtime", "gold"),
    ("context", 810, 280, "runtime", "teal"),
    ("llm", 1400, 280, "remote", "purple"),
    ("dispatch", 1150, 580, "runtime", "teal"),
    ("hook", 810, 580, "runtime", "pink"),
    ("tools", 470, 580, "runtime", "orange"),
    ("mcp", 1150, 430, "runtime", "orange"),
    ("result", 810, 430, "runtime", "teal"),
    ("workspace", 470, 430, "runtime", "blue"),
    ("delegation", 130, 580, "local", "gold"),
    ("subagents", 130, 430, "local", "gold"),
    ("response", 1150, 730, "runtime", "blue"),
]

# 화면 명세 §9.4: id, from, to, points, label_at, label_max_w
EDGES: list[tuple[str, str, str, list[list[float]], list[float], float | None]] = [
    ("task_submit", "input", "sdk", [[226, 130], [374, 130]], [300, 130], None),
    ("control_request", "sdk", "api", [[566, 112], [714, 112]], [640, 112], None),
    ("control_response", "api", "sdk", [[714, 148], [566, 148]], [640, 148], None),
    ("context_prepare", "api", "context", [[810, 170], [810, 240]], [810, 191], None),
    ("instructions_apply", "instructions", "context", [[566, 280], [714, 280]], [640, 280], None),
    ("model_request", "context", "llm", [[906, 280], [1304, 280]], [1105, 280], None),
    ("model_output", "llm", "dispatch", [[1400, 320], [1400, 580], [1246, 580]], [1400, 450], None),
    (
        "tool_call",
        "dispatch",
        "tools",
        [[1110, 620], [1110, 655], [440, 655], [440, 620]],
        [775, 655],
        None,
    ),
    ("delegation_tools", "delegation", "tools", [[226, 580], [374, 580]], [300, 580], None),
    ("local_work", "tools", "workspace", [[440, 540], [440, 470]], [440, 505], None),
    ("work_result", "workspace", "result", [[566, 430], [714, 430]], [640, 430], None),
    (
        "tool_result",
        "tools",
        "result",
        [[510, 540], [510, 505], [780, 505], [780, 470]],
        [645, 505],
        None,
    ),
    ("next_context", "result", "context", [[810, 390], [810, 320]], [810, 355], None),
    ("final_response", "dispatch", "response", [[1190, 620], [1190, 690]], [1190, 655], None),
    ("rule_load", "rules", "instructions", [[226, 280], [374, 280]], [300, 280], None),
    ("hook_run", "dispatch", "hook", [[1054, 580], [906, 580]], [980, 580], None),
    ("hook_verdict", "hook", "tools", [[714, 580], [566, 580]], [640, 580], None),
    ("mcp_call", "dispatch", "mcp", [[1150, 540], [1150, 470]], [1150, 505], None),
    ("mcp_result", "mcp", "result", [[1054, 430], [906, 430]], [980, 430], None),
    ("delegate", "delegation", "subagents", [[80, 540], [80, 470]], [80, 505], 92),
    ("merge", "subagents", "delegation", [[180, 470], [180, 540]], [180, 505], 92),
]

# 순서로만 아는 연결(지표 없음, 점선). 명세 §9.4의 7개 + 제어 응답
# (5.5R.8: 응답을 따로 기록한 이벤트가 없다).
STRUCTURAL = {
    "control_response",
    "context_prepare",
    "instructions_apply",
    "model_request",
    "delegation_tools",
    "local_work",
    "next_context",
    "rule_load",
}


@pytest.fixture(scope="module")
def profile() -> ArchitectureProfile:
    return load_default_profiles()[PROFILE_ID]


def _project(sample: str, profile: ArchitectureProfile, operators: Ops) -> ArchitectureView:
    data = load_sample(sample)
    return project_architecture(
        data.events,
        profile,
        profile_id=PROFILE_ID,
        operators=operators,
        source_kinds=data.source_kinds,
        tokens=data.tokens,
        error_categories=ERROR_CATEGORIES,
    )


def _num(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def _summary(view: ArchitectureView) -> dict[str, Any]:
    """골든 비교용 요약: 칸·관측 연결의 상태, 지표 값, 묶음(값, 횟수), 우선순위로 남긴 출처."""
    cells: dict[str, Any] = {}
    for cell in view.cells:
        row: dict[str, Any] = {
            "status": cell.status,
            **{name: _num(m.value) for name, m in cell.metrics.items()},
        }
        if cell.groups is not None:
            row["groups"] = [(g.key, _num(g.metrics["count"].value)) for g in cell.groups]
        if cell.selector.arch_sources is not None:
            row["sources"] = cell.selector.arch_sources
        cells[cell.id] = row
    edges: dict[str, Any] = {}
    for edge in view.edges:
        if edge.kind != "observed":
            continue
        row = {
            "status": edge.status,
            **{name: _num(m.value) for name, m in edge.metrics.items()},
        }
        if edge.selector is not None and edge.selector.arch_sources is not None:
            row["sources"] = edge.selector.arch_sources
        edges[edge.id] = row
    assert view.unassigned is not None
    return {
        "cells": cells,
        "edges": edges,
        "unassigned": _num(view.unassigned.metrics["count"].value),
        "event_total": view.event_total,
    }


CC = ["claude-code-jsonl"]

GOLDEN_CLAUDE_CODE_SESSION: dict[str, Any] = {
    "cells": {
        "input": {"status": "observed", "count": 2.0},
        "sdk": {"status": "observed", "count": 0.0, "errors": 0.0},
        "api": {"status": "observed", "count": 0.0, "errors": 0.0},
        "rules": {"status": "partial", "count": 1.0, "groups": [("/work/demo/CLAUDE.md", 1.0)]},
        "instructions": {"status": "observed", "count": 0.0, "groups": []},
        "context": {"status": "observed", "count": 1.0},
        "llm": {
            "status": "observed",
            "count": 4.0,
            "errors": 0.0,
            "tokens": 214.0,
            "duration": None,
            "groups": [("claude-test-model", 2.0), ("claude-test-small", 2.0)],
        },
        "dispatch": {"status": "observed", "count": 4.0},
        "hook": {
            "status": "partial",
            "count": 3.0,
            "errors": 0.0,
            "duration": None,
            "groups": [("PreToolUse", 1.0), ("SessionStart", 1.0), (None, 1.0)],
        },
        "tools": {
            "status": "observed",
            "count": 2.0,
            "duration": 1500.0,
            "groups": [("Read", 1.0), ("Write", 1.0)],
        },
        "mcp": {
            "status": "partial",
            "count": 2.0,
            "errors": 0.0,
            "duration": 2000.0,
            "groups": [("tracker", 1.0), (None, 1.0)],
        },
        "result": {"status": "observed", "count": 4.0, "errors": 1.0},
        "workspace": {"status": "observed", "count": 1.0},
        "delegation": {"status": "observed", "count": 2.0, "errors": 0.0},
        "subagents": {
            "status": "observed",
            "count": 3.0,
            "errors": 0.0,
            "tokens": 12.0,
            "groups": [("agent-a1b2", 3.0)],
        },
        "response": {"status": "not_collected", "count": None},
    },
    "edges": {
        "task_submit": {"status": "observed", "count": 1.0},
        "control_request": {"status": "observed", "count": 0.0, "errors": 0.0},
        "model_output": {"status": "observed", "count": 4.0, "errors": 0.0},
        "tool_call": {"status": "observed", "count": 2.0, "errors": 0.0, "duration": 1500.0},
        "work_result": {"status": "observed", "count": 1.0},
        "tool_result": {"status": "observed", "count": 3.0, "errors": 1.0},
        "final_response": {"status": "not_collected", "count": None},
        "hook_run": {"status": "observed", "count": 2.0, "errors": 0.0, "duration": None},
        "hook_verdict": {"status": "observed", "count": 1.0, "errors": 0.0},
        "mcp_call": {"status": "observed", "count": 1.0, "errors": 0.0, "duration": 2000.0},
        "mcp_result": {"status": "partial", "count": 0.0, "errors": 0.0},
        "delegate": {"status": "observed", "count": 1.0, "errors": 0.0},
        "merge": {"status": "observed", "count": 1.0, "errors": 0.0},
    },
    "unassigned": 1.0,
    "event_total": 21,
}

GOLDEN_RUN_WITH_SESSION_LOG: dict[str, Any] = {
    "cells": {
        "input": {"status": "observed", "count": 2.0},
        "sdk": {"status": "observed", "count": 3.0, "errors": 0.0},
        "api": {"status": "observed", "count": 0.0, "errors": 0.0},
        # 5.7R.7(M-2): 플랫폼 맥락 구성의 규칙 리소스가 첫 문서(kind rules)가 되어 Rules를 채운다.
        # 이전 값 {"status": "partial", "count": 0.0, "groups": []}: 세션 로그(부분)만 Rules를
        # 채울 수 있었다.
        "rules": {"status": "observed", "count": 1.0, "groups": [("house-rules", 1.0)]},
        "instructions": {"status": "observed", "count": 0.0, "groups": []},
        "context": {"status": "observed", "count": 1.0},
        "llm": {
            "status": "observed",
            "count": 2.0,
            "errors": 0.0,
            "tokens": 23.0,
            "duration": None,
            "groups": [("claude-test-model", 1.0), ("claude-test-small", 1.0)],
            "sources": CC,
        },
        "dispatch": {"status": "observed", "count": 4.0, "sources": CC},
        "hook": {
            "status": "observed",
            "count": 2.0,
            "errors": 0.0,
            "duration": 25.0,
            "groups": [(None, 2.0)],
        },
        "tools": {
            "status": "observed",
            "count": 2.0,
            "duration": 750.0,
            "groups": [("Bash", 1.0), ("Read", 1.0)],
            "sources": CC,
        },
        "mcp": {
            "status": "observed",
            "count": 1.0,
            "errors": 0.0,
            "duration": 1000.0,
            "groups": [("docs", 1.0)],
            "sources": CC,
        },
        "result": {"status": "observed", "count": 4.0, "errors": 1.0, "sources": CC},
        "workspace": {"status": "observed", "count": 0.0},
        "delegation": {"status": "observed", "count": 2.0, "errors": 0.0, "sources": CC},
        "subagents": {
            "status": "observed",
            "count": 4.0,
            "errors": 0.0,
            "tokens": 11.0,
            "groups": [("agent-h1", 4.0)],
            "sources": CC,
        },
        "response": {"status": "observed", "count": 5.0},
    },
    "edges": {
        "task_submit": {"status": "observed", "count": 1.0},
        "control_request": {"status": "observed", "count": 0.0, "errors": 0.0},
        "model_output": {"status": "observed", "count": 2.0, "errors": 0.0, "sources": CC},
        "tool_call": {
            "status": "observed",
            "count": 2.0,
            "errors": 0.0,
            "duration": 750.0,
            "sources": CC,
        },
        "work_result": {"status": "observed", "count": 0.0},
        "tool_result": {"status": "observed", "count": 3.0, "errors": 1.0, "sources": CC},
        "final_response": {"status": "observed", "count": 2.0},
        "hook_run": {"status": "observed", "count": 1.0, "errors": 0.0, "duration": 25.0},
        "hook_verdict": {"status": "observed", "count": 1.0, "errors": 0.0},
        "mcp_call": {
            "status": "observed",
            "count": 1.0,
            "errors": 0.0,
            "duration": 1000.0,
            "sources": CC,
        },
        "mcp_result": {"status": "observed", "count": 1.0, "errors": 1.0},
        "delegate": {"status": "observed", "count": 1.0, "errors": 0.0, "sources": CC},
        "merge": {"status": "observed", "count": 1.0, "errors": 0.0, "sources": CC},
    },
    "unassigned": 2.0,
    "event_total": 37,
}


def test_layout_matches_screen_spec(profile: ArchitectureProfile) -> None:
    assert profile.canvas is not None
    assert (profile.canvas.width, profile.canvas.height) == (1520, 812)
    assert [(z.id, z.x, z.y, z.w, z.h, z.style) for z in profile.zones] == [
        ("local", 10, 16, 1260, 780, "boundary"),
        ("remote", 1290, 16, 220, 780, "service"),
        ("runtime", 370, 212, 880, 572, "runtime"),
    ]
    assert [(cid, c.x, c.y, c.zone, c.tone) for cid, c in profile.cells.items()] == CELLS
    assert all(c.w is None and c.h is None for c in profile.cells.values())  # 기본 크기(180, 68)
    assert [
        (e.id, e.from_, e.to, e.points, e.label_at, e.label_max_w) for e in profile.edges
    ] == EDGES
    for edge in profile.edges:
        structural = edge.id in STRUCTURAL
        assert edge.kind == ("structural" if structural else "observed"), edge.id
        if structural:
            assert (edge.style, edge.when, edge.metrics) == ("inferred", None, None), edge.id
        else:
            assert edge.when is not None, edge.id


def test_profile_has_no_issues(profile: ArchitectureProfile, operators: Ops) -> None:
    # drill 필터 이름은 로그 필터 목록과 대조한다(`thread`는 LogFilter 필드).
    found = profile_issues(profile, operators=operators, filters=["thread"], profile_id=PROFILE_ID)
    assert found == []


def test_coverage_and_priority_are_data(profile: ArchitectureProfile) -> None:
    assert profile.source_priority == ["claude-code-jsonl", "platform-runs"]
    assert set(profile.coverage) == {"claude-code-jsonl", "platform-runs"}
    for coverage in profile.coverage.values():
        assert set(coverage.cells) <= set(profile.cells)
        assert set(coverage.partial) <= set(coverage.cells)
    # C5(design §5.5R.1): Claude Code hook 소요는 수집되지 않는다 → 부분
    assert "hook" in profile.coverage["claude-code-jsonl"].partial


def test_user_can_turn_off_and_replace_defaults() -> None:
    defaults = load_default_profiles()
    on = merge_profiles(defaults, [], None)
    assert on.ids() == [PROFILE_ID]
    assert on.default_profile == PROFILE_ID
    assert on.entries[PROFILE_ID].origin == "default"
    off = merge_profiles(defaults, [], ArchitectureSettings(include_defaults=False))
    assert (off.ids(), off.default_profile, off.pick()) == ([], None, (None, None))
    gone = merge_profiles(
        defaults, [], ArchitectureSettings.model_validate({"profiles": {PROFILE_ID: None}})
    )
    assert gone.ids() == []
    assert [e.id for e in gone.disabled] == [PROFILE_ID]
    mine = merge_profiles(
        defaults,
        [],
        ArchitectureSettings.model_validate({"profiles": {PROFILE_ID: {"title": "내 구조도"}}}),
    )
    entry = mine.entries[PROFILE_ID]
    assert (entry.origin, entry.overrides, entry.title) == ("user", "default", "내 구조도")
    assert entry.profile.cells == {}  # id 단위로 통째로 바뀐다


@pytest.mark.parametrize(
    ("sample", "golden"),
    [
        ("claude_code_session", GOLDEN_CLAUDE_CODE_SESSION),
        ("run_with_session_log", GOLDEN_RUN_WITH_SESSION_LOG),
    ],
)
def test_golden(
    sample: str, golden: dict[str, Any], profile: ArchitectureProfile, operators: Ops
) -> None:
    assert _summary(_project(sample, profile, operators)) == golden


def test_dual_source_counts_each_tool_call_once(
    profile: ArchitectureProfile, operators: Ops
) -> None:
    data = load_sample("run_with_session_log")
    calls = [e for e in data.events if "tool_call" in e.tags]
    by_kind = {
        kind: {e.call_id for e in calls if data.source_kinds.get(e.source) == kind}
        for kind in ("claude-code-jsonl", "platform-runs")
    }
    # 표본 전제: 같은 도구 호출 4개가 두 출처에 한 번씩 있다
    assert by_kind["claude-code-jsonl"] == by_kind["platform-runs"]
    assert len(by_kind["claude-code-jsonl"]) == 4
    view = _project("run_with_session_log", profile, operators)
    dispatch = next(c for c in view.cells if c.id == "dispatch")
    assert dispatch.metrics["count"].value == 4  # 8이 아니다
    assert dispatch.selector.arch_sources == ["claude-code-jsonl"]
    # 클릭 필터(이벤트 표)도 같은 이벤트를 고른다
    keep = selector_predicate(
        profile, dispatch.selector, profile_id=PROFILE_ID, operators=operators
    )
    picked = [e for e in data.events if keep(e)]
    assert len(picked) == 4
    assert {e.call_id for e in picked} == by_kind["claude-code-jsonl"]
    tool_call = next(e for e in view.edges if e.id == "tool_call")
    assert tool_call.selector is not None
    keep = selector_predicate(
        profile, tool_call.selector, profile_id=PROFILE_ID, operators=operators
    )
    assert len([e for e in data.events if keep(e)]) == tool_call.metrics["count"].value == 2


def test_platform_record_alone_fills_platform_cells(
    profile: ArchitectureProfile, operators: Ops
) -> None:
    data = load_sample("run_with_session_log")
    platform = [e for e in data.events if data.source_kinds.get(e.source) == "platform-runs"]
    view = project_architecture(
        platform,
        profile,
        profile_id=PROFILE_ID,
        operators=operators,
        source_kinds=data.source_kinds,
        error_categories=ERROR_CATEGORIES,
    )
    cells = {c.id: c for c in view.cells}
    # 플랫폼 기록이 채우지 못하는 칸은 0이 아니라 "수집 안 됨"
    for cid in ("input", "instructions", "workspace"):
        assert cells[cid].status == "not_collected", cid
        assert cells[cid].metrics["count"].value is None
    # Rules(5.7R.7, M-2): 맥락 구성의 규칙 리소스 → 관측, 클릭 필터 수 = 칸 수
    rules = cells["rules"]
    assert rules.status == "observed"
    assert rules.metrics["count"].value == 1
    assert [(g.key, g.metrics["count"].value) for g in rules.groups or []] == [("house-rules", 1)]
    keep = selector_predicate(profile, rules.selector, profile_id=PROFILE_ID, operators=operators)
    assert len([e for e in platform if keep(e)]) == rules.metrics["count"].value
    # 플랫폼 실행 출처는 모델 호출 소요(C2)와 hook 소요를 안다
    assert cells["llm"].metrics["duration"].value == pytest.approx(1200.0)
    assert cells["hook"].metrics["duration"].value == pytest.approx(25.0, abs=0.01)
    assert cells["dispatch"].metrics["count"].value == 4
    assert cells["context"].metrics["count"].value == 1  # agent.context_prepared(C1)
    assert [(g.key, g.metrics["count"].value) for g in cells["subagents"].groups or []] == [
        ("lead/helper", 5)
    ]


def test_renamed_ids_give_same_counts(profile: ArchitectureProfile, operators: Ops) -> None:
    renamed = rename_profile_ids(profile, cell=lambda c: f"c-{c}", edge=lambda e: f"e-{e}")
    data = load_sample("claude_code_session")
    kwargs: dict[str, Any] = {
        "operators": operators,
        "source_kinds": data.source_kinds,
        "tokens": data.tokens,
        "error_categories": ERROR_CATEGORIES,
    }
    base = project_architecture(data.events, profile, profile_id="a", **kwargs)
    other = project_architecture(data.events, renamed, profile_id="b", **kwargs)
    assert [{k: m.value for k, m in c.metrics.items()} for c in base.cells] == [
        {k: m.value for k, m in c.metrics.items()} for c in other.cells
    ]
    assert [{k: m.value for k, m in e.metrics.items()} for e in base.edges] == [
        {k: m.value for k, m in e.metrics.items()} for e in other.edges
    ]
