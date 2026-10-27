"""5.5R.11 범위 종류 `run`·`run-tree`: fake 백엔드 위임 실행으로 범위 이벤트 수를 센다.

design §5.5R.3(X27, 켜고 끄기 표 4·5행).

서버를 띄워(포트 없음, TestClient) 팀 구성을 fake 백엔드로 실행한다.
사용자 → 중첩 팀 노드 T(자식 팀 구성: 에이전트 ca) → 리더 lead ⇲(독립 위임 `delegate`) 팀원 m1 →
사용자 답변. 루트 Run 하나와 자식 Run 하나가 생긴다(m1은 루트 Run 안 호출 NodeRun).

- `scope=run:<루트>` = 루트 Run의 플랫폼 이벤트(`run_id`)와 루트 세션들의 합집합.
  자식 Run 이벤트는 없고 위임 대상 m1의 이벤트는 있다.
- `scope=run-tree:<루트>` = 위 + 자식 Run 이벤트. 수 = 두 Run 수의 합.
- `link-logs-runs`를 끄면 `scope=run:`·`run-tree:`는 422, 세션 범위 질의는 그대로.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, agent_doc, make_settings, server, wait_run

OPTIONS: dict[str, dict[str, Any]] = {
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
}
SOURCE = "platform-runs"


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
        "config": {},
    }


def _node(node_id: str, type: str = "agent", **config: Any) -> dict[str, Any]:
    return {"id": node_id, "type": type, "label": node_id, "config": config}


CHILD = {
    "id": "child-55r11",
    "name": "자식 팀",
    "nodes": [_node("you", "user"), _node("ca", agent_ref="c-agent")],
    "edges": [
        _edge("m-ca", "you", "says", "ca", "in", "message"),
        _edge("a-ca", "ca", "out", "you", "hears", "reply"),
    ],
}

ROOT = {
    "id": "scope-55r11",
    "name": "실행 범위",
    "nodes": [
        _node("you", "user"),
        _node("T", "team", team_ref=CHILD["id"]),
        _node("lead", agent_ref="lead"),
        _node("m1", agent_ref="member"),
    ],
    "edges": [
        _edge("m-T", "you", "says", "T", "in", "message"),
        _edge("h1", "T", "out", "lead", "in", "handoff"),
        _edge("lead->m1", "lead", "delegates", "m1", "delegated", "delegate"),
        _edge("a-lead", "lead", "out", "you", "hears", "reply"),
    ],
}


def _agents() -> list[dict[str, Any]]:
    lead = agent_doc("lead", "리더<$host_1>")
    lead["backend_options"]["default"]["host_tool_calls"] = [
        {"tool": "delegate", "input": {"target": "m1", "task": "할 일"}}
    ]
    return [agent_doc("c-agent", "자식($prompt)"), lead, agent_doc("member", "팀원($prompt)")]


def _items(client: Any, **params: Any) -> list[dict[str, Any]]:
    response = client.get(f"{API}/logs/events", params={"limit": 1000, **params})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _count(client: Any, **flt: Any) -> int:
    response = client.post(
        f"{API}/logs/aggregate", json={"group_by": [], "metric": "events", "filter": flt}
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    return int(rows[0]["value"]) if rows else 0


def _indexed(client: Any, run_ids: list[str]) -> dict[str, int]:
    """두 번 연속 같은 수가 나올 때까지 platform-runs를 수집한다."""
    last: dict[str, int] | None = None
    for _ in range(100):
        assert client.post(f"{API}/logs/scan", json={"source_ids": [SOURCE]}).status_code == 202
        counts = {rid: _count(client, run_id=[rid], source=[SOURCE]) for rid in run_ids}
        if all(counts.values()) and counts == last:
            return counts
        last = counts
        time.sleep(0.1)
    raise AssertionError(f"platform-runs 색인이 끝나지 않았다: {last}")


def _run(client: Any) -> tuple[str, str]:
    for body in _agents():
        assert client.post(f"{API}/agents", json=body).status_code == 201, body["id"]
    for graph in (CHILD, ROOT):
        assert client.post(f"{API}/graphs", json=graph).status_code == 201, graph["id"]
    started = client.post(f"{API}/runs", json={"graph_id": ROOT["id"], "input": {"text": "hi"}})
    assert started.status_code == 202, started.text
    root_id = started.json()["id"]
    snap = wait_run(client, root_id, timeout=30)
    assert snap["run"]["status"] == "completed", snap["run"]
    [child] = snap["children"]
    return root_id, child["id"]


def test_run_and_run_tree_scope_counts_from_fake_delegation(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, options=OPTIONS)) as client:
        root_id, child_id = _run(client)
        counts = _indexed(client, [root_id, child_id])

        run_items = _items(client, scope=f"run:{root_id}")
        tree_items = _items(client, scope=f"run-tree:{root_id}")
        # 이 서버에는 외부 세션 로그가 없으므로 범위 = 플랫폼 이벤트(세션도 같은 이벤트를 가리킨다)
        assert {e["run_id"] for e in run_items} == {root_id}
        assert len(run_items) == counts[root_id]
        assert {e["run_id"] for e in tree_items} == {root_id, child_id}
        assert len(tree_items) == counts[root_id] + counts[child_id]
        # 집계도 같은 범위로 같은 수(구조도·이벤트 표가 같은 범위를 쓴다)
        assert _count(client, scope=f"run:{root_id}") == len(run_items)
        assert _count(client, scope=f"run-tree:{root_id}") == len(tree_items)
        # 위임 대상 m1(호출 NodeRun)은 루트 Run 범위 안, 자식 팀 ca는 트리 범위에만
        paths = {tuple(e["node_path"]) for e in run_items}
        assert ("lead", "m1") in paths
        assert not any(e["node_path"][:1] == ["ca"] for e in run_items)
        assert any(e["run_id"] == child_id and e["node_path"][:1] == ["ca"] for e in tree_items)
        # 자식에서 시작한 트리는 자식 하나
        assert _count(client, scope=f"run-tree:{child_id}") == counts[child_id]
        # 다른 필터와 AND
        thread = next(e["thread"] for e in run_items if e["node_path"] == ["lead", "m1"])
        delegated = _items(client, scope=f"run:{root_id}", thread=thread)
        assert delegated
        assert len(delegated) < len(run_items)
        assert all(e["thread"] == thread for e in delegated)
        # 기존 세션 로그 탭은 그대로(외부 세션 이벤트만 — 여기는 없음)
        tab = client.get(f"{API}/runs/{root_id}/logs").json()
        assert (tab["items"], tab["total"]) == ([], 0)
        missing = client.get(f"{API}/logs/events", params={"scope": "run:nope"})
        assert missing.status_code == 422
        assert missing.json()["error"]["details"]["path"] == "scope"


def test_disabled_link_logs_runs_rejects_run_scopes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, options=OPTIONS, modules={"disabled": ["link-logs-runs"]})
    with server(settings) as client:
        for scope in ("run:r1", "run-tree:r1"):
            response = client.get(f"{API}/logs/events", params={"scope": scope})
            assert response.status_code == 422, scope
            assert response.json()["error"]["details"]["path"] == "scope"
        assert client.get(f"{API}/logs/events", params={"session": "s1"}).status_code == 200
        schema = client.get(f"{API}/logs/schema").json()
        assert "scope" in {f["id"] for f in schema["filters"]}
