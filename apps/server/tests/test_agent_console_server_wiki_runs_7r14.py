"""7R.14: 설치된 서버에서 위키·실행 연동(`link-wiki-runs`) 모듈 매트릭스(design §7R.4 끄기 표).

- 전부 켜짐: 연동이 active·웹 역할 `wiki:runs`, 위키 `capabilities.runs` 참, 위키 리소스를 붙인
  에이전트가 fake-agent 실행에서 도구로 쓰고 읽는다(`wiki.*` 이벤트, 본문 없음), 위키 변경 조회
  `author_run`에 쓴 주체(실행·에이전트 이름)가 보인다.
- `mod-wiki` 끔(연동 unsatisfied)·연동 끔: 실행은 정상, "적용하지 못한 칸" 경고(R13.5) 1건, 연동을
  끄면 `capabilities.runs` 거짓.

위키 규칙·위키는 테스트 안에서 REST로 만든다. 리소스 종류 id·칸 이름·도구 이름은 패키지·계약
데이터에서 읽는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.wiki import wiki_access_defaults
from agent_console_link_wiki_runs import load_wiki_resource_type, wiki_slot
from agent_console_server.testing import API, agent_doc, make_settings, server, wait_run

# 프로젝트와 무관한 실행 테스트: link-projects-runs의 `require_project`를 끈다(메모리 연동 시험과
# 같다).
NO_PROJECT_GATE: dict[str, dict[str, Any]] = {"link-projects-runs": {"require_project": False}}

LINK = "link-wiki-runs"
RTYPE = load_wiki_resource_type()
TOOLS = {op: t["name"] for op, t in wiki_access_defaults()["tools"].items()}
BODY = "결정: 응답 형식은 JSON v2"
QUIET = {
    "mod-logs": {"startup_scan": False, "scan_interval_seconds": 0},
    "mod-wiki": {"scan_interval_seconds": 0},
}


def _seed(client: Any, *, wiki: bool = True) -> str:
    wiki_id = ""
    if wiki:
        created = client.post(f"{API}/wiki/wikis", json={"name": "Team Notes"})
        assert created.status_code == 201, created.text
        wiki_id = created.json()["wiki"]["id"]
    resource = {
        "id": "wiki-rw",
        "type": RTYPE.id,
        "name": "위키 접근",
        "config": {"wikis": [{"wiki": wiki_id or "team-notes", "access": ["read", "write"]}]},
    }
    assert client.post(f"{API}/resources", json=resource).status_code == 201
    calls = [
        {"tool": TOOLS["write"], "input": {"path": "결정/형식", "content": BODY}, "append": False},
        {"tool": TOOLS["read"], "input": {"path": "결정/형식"}, "append": False},
    ]
    keeper = agent_doc("keeper", "$host_1_status|$host_2", resources=[{"ref": "wiki-rw"}])
    keeper["name"] = "위키 관리자"
    keeper["backend_options"]["default"]["host_tool_calls"] = calls
    assert client.post(f"{API}/agents", json=keeper).status_code == 201
    graph = {
        "id": "g1",
        "name": "팀",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "k", "type": "agent", "label": "k", "config": {"agent_ref": "keeper"}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "k", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r1",
                "source": {"node": "k", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }
    assert client.post(f"{API}/graphs", json=graph).status_code == 201
    return wiki_id


def _run(client: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    created = client.post(f"{API}/runs", json={"graph_id": "g1", "input": {"text": "시작"}})
    assert created.status_code == 202, created.text
    run = wait_run(client, created.json()["id"])["run"]
    events: list[dict[str, Any]] = client.get(f"{API}/runs/{run['id']}/events").json()
    return run, events


def _slot_warnings(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e["payload"]["details"]
        for e in events
        if e["type"] == "log.warning"
        and e["payload"]["details"].get("code") == "resource.slot_unsupported"
    ]


def test_all_on_agent_uses_wiki_tools(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, options={**NO_PROJECT_GATE, **QUIET})) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos[LINK]["status"] == "active"
        assert infos[LINK]["web_roles"] == ["wiki:runs"]
        assert RTYPE.id in {t["id"] for t in client.get(f"{API}/resource-types").json()}
        assert client.get(f"{API}/wiki/info").json()["capabilities"]["runs"] is True
        wiki_id = _seed(client)
        run, events = _run(client)
        assert run["status"] == "completed", run
        found = [e for e in events if e["type"].startswith("wiki.")]
        assert [(e["type"], e["payload"]["status"]) for e in found] == [
            ("wiki.write", "ok"),
            ("wiki.read", "ok"),
        ]
        assert all(BODY not in json.dumps(e["payload"], ensure_ascii=False) for e in found)
        assert _slot_warnings(events) == []
        page = client.get(f"{API}/wiki/changes", params={"author_run": run["id"]}).json()
        [item] = page["items"]
        assert (item["wiki"], item["path"]) == (wiki_id, "결정/형식")
        assert (item["author"]["run_id"], item["author"]["label"]) == (run["id"], "위키 관리자")


@pytest.mark.parametrize(("off", "state"), [("mod-wiki", "unsatisfied"), (LINK, "disabled")])
def test_off_runs_normally_with_one_warning(tmp_path: Path, off: str, state: str) -> None:
    settings = make_settings(
        tmp_path, options={**NO_PROJECT_GATE, **QUIET}, modules={"disabled": [off]}
    )
    with server(settings) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses[LINK] == state
        wiki_on = off != "mod-wiki"
        if wiki_on:
            assert client.get(f"{API}/wiki/info").json()["capabilities"]["runs"] is False
        _seed(client, wiki=wiki_on)  # 리소스 종류는 연동을 꺼도 등록돼 있다
        run, events = _run(client)
        assert run["status"] == "completed", run
        assert [e for e in events if e["type"].startswith("wiki.")] == []
        [warning] = _slot_warnings(events)
        assert (warning["slot"], warning["resources"]) == (wiki_slot(RTYPE), ["wiki-rw"])
