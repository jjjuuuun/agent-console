"""5.5R.7 수집 보강: fake 실행 기록의 새 필드가 `platform-runs` 출처로 색인된다.

design §5.5R.1.

서버를 띄워(포트 없음, TestClient) 팀 구성 하나를 fake 백엔드로 실행한다.
사용자 → 리더 lead ⇲(독립 위임 `delegate`) 팀원 m1. lead에는 본문이 있는 rule 리소스를
붙이고 fake 규칙의 `llm_duration_ms`를 준다. 실행 기록과 로그 색인에서 확인한다.

- C1 `agent.context_prepared`: 리소스 id·종류·바이트 수·sha256·조각 수만 있고 본문·비밀은 없다.
- C2 `agent.usage.duration_ms` → 시작(inferred)·끝 두 로그 이벤트.
- C7 호출 NodeRun `node.started`·`node.completed` payload `tool_use_id` = 위임자의 위임 도구
  호출 id → 로그 근거 `correlation.tool_use_id`. 스케줄 실행(lead)의 `node.started`는 `to`가
  비고 호출(m1)만 찬다.
- C4 MCP 서버 키(5.5R.7 QA 후속): lead 관측 설정 `mcp`를 켜고 fake 규칙 `observe`로 MCP 호출
  (`mcp.call_started`·`mcp.call_completed`, 서버 `docs`)을 흉내 내면 색인의 `correlation.mcp_server`
  까지 이어진다.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from agent_console_server.testing import (
    API,
    SECRET_VALUE,
    agent_doc,
    make_settings,
    server,
    wait_run,
)

BODY = "규칙 본문 BODY-MARKER-7f3 — 이 글은 이벤트에 실리면 안 된다"
OPTIONS: dict[str, dict[str, Any]] = {
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
}


def _edge(
    eid: str, src: tuple[str, str], dst: tuple[str, str], kind: str, **config: Any
) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src[0], "port": src[1]},
        "target": {"node": dst[0], "port": dst[1]},
        "kind": kind,
        "config": config,
    }


GRAPH = {
    "id": "collect-55r7",
    "name": "수집 보강",
    "inputs": [{"name": "request"}],
    "nodes": [
        {"id": "you", "type": "user", "label": "나"},
        {"id": "lead", "type": "agent", "label": "lead", "config": {"agent_ref": "lead"}},
        {"id": "m1", "type": "agent", "label": "m1", "config": {"agent_ref": "member"}},
    ],
    "edges": [
        _edge("m-lead", ("you", "says"), ("lead", "in"), "message", input_key="request"),
        _edge("lead->m1", ("lead", "delegates"), ("m1", "delegated"), "delegate"),
        _edge("a-lead", ("lead", "out"), ("you", "hears"), "reply"),
    ],
}


MCP_TOOL = "mcp__docs__lookup"
MCP_OBSERVE: list[dict[str, Any]] = [
    {
        "type": event_type,
        "after": "tool",
        "payload": {"server": "docs", "tool": "lookup", "tool_use_id": "$session_id:tool0"},
    }
    for event_type in ("mcp.call_started", "mcp.call_completed")
]
"""fake 관측 규칙: 첫 도구 호출 뒤 MCP 호출 시작·완료(서버 docs)."""


def _etag(response: Any) -> str:
    return str(response.headers["ETag"]).strip('"')


def _log_events(client: Any, run_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for _ in range(100):
        scan = client.post(f"{API}/logs/scan", json={"source_ids": ["platform-runs"]})
        assert scan.status_code == 202, scan.text
        page = client.get(
            f"{API}/logs/events", params={"source": "platform-runs", "run_id": run_id, "limit": 500}
        ).json()
        items = page.get("items", [])
        if any(e["category"] == "usage" for e in items) and any(
            e["category"] == "context" for e in items
        ):
            return items
        time.sleep(0.1)
    raise AssertionError(f"platform-runs 색인이 끝나지 않았다: {len(items)}개")


def test_fake_run_new_fields_are_recorded_and_indexed(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, options=OPTIONS)
    with server(settings) as client:
        made = client.post(
            f"{API}/resources",
            json={"id": "house-rules", "type": "rule", "name": "규칙", "config": {}},
        )
        assert made.status_code == 201, made.text
        body = f"{BODY}\n비밀 {SECRET_VALUE}\n".encode()
        put = client.put(
            f"{API}/resources/house-rules/content",
            content=body,
            headers={"If-Match": _etag(made), "Content-Type": "text/markdown"},
        )
        assert put.status_code == 200, put.text
        lead = agent_doc(
            "lead",
            "리더<$host_1>",
            resources=[{"ref": "house-rules"}],
        )
        lead["backend_options"]["default"].update(
            {
                "llm_duration_ms": 1234,
                "host_tool_calls": [
                    {"tool": "delegate", "input": {"target": "m1", "task": "할 일"}}
                ],
                "tool_calls": [{"name": MCP_TOOL, "input": {"q": "x"}}],
                "observe": MCP_OBSERVE,
            }
        )
        lead["observe"] = {"mcp": True}
        for doc in (lead, agent_doc("member", "팀원($prompt)")):
            assert client.post(f"{API}/agents", json=doc).status_code == 201, doc["id"]
        assert client.post(f"{API}/graphs", json=GRAPH).status_code == 201
        started = client.post(
            f"{API}/runs", json={"graph_id": GRAPH["id"], "input": {"request": "go"}}
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["id"]
        snap = wait_run(client, run_id, timeout=30)
        assert snap["run"]["status"] == "completed", snap["run"]

        events = client.get(f"{API}/runs/{run_id}/events").json()
        events = events.get("items", events) if isinstance(events, dict) else events

        assert isinstance(events, list), events
        # C1: 리더 맥락 구성 — 표지만
        [ctx_event] = [
            e
            for e in events
            if e["type"] == "agent.context_prepared" and e["node_path"] == ["lead"]
        ]
        payload = ctx_event["payload"]
        assert payload["resources"] == [
            {
                "id": "house-rules",
                "kind": "rule",
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        ]
        assert payload["fragments"] == 1
        dumped = json.dumps(ctx_event, ensure_ascii=False)
        assert "BODY-MARKER-7f3" not in dumped
        assert SECRET_VALUE not in dumped

        # C2: 마지막 사용량에 설정한 소요
        lead_usage = [
            e for e in events if e["type"] == "agent.usage" and e["node_path"] == ["lead"]
        ]
        assert lead_usage[-1]["payload"]["duration_ms"] == 1234

        # C7: 호출 NodeRun의 node.* payload tool_use_id = 위임 도구 호출 id
        [call] = [
            e
            for e in events
            if e["type"] == "agent.tool_call" and e["payload"]["name"] == "delegate"
        ]
        tool_use_id = call["payload"]["tool_use_id"]
        m1_nodes = {
            e["type"]: e["payload"]
            for e in events
            if e["node_path"] == ["lead", "m1"] and e["type"].startswith("node.")
        }
        assert m1_nodes["node.started"]["tool_use_id"] == tool_use_id
        assert m1_nodes["node.completed"]["tool_use_id"] == tool_use_id
        lead_started = next(
            e for e in events if e["type"] == "node.started" and e["node_path"] == ["lead"]
        )
        assert lead_started["payload"]["tool_use_id"] is None

        # platform-runs 색인
        logs = _log_events(client, run_id)
        [context_log] = [
            e for e in logs if e["category"] == "context" and e["node_path"] == ["lead"]
        ]
        assert context_log["title"] == "맥락 구성"
        detail = client.get(f"{API}/logs/events/{context_log['uid']}").json()
        dumped = json.dumps(detail, ensure_ascii=False)
        assert "BODY-MARKER-7f3" not in dumped
        assert SECRET_VALUE not in dumped
        assert "house-rules" in dumped

        # 5.7R.7(M-2): 규칙 리소스 → 목록 본문 문서(대응표 each) → 기본 구조도 Rules 칸이 관측이고
        # 칸을 눌렀을 때 이벤트 표 수 = 칸 수
        assert context_log["documents"] == [
            {"path": "house-rules", "kind": "rules", "action": "read"}
        ]
        scope = {"source": "platform-runs", "run_id": run_id}
        view = client.get(f"{API}/logs/architecture", params=scope)
        assert view.status_code == 200, view.text
        rules = next(c for c in view.json()["cells"] if c["id"] == "rules")
        assert rules["status"] == "observed"
        assert rules["metrics"]["count"]["value"] == 1
        selector = rules["selector"]
        click: dict[str, Any] = {
            **scope,
            "arch": selector["arch"],
            "max_seq": view.json()["max_seq"],
            "limit": 500,
        }
        if selector.get("arch_sources") is not None:
            click["arch_sources"] = ",".join(selector["arch_sources"])
        picked = client.get(f"{API}/logs/events", params=click)
        assert picked.status_code == 200, picked.text
        assert [e["uid"] for e in picked.json()["items"]] == [context_log["uid"]]

        usage = [
            e
            for e in logs
            if e["category"] == "usage"
            and e["node_path"] == ["lead"]
            and e["stage"] in ("start", "complete")
        ]
        assert [e["stage"] for e in usage] == ["start", "complete"]
        assert all(abs(e["duration_ms"] - 1234) < 1 for e in usage), usage
        assert usage[0]["evidence"] == "inferred"

        def started_log(path: list[str]) -> dict[str, Any]:
            return next(
                e
                for e in logs
                if e["node_path"] == path
                and e["category"] == "agent"
                and e["stage"] == "info"
                and e["title"].endswith("running")
            )

        lead_log, m1_log = started_log(["lead"]), started_log(["lead", "m1"])
        assert (lead_log["from"], lead_log["to"], lead_log["via"]) == ([], [], "")
        assert (m1_log["from"], m1_log["to"], m1_log["via"]) == (["lead"], ["m1"], "delegate")
        assert m1_log["correlation"]["tool_use_id"] == tool_use_id
        [call_log] = [e for e in logs if e["call_id"] == tool_use_id and e["stage"] == "start"]
        assert call_log["tool"] == "delegate"

        # C4: fake MCP 호출 → 실행 이벤트 payload server → 색인 근거 correlation.mcp_server
        mcp_events = [
            e for e in events if e["type"].startswith("mcp.call_") and e["node_path"] == ["lead"]
        ]
        assert [e["payload"]["server"] for e in mcp_events] == ["docs", "docs"]
        mcp_logs = [e for e in logs if e["category"] == "mcp" and e["node_path"] == ["lead"]]
        assert [e["stage"] for e in mcp_logs] == ["start", "complete"]
        assert {e["correlation"].get("mcp_server") for e in mcp_logs} == {"docs"}
        assert all(e["tool"] == MCP_TOOL for e in mcp_logs)
