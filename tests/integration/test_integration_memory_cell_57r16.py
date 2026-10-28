"""5.7R.16: 구조도 "Memory 칸" R0 시험(design §5.7R.9 R0 시험 1~4, R0.1·R0.3·R8.8·R16.6).

서버를 띄워(포트 없음, TestClient) 메모리 도구를 쓰는 에이전트 하나를 fake 백엔드로 실행한다.
메모리 범위 종류·리소스·에이전트·구조도 프로필·대응표 덮어쓰기는 전부 이 테스트 안에서 만든
**사용자 설정 데이터**다(코드 패치·저장소 데이터 파일 없음 — 시험 4).

1. 기본 프로필(`GET /architecture/profiles/{기본 id}`의 본문)을 복제해 Memory 칸·연결·coverage를
   더한 사용자 프로필로 `run:` 범위 구조도를 그린다. 칸 횟수 = 실행의 메모리 이벤트 수 = 칸 클릭
   필터(`arch`) 수. 서버 SQLite 색인과, 같은 실행 기록을 메모리 색인에 넣은 조립(`PlatformRunsRig` +
   `LogArchitectureHarness`) 둘 다 본다.
2. 대응표 `memory.*` 규칙을 설정 `event_map`으로 바꿔 범주 이름을 `notes`로 하고 프로필 조건도
   `notes`로 하면 같은 결과다(범주 이름도 데이터).
3. 기본 프로필은 그대로다: 칸 목록이 패키지 데이터와 같고(Memory 칸 없음) 메모리 이벤트는 어느
   기본 칸에도 들지 않으며(분류 안 됨), 기본 칸 수는 Memory 칸을 더한 프로필과 같다.
4. 기본 `memory.*` 규칙을 끄면(`{}`) 메모리 이벤트는 범주 `other`이고 다른 로그는 그대로다.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_architecture import load_default_profiles
from agent_console_contracts import NodeRun, Run, RunEvent
from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_link_logs_architecture.testing import (
    LogArchitectureHarness,
    click_count_mismatches,
)
from agent_console_link_logs_runs import load_default_event_map, run_scope_kinds
from agent_console_link_logs_runs.testing import LocalLogs, PlatformRunsRig
from agent_console_logs import QueryContext
from agent_console_server.testing import API, agent_doc, make_settings, server, wait_run

SOURCE = "platform-runs"
OPTIONS: dict[str, dict[str, Any]] = {
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
}
PROFILE = "with-memory"
MEMORY_RULE = "memory.*"
ERRORS = QueryContext(error_categories=frozenset({"error"}))  # 기본 분류 체계의 danger 범주

# 사용자 데이터: 메모리 범위 종류(패키지 기본 범위 종류를 끈다)와 접근 리소스
MEMORY_SETTINGS = {
    "include_default_scope_kinds": False,
    "scope_kinds": {
        "shelf": {"label": "선반", "id": "{/graph_id}"},
        "vault": {"label": "금고", "id": ""},
    },
}
ACCESS = {
    "id": "mem-57r16",
    "type": "memory",
    "name": "선반 접근",
    "config": {
        "scopes": [
            {"kind": "shelf", "access": ["read", "search", "write", "delete"]},
            {"kind": "vault", "access": ["read"]},
        ]
    },
}
CALLS: list[tuple[str, dict[str, Any]]] = [
    ("memory_write", {"key": "결정/api", "content": "v2를 쓴다"}),
    ("memory_write", {"key": "임시/메모", "content": "곧 지움"}),
    ("memory_search", {"query": "v2"}),
    ("memory_read", {"key": "결정/api"}),
    ("memory_delete", {"key": "임시/메모"}),
    ("memory_write", {"key": "k", "content": "x", "scope": "vault"}),  # 권한 없음 → denied
]
GRAPH = {
    "id": "memory-57r16",
    "name": "메모리 칸",
    "nodes": [
        {"id": "you", "type": "user", "label": "나"},
        {"id": "keeper", "type": "agent", "label": "keeper", "config": {"agent_ref": "keeper"}},
    ],
    "edges": [
        {
            "id": "m",
            "source": {"node": "you", "port": "says"},
            "target": {"node": "keeper", "port": "in"},
            "kind": "message",
            "config": {},
        },
        {
            "id": "r",
            "source": {"node": "keeper", "port": "out"},
            "target": {"node": "you", "port": "hears"},
            "kind": "reply",
            "config": {},
        },
    ],
}


def memory_profile(base: Mapping[str, Any], category: str) -> dict[str, Any]:
    """기본 프로필 복제 + Memory 칸·연결·coverage(ac-mod-memory README 예시와 같은 데이터)."""
    when = {"all": [{"path": "/category", "op": "eq", "value": category}]}
    profile = copy.deepcopy(dict(base))
    profile["title"] = "에이전트 아키텍처 + 메모리"
    profile["cells"]["memory"] = {
        "label": "Memory",
        "description": "공유 메모리 읽기·쓰기",
        "x": 810,
        "y": 730,
        "zone": "runtime",
        "tone": "gold",
        "metrics": ["count", "errors"],
        "group_by": "/correlation/memory_scope",
        "when": when,
    }
    profile["edges"].append(
        {
            "id": "memory_access",
            "from": "dispatch",
            "to": "memory",
            "label": "메모리 접근",
            "kind": "observed",
            "style": "request",
            "points": [[1054, 610], [1030, 610], [1030, 730], [906, 730]],
            "label_at": [968, 730],
            "metrics": ["count", "errors"],
            "when": when,
        }
    )
    profile["coverage"][SOURCE]["cells"].append("memory")
    return profile


def _settings_body(
    client: TestClient, base: Mapping[str, Any], category: str, event_map: dict[str, Any] | None
) -> dict[str, Any]:
    body: dict[str, Any] = client.get(f"{API}/settings").json()
    body["memory"] = MEMORY_SETTINGS
    body["architecture"] = {"profiles": {PROFILE: memory_profile(base, category)}}
    config = {"event_map": event_map} if event_map is not None else {}
    body["logs"] = {"sources": [{"id": SOURCE, "enabled": True, "config": config}]}
    return body


def _run(client: TestClient) -> dict[str, Any]:
    keeper = agent_doc("keeper", "끝", resources=[{"ref": ACCESS["id"]}])
    keeper["backend_options"]["default"]["host_tool_calls"] = [
        {"tool": tool, "input": data, "append": False} for tool, data in CALLS
    ]
    assert client.post(f"{API}/resources", json=ACCESS).status_code == 201
    assert client.post(f"{API}/agents", json=keeper).status_code == 201
    assert client.post(f"{API}/graphs", json=GRAPH).status_code == 201
    started = client.post(f"{API}/runs", json={"graph_id": GRAPH["id"], "input": {"text": "go"}})
    assert started.status_code == 202, started.text
    snap = wait_run(client, started.json()["id"], timeout=30)
    assert snap["run"]["status"] == "completed", snap["run"]
    return snap


def _run_events(client: TestClient, run_id: str) -> list[dict[str, Any]]:
    """종료 이벤트까지 저장된 실행 이벤트(기록기는 Run을 먼저 저장한다)."""
    for _ in range(200):
        events: list[dict[str, Any]] = client.get(f"{API}/runs/{run_id}/events").json()
        if any(e["type"] in ("run.completed", "run.finished") for e in events):
            return events
        time.sleep(0.05)
    return events


def _count(client: TestClient, **flt: Any) -> int:
    rows = client.post(
        f"{API}/logs/aggregate", json={"group_by": [], "metric": "events", "filter": flt}
    ).json()
    return int(rows[0]["value"]) if rows else 0


def _indexed(client: TestClient, run_id: str) -> None:
    """두 번 연속 같은 수가 나올 때까지 플랫폼 실행 이벤트를 수집한다."""
    last = -1
    for _ in range(200):
        assert client.post(f"{API}/logs/scan", json={"source_ids": [SOURCE]}).status_code == 202
        got = _count(client, run_id=[run_id], source=[SOURCE])
        if got and got == last:
            return
        last = got
        time.sleep(0.1)
    raise AssertionError(f"색인이 끝나지 않았다: {last}")


def _items(client: TestClient, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        query = {**params, "limit": 200, **({"cursor": cursor} if cursor else {})}
        page = client.get(f"{API}/logs/events", params=query)
        assert page.status_code == 200, page.text
        out += page.json()["items"]
        cursor = page.json().get("next_cursor")
        if not cursor:
            return out


def _picked(
    client: TestClient, scope: dict[str, Any], view: dict[str, Any], selector: Any
) -> list[dict[str, Any]]:
    """칸·연결을 눌렀을 때의 이벤트 표(범위 + 선택 필터 + 결과 ``max_seq``)."""
    params: dict[str, Any] = {**scope, "arch": selector["arch"], "max_seq": view["max_seq"]}
    if selector.get("arch_group") is not None:
        params["arch_group"] = selector["arch_group"]
    if selector.get("arch_sources") is not None:
        params["arch_sources"] = ",".join(selector["arch_sources"])
    return _items(client, params)


def _click(client: TestClient, scope: dict[str, Any], view: dict[str, Any], selector: Any) -> int:
    return len(_picked(client, scope, view, selector))


def _view(client: TestClient, scope: dict[str, Any], profile: str) -> dict[str, Any]:
    res = client.get(f"{API}/logs/architecture", params={**scope, "profile": profile})
    assert res.status_code == 200, res.text
    view: dict[str, Any] = res.json()
    assert view["profile"] == profile
    return view


def _cell(view: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in view["cells"] if c["id"] == cell_id)
    return found


def _memory_index_view(
    snap: dict[str, Any],
    events: list[dict[str, Any]],
    event_map: dict[str, Any] | None,
    profile: dict[str, Any],
) -> tuple[Any, int]:
    """같은 실행 기록을 메모리 색인(서버 없이 조립)에 넣고 `run:` 범위 구조도를 그린다.

    Returns:
        (구조도, 클릭 수가 지표와 다른 대상 수).
    """
    rig = PlatformRunsRig()
    run = Run.model_validate(snap["run"])
    rig.records.runs.save(run)
    for node_run in snap["node_runs"]:
        rig.records.runs.save_node_run(NodeRun.model_validate(node_run))
    rig.records.events.append(*(RunEvent.model_validate(e) for e in events))
    rig.scan({"event_map": event_map} if event_map is not None else {})
    harness = LogArchitectureHarness(
        rig.index,
        profiles={PROFILE: ArchitectureProfile.model_validate(profile)},
        ctx=ERRORS,
        scope_kinds=run_scope_kinds(rig.records.runs, LocalLogs(rig.index)),
        source_kinds={},
    )
    base = {"scope": f"run:{run.id}"}
    view = harness.project(**base, profile=PROFILE)
    wrong, checked = click_count_mismatches(view, harness.count, base)
    assert checked > 0
    return view, len(wrong)


@pytest.mark.parametrize(
    ("category", "renamed"),
    [("memory", False), ("notes", True)],
    ids=["default-category", "renamed-notes"],
)
def test_user_profile_memory_cell_counts_match(
    tmp_path: Path, category: str, renamed: bool
) -> None:
    # 시험 2: 기본 규칙을 통째로 복사해 범주 이름만 바꾼 설정 event_map(사용자 데이터)
    event_map = (
        {MEMORY_RULE: {**load_default_event_map().rules[MEMORY_RULE], "category": category}}
        if renamed
        else None
    )
    with server(make_settings(tmp_path, options=OPTIONS)) as client:
        default_id = client.get(f"{API}/architecture/profiles").json()["default_profile"]
        base = client.get(f"{API}/architecture/profiles/{default_id}").json()["profile"]
        body = _settings_body(client, base, category, event_map)
        assert client.put(f"{API}/settings", json=body).status_code == 200
        listing = client.get(f"{API}/architecture/profiles").json()
        assert PROFILE in {p["id"] for p in listing["profiles"]}

        snap = _run(client)
        run_id = snap["run"]["id"]
        events = _run_events(client, run_id)
        memory_events = [e for e in events if e["type"].startswith("memory.")]
        statuses = [e["payload"]["status"] for e in memory_events]
        assert statuses == ["ok"] * (len(CALLS) - 1) + ["denied"], statuses
        expected = len(memory_events)
        _indexed(client, run_id)

        # 시험 1(SQLite 색인 — 서버 호스트 DB): 칸 수 = 메모리 이벤트 수 = 칸 클릭 수
        scope = {"scope": f"run:{run_id}"}
        logs = _items(client, {**scope, "category": category})
        assert len(logs) == expected
        assert {d["kind"] for e in logs for d in e["documents"]} == {"memory"}
        assert sum(1 for e in logs if not e["documents"]) == 1  # 범위를 모르는 denied 호출
        view = _view(client, scope, PROFILE)
        cell = _cell(view, "memory")
        assert cell["status"] == "observed"
        assert cell["metrics"]["count"]["value"] == expected
        assert cell["metrics"]["errors"]["value"] == 0  # denied = block(판정이지 오류가 아님)
        assert _click(client, scope, view, cell["selector"]) == expected
        groups = {g["key"]: g["metrics"]["count"]["value"] for g in cell.get("groups") or []}
        # 묶음 = 근거 memory_scope(범위 종류). 권한 없는 호출은 범위를 몰라(scope null) 이름 없음
        assert groups["shelf"] == expected - 1
        assert sum(groups.values()) == expected
        [edge] = [e for e in view["edges"] if e["id"] == "memory_access"]
        assert edge["metrics"]["count"]["value"] == expected
        assert _click(client, scope, view, edge["selector"]) == expected

        # 시험 1(메모리 색인 — 같은 실행 기록, 같은 사용자 데이터)
        mem_view, wrong = _memory_index_view(
            snap, events, event_map, memory_profile(base, category)
        )
        mem_cell = next(c for c in mem_view.cells if c.id == "memory")
        assert mem_cell.metrics["count"].value == expected
        assert wrong == 0

        # 시험 3: 기본 프로필은 그대로 — Memory 칸이 없고 메모리 이벤트는 분류 안 됨
        default_view = _view(client, scope, default_id)
        packaged = load_default_profiles()[default_id]
        assert [c["id"] for c in default_view["cells"]] == list(packaged.cells)
        assert "memory_access" not in {e["id"] for e in default_view["edges"]}
        uids = {e["uid"] for e in logs}
        for target in default_view["cells"]:
            picked = {e["uid"] for e in _picked(client, scope, default_view, target["selector"])}
            assert not (picked & uids), target["id"]
        unassigned = default_view["unassigned"]
        assert unassigned is not None
        assert _click(client, scope, default_view, unassigned["selector"]) >= expected
        counts = {c["id"]: c["metrics"].get("count") for c in default_view["cells"]}
        assert counts == {
            c["id"]: c["metrics"].get("count") for c in view["cells"] if c["id"] != "memory"
        }


def test_turning_off_default_memory_rule_gives_other(tmp_path: Path) -> None:
    # 시험 4(design §5.7R.10 표 7행): 설정 event_map에서 기본 규칙을 빈 규칙으로 끈다
    with server(make_settings(tmp_path, options=OPTIONS)) as client:
        default_id = client.get(f"{API}/architecture/profiles").json()["default_profile"]
        base = client.get(f"{API}/architecture/profiles/{default_id}").json()["profile"]
        body = _settings_body(client, base, "memory", {MEMORY_RULE: {}})
        assert client.put(f"{API}/settings", json=body).status_code == 200
        snap = _run(client)
        run_id = snap["run"]["id"]
        events = _run_events(client, run_id)
        memory_types = [e["type"] for e in events if e["type"].startswith("memory.")]
        assert len(memory_types) == len(CALLS)
        _indexed(client, run_id)
        scope = {"scope": f"run:{run_id}"}
        logs = _items(client, scope)
        memory_logs = [e for e in logs if e["title"].startswith("memory.")]
        assert sorted(e["title"] for e in memory_logs) == sorted(memory_types)
        assert {e["category"] for e in memory_logs} == {"other"}
        assert _items(client, {**scope, "category": "memory"}) == []
        # 다른 로그는 그대로(모델 응답·도구 호출·실행 상태)
        assert {"llm", "tool_call", "system"} <= {e["category"] for e in logs}
        # 사용자 프로필의 Memory 칸은 0회(조건은 데이터라 범주가 없으면 맞지 않는다)
        cell = _cell(_view(client, scope, PROFILE), "memory")
        assert (cell["metrics"]["count"] or {}).get("value") in (0, None)
