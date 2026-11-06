"""7R.15: 구조도 "Wiki 칸" R0 시험(design §7R.4 로그·구조도 행, §5.7R.9 Memory 칸 시험과 같은 방식).

서버를 띄워(포트 없음, TestClient) 위키 도구를 쓰는 에이전트 하나를 fake 백엔드로 실행한다.
위키·접근 리소스·에이전트·구조도 프로필·대응표 덮어쓰기는 전부 이 테스트 안에서 만든 **사용자
데이터**다(코드 패치·저장소 데이터 파일 없음). 도구 이름은 계약 기본값에서 읽는다.

1. 실행 → 로그 색인에 `wiki.*`(범주 `wiki`, 문서 표지 kind `wiki`, 본문 없음). 기본 프로필을 복제해
   Wiki 칸·연결·coverage를 더한 사용자 프로필로 `run:` 범위 구조도를 그리면 칸 횟수 = 위키 이벤트 수
   = 칸 클릭 필터(`arch`) 수, 묶음 = 근거 `wiki`(위키 id).
2. 대응표 `wiki.*` 규칙을 설정 `event_map`으로 바꿔 범주 이름을 `knowledge`로 하고 프로필 조건도
   `knowledge`로 하면 같은 결과(범주 이름도 데이터).
3. 기본 프로필은 그대로: 칸 목록이 패키지 데이터와 같고 위키 이벤트는 어느 기본 칸에도 들지 않는다.
4. 기본 `wiki.*` 규칙을 끄면(`{}`) 위키 이벤트는 범주 `other`로 남고 다른 로그는 그대로다.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_architecture import load_default_profiles
from agent_console_contracts.wiki import wiki_access_defaults
from agent_console_link_logs_runs import load_default_event_map
from agent_console_link_wiki_runs import load_wiki_resource_type
from agent_console_server.testing import API, agent_doc, make_settings, server, wait_run

NO_PROJECT_GATE: dict[str, dict[str, Any]] = {"link-projects-runs": {"require_project": False}}
SOURCE = "platform-runs"
OPTIONS: dict[str, dict[str, Any]] = {
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
    "mod-wiki": {"scan_interval_seconds": 0},
}
PROFILE = "with-wiki"
WIKI_RULE = "wiki.*"
BODY = "결정: 응답 형식은 JSON v2"
TOOLS = {op: t["name"] for op, t in wiki_access_defaults()["tools"].items()}
ALL_OPS = ["read", "search", "list", "links", "write", "move", "delete"]


def _calls(wiki_id: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("write", {"path": "결정/형식", "content": BODY}),
        ("write", {"path": "임시/메모", "content": "곧 옮김"}),
        ("search", {"query": "JSON"}),
        ("list", {}),
        ("read", {"path": "결정/형식"}),
        ("links", {"path": "결정/형식"}),
        ("move", {"path": "임시/메모", "to": "임시/옮김"}),
        ("delete", {"path": "임시/옮김"}),
        ("write", {"path": "x", "content": "y", "wiki": f"{wiki_id}-없음"}),  # 접근 밖 → denied
    ]


def wiki_profile(base: Mapping[str, Any], category: str) -> dict[str, Any]:
    """기본 프로필 복제 + Wiki 칸·연결·coverage(ac-mod-wiki README 예시와 같은 데이터)."""
    when = {"all": [{"path": "/category", "op": "eq", "value": category}]}
    profile = copy.deepcopy(dict(base))
    profile["title"] = "에이전트 아키텍처 + 위키"
    profile["cells"]["wiki"] = {
        "label": "Wiki",
        "description": "위키 읽기·쓰기",
        "x": 810,
        "y": 730,
        "zone": "runtime",
        "tone": "gold",
        "metrics": ["count", "errors"],
        "group_by": "/correlation/wiki",
        "when": when,
    }
    profile["edges"].append(
        {
            "id": "wiki_access",
            "from": "dispatch",
            "to": "wiki",
            "label": "위키 접근",
            "kind": "observed",
            "style": "request",
            "points": [[1054, 610], [1030, 610], [1030, 730], [906, 730]],
            "label_at": [968, 730],
            "metrics": ["count", "errors"],
            "when": when,
        }
    )
    profile["coverage"][SOURCE]["cells"].append("wiki")
    return profile


def _put_settings(
    client: TestClient, base: Mapping[str, Any], category: str, event_map: dict[str, Any] | None
) -> None:
    body: dict[str, Any] = client.get(f"{API}/settings").json()
    body["architecture"] = {"profiles": {PROFILE: wiki_profile(base, category)}}
    config = {"event_map": event_map} if event_map is not None else {}
    body["logs"] = {"sources": [{"id": SOURCE, "enabled": True, "config": config}]}
    res = client.put(f"{API}/settings", json=body)
    assert res.status_code == 200, res.text


def _run(client: TestClient) -> tuple[str, str, list[dict[str, Any]]]:
    created = client.post(f"{API}/wiki/wikis", json={"name": "Team Notes"})
    assert created.status_code == 201, created.text
    wiki_id = created.json()["wiki"]["id"]
    resource = {
        "id": "wiki-7r15",
        "type": load_wiki_resource_type().id,
        "name": "위키 접근",
        "config": {"wikis": [{"wiki": wiki_id, "access": ALL_OPS}]},
    }
    assert client.post(f"{API}/resources", json=resource).status_code == 201
    keeper = agent_doc("keeper", "끝", resources=[{"ref": resource["id"]}])
    keeper["backend_options"]["default"]["host_tool_calls"] = [
        {"tool": TOOLS[op], "input": data, "append": False} for op, data in _calls(wiki_id)
    ]
    assert client.post(f"{API}/agents", json=keeper).status_code == 201
    graph = {
        "id": "wiki-7r15",
        "name": "위키 칸",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "k", "type": "agent", "label": "k", "config": {"agent_ref": "keeper"}},
        ],
        "edges": [
            {
                "id": "m",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "k", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r",
                "source": {"node": "k", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }
    assert client.post(f"{API}/graphs", json=graph).status_code == 201
    started = client.post(f"{API}/runs", json={"graph_id": graph["id"], "input": {"text": "go"}})
    assert started.status_code == 202, started.text
    snap = wait_run(client, started.json()["id"], timeout=30)
    assert snap["run"]["status"] == "completed", snap["run"]
    run_id = snap["run"]["id"]
    events: list[dict[str, Any]] = []
    for _ in range(200):
        events = client.get(f"{API}/runs/{run_id}/events").json()
        if any(e["type"] in ("run.completed", "run.finished") for e in events):
            break
        time.sleep(0.05)
    return wiki_id, run_id, events


def _count(client: TestClient, **flt: Any) -> int:
    rows = client.post(
        f"{API}/logs/aggregate", json={"group_by": [], "metric": "events", "filter": flt}
    ).json()
    return int(rows[0]["value"]) if rows else 0


def _indexed(client: TestClient, run_id: str) -> None:
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
    params: dict[str, Any] = {**scope, "arch": selector["arch"], "max_seq": view["max_seq"]}
    if selector.get("arch_group") is not None:
        params["arch_group"] = selector["arch_group"]
    if selector.get("arch_sources") is not None:
        params["arch_sources"] = ",".join(selector["arch_sources"])
    return _items(client, params)


def _view(client: TestClient, scope: dict[str, Any], profile: str) -> dict[str, Any]:
    res = client.get(f"{API}/logs/architecture", params={**scope, "profile": profile})
    assert res.status_code == 200, res.text
    view: dict[str, Any] = res.json()
    assert view["profile"] == profile
    return view


def _cell(view: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in view["cells"] if c["id"] == cell_id)
    return found


@pytest.mark.parametrize(
    ("category", "renamed"),
    [("wiki", False), ("knowledge", True)],
    ids=["default-category", "renamed-knowledge"],
)
def test_user_profile_wiki_cell_counts_match(tmp_path: Path, category: str, renamed: bool) -> None:
    event_map = (
        {WIKI_RULE: {**load_default_event_map().rules[WIKI_RULE], "category": category}}
        if renamed
        else None
    )
    with server(make_settings(tmp_path, options={**NO_PROJECT_GATE, **OPTIONS})) as client:
        default_id = client.get(f"{API}/architecture/profiles").json()["default_profile"]
        base = client.get(f"{API}/architecture/profiles/{default_id}").json()["profile"]
        _put_settings(client, base, category, event_map)

        wiki_id, run_id, events = _run(client)
        wiki_events = [e for e in events if e["type"].startswith("wiki.")]
        statuses = [e["payload"]["status"] for e in wiki_events]
        assert statuses == ["ok"] * 8 + ["denied"], statuses
        expected = len(wiki_events)
        _indexed(client, run_id)

        # 시험 1: 로그 색인 — 범주·문서 표지(본문 없음)
        scope = {"scope": f"run:{run_id}"}
        logs = _items(client, {**scope, "category": category})
        assert len(logs) == expected
        assert {d["kind"] for e in logs for d in e["documents"]} == {"wiki"}
        assert all(BODY not in json.dumps(e, ensure_ascii=False) for e in logs)
        docs = sorted(
            (d["path"], d["action"]) for e in logs for d in e["documents"] if d["action"] != "read"
        )
        assert (f"{wiki_id}/임시/메모", "moved_from") in docs
        assert (f"{wiki_id}/임시/옮김", "moved_to") in docs
        assert sum(1 for e in logs if not e["documents"]) == 2  # 검색·목록

        view = _view(client, scope, PROFILE)
        cell = _cell(view, "wiki")
        assert cell["status"] == "observed"
        assert cell["metrics"]["count"]["value"] == expected
        assert cell["metrics"]["errors"]["value"] == 0  # denied = block(판정이지 오류가 아님)
        assert len(_picked(client, scope, view, cell["selector"])) == expected
        groups = {g["key"]: g["metrics"]["count"]["value"] for g in cell.get("groups") or []}
        assert groups[wiki_id] == expected - 1  # 접근 밖 위키 하나
        assert sum(groups.values()) == expected
        [edge] = [e for e in view["edges"] if e["id"] == "wiki_access"]
        assert edge["metrics"]["count"]["value"] == expected
        assert len(_picked(client, scope, view, edge["selector"])) == expected

        # 시험 3: 기본 프로필은 그대로 — Wiki 칸이 없고 위키 이벤트는 분류 안 됨
        default_view = _view(client, scope, default_id)
        packaged = load_default_profiles()[default_id]
        assert [c["id"] for c in default_view["cells"]] == list(packaged.cells)
        assert "wiki_access" not in {e["id"] for e in default_view["edges"]}
        uids = {e["uid"] for e in logs}
        for target in default_view["cells"]:
            picked = {e["uid"] for e in _picked(client, scope, default_view, target["selector"])}
            assert not (picked & uids), target["id"]
        counts = {c["id"]: c["metrics"].get("count") for c in default_view["cells"]}
        assert counts == {
            c["id"]: c["metrics"].get("count") for c in view["cells"] if c["id"] != "wiki"
        }


def test_turning_off_default_wiki_rule_keeps_events_as_other(tmp_path: Path) -> None:
    # 시험 4: 설정 event_map에서 기본 규칙을 빈 규칙으로 끈다(대응표 데이터 없이도 이벤트는 남음)
    with server(make_settings(tmp_path, options={**NO_PROJECT_GATE, **OPTIONS})) as client:
        default_id = client.get(f"{API}/architecture/profiles").json()["default_profile"]
        base = client.get(f"{API}/architecture/profiles/{default_id}").json()["profile"]
        _put_settings(client, base, "wiki", {WIKI_RULE: {}})
        _wiki_id, run_id, events = _run(client)
        wiki_types = [e["type"] for e in events if e["type"].startswith("wiki.")]
        assert len(wiki_types) == 9
        _indexed(client, run_id)
        scope = {"scope": f"run:{run_id}"}
        logs = _items(client, scope)
        wiki_logs = [e for e in logs if e["title"].startswith("wiki.")]
        assert sorted(e["title"] for e in wiki_logs) == sorted(wiki_types)
        assert {e["category"] for e in wiki_logs} == {"other"}
        assert all(not e["documents"] for e in wiki_logs)
        assert _items(client, {**scope, "category": "wiki"}) == []
        assert {"llm", "tool_call", "system"} <= {e["category"] for e in logs}
        cell = _cell(_view(client, scope, PROFILE), "wiki")
        assert (cell["metrics"]["count"] or {}).get("value") in (0, None)
