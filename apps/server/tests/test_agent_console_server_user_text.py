"""사용자 문구 금지 패턴 린트(5.2R.5, ux-overhaul §1.5-C·D13): 번들 디스크립터·서버 메시지.

규칙 데이터는 ``agent_console_contracts.user_text``(패키지 데이터 한 곳)다. 계약 description은
``ac-contracts`` 테스트가 본다. 여기서는 통합 서버가 실제로 내보내는 값을 본다.

- 디스크립터: 설치된 모듈이 주는 디스크립터 목록 경로의 모든 문자열(``description`` 범위).
- 서버 메시지: 고장 난 팀 구성의 검증 이슈·실행 차단 응답·실행 실패 요약(``messages`` 범위).
  노드 id(``'n1'`` 꼴)를 문구에 넣지 않는다 — id는 ``details``·``node_id``에만.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.user_text import UserTextViolation, scan_forbidden_text
from agent_console_server.testing import API, make_settings, server, wait_run

DESCRIPTOR_PATHS = (
    "/backends",
    "/node-types",
    "/edge-types",
    "/delegation-strategies",
    "/interaction-kinds",
    "/condition-operators",
    "/resource-types",
    "/merge-strategies",
    "/exporters",
    "/resources/import/sources",
    "/modules",
    "/usage/sources",
    "/logs/sources",
    "/logs/classifiers",
    "/logs/schema",
    "/logs/taxonomy",
    "/logs/dashboard-templates",
)
"""디스크립터·번들 데이터를 주는 GET 경로(모듈이 꺼져 있으면 404 — 건너뛴다)."""

# 사용자 문구가 아닌 키(값이 id·경로·패턴·스키마 키워드 등). 문자열만 고르고 키 이름은 보지 않는다.
_NON_TEXT_KEYS = frozenset({"id", "pattern", "$ref", "path", "paths", "examples"})


def _report(found: list[UserTextViolation]) -> str:
    return "\n".join(f"{v.path}: [{v.rule}] {v.match!r} — {v.text[:100]}" for v in found)


def _texts(value: Any, at: str = "") -> list[tuple[str, str]]:
    """JSON 값의 (위치, 문자열) — 사용자 문구가 아닌 키의 값은 뺀다."""
    out: list[tuple[str, str]] = []
    if isinstance(value, str):
        out.append((at, value))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in _NON_TEXT_KEYS:
                out.extend(_texts(item, f"{at}/{key}"))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            out.extend(_texts(item, f"{at}/{i}"))
    return out


def _scan(value: Any, scope: str, at: str) -> list[UserTextViolation]:
    found: list[UserTextViolation] = []
    for path, text in _texts(value, at):
        found.extend(scan_forbidden_text(text, scope=scope, path=path))
    return found


@pytest.fixture
def client(tmp_path: Path) -> Any:
    with server(make_settings(tmp_path)) as c:
        yield c


def test_bundled_descriptors_have_no_design_numbers(client: Any) -> None:
    found: list[UserTextViolation] = []
    seen = 0
    for path in DESCRIPTOR_PATHS:
        res = client.get(f"{API}{path}")
        if res.status_code == 404:
            continue
        assert res.status_code == 200, (path, res.text)
        seen += 1
        found.extend(_scan(res.json(), "description", path))
    assert seen >= 10  # 기본 설치에서 대부분의 목록이 켜져 있다
    assert found == [], _report(found)


def _agent(agent_id: str, name: str) -> dict[str, Any]:
    return {"id": agent_id, "name": name, "backend_options": {"default": {"response": "네"}}}


def _edge(eid: str, kind: str, src: tuple[str, str], dst: tuple[str, str]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": kind,
        "source": {"node": src[0], "port": src[1]},
        "target": {"node": dst[0], "port": dst[1]},
    }


def _broken_graphs() -> list[dict[str, Any]]:
    """검증 이슈를 여럿 내는 팀 구성들(노드 id는 일부러 `n1` 꼴, label은 일부만)."""
    you = {"id": "n0", "type": "user"}
    return [
        {  # 입구·답변 없음, 도달 불가, 모르는 종류·연결, 없는 노드·포트
            "id": "broken-a",
            "name": "고장 A",
            "nodes": [
                you,
                {"id": "n1", "type": "agent", "config": {"agent_ref": "helper"}},
                {"id": "n2", "type": "agent", "config": {"agent_ref": "missing"}},
                {"id": "n3", "type": "no-such-kind"},
            ],
            "edges": [
                _edge("e1", "no-such-edge", ("n1", "out"), ("n2", "in")),
                _edge("e2", "handoff", ("n1", "out"), ("n9", "in")),
                _edge("e3", "handoff", ("n1", "nope"), ("n2", "in")),
            ],
        },
        {  # 입구·답변 없음(팀 규칙은 모르는 종류가 없을 때만 돈다)
            "id": "broken-c",
            "name": "고장 C",
            "nodes": [you, {"id": "n1", "type": "agent", "config": {"agent_ref": "helper"}}],
            "edges": [],
        },
        {  # 흐름 사이클 + 위임 순환
            "id": "broken-b",
            "name": "고장 B",
            "nodes": [
                you,
                {"id": "n1", "type": "agent", "config": {"agent_ref": "helper"}},
                {"id": "n2", "type": "agent", "config": {"agent_ref": "helper"}},
            ],
            "edges": [
                _edge("m", "message", ("n0", "says"), ("n1", "in")),
                _edge("f1", "handoff", ("n1", "out"), ("n2", "in")),
                _edge("f2", "handoff", ("n2", "out"), ("n1", "in")),
                _edge("d1", "delegate", ("n1", "delegates"), ("n2", "delegated")),
                _edge("d2", "delegate", ("n2", "delegates"), ("n1", "delegated")),
            ],
        },
    ]


def test_server_messages_name_nodes_not_ids(client: Any) -> None:
    assert client.post(f"{API}/agents", json=_agent("helper", "도우미")).status_code == 201
    found: list[UserTextViolation] = []
    codes: set[str] = set()
    for graph in _broken_graphs():
        res = client.post(f"{API}/graphs/{graph['id']}/validate", json=graph)
        assert res.status_code == 200, res.text
        issues = res.json()
        assert issues, graph["id"]
        codes |= {i["code"] for i in issues}
        for i, issue in enumerate(issues):
            # 사용자 문구만: 메시지·제안 문구·해결 버튼 문구(id는 node_id·details에 있다)
            texts = {
                "message": issue["message"],
                "suggestions": [s.get("label") for s in issue.get("suggestions") or []],
                "fix": [a["label"] for a in (issue.get("fix") or {}).get("actions", [])],
            }
            found.extend(_scan(texts, "messages", f"/{graph['id']}/{i}"))
        # 실행 차단 응답(문제 응답)
        assert client.post(f"{API}/graphs", json=graph).status_code == 201
        blocked = client.post(f"{API}/runs", json={"graph_id": graph["id"], "input": {"t": "x"}})
        assert blocked.status_code == 422, blocked.text
        error = blocked.json()["error"]
        found.extend(_scan({"message": error["message"]}, "messages", f"/{graph['id']}/run"))
    assert {"team.no_entry", "unknown_node_type", "cycle"} <= codes
    assert found == [], _report(found)


def test_run_failure_summary_names_node(client: Any) -> None:
    """실행 실패 요약(백엔드 실패)은 노드를 이름으로 부른다(label이 없으면 정의 이름)."""
    agent = {
        "id": "boom",
        "name": "터지는 도우미",
        "backend": "fake",
        "backend_options": {"default": {"response": "x", "fail": {"message": "고장"}}},
    }
    assert client.post(f"{API}/agents", json=agent).status_code == 201
    graph = {
        "id": "fails",
        "name": "실패",
        "nodes": [
            {"id": "n0", "type": "user"},
            {"id": "n1", "type": "agent", "config": {"agent_ref": "boom"}},
        ],
        "edges": [
            _edge("m", "message", ("n0", "says"), ("n1", "in")),
            _edge("r", "reply", ("n1", "out"), ("n0", "hears")),
        ],
    }
    assert client.post(f"{API}/graphs", json=graph).status_code == 201
    started = client.post(f"{API}/runs", json={"graph_id": "fails", "input": {"text": "hi"}})
    assert started.status_code == 202, started.text
    snap = wait_run(client, started.json()["id"])
    error = snap["run"]["error"]
    assert snap["run"]["status"] == "failed", snap["run"]
    assert error is not None
    assert "터지는 도우미" in error["message"], error
    assert error["details"]["node_id"] == "n1"
    assert _scan({"message": error["message"]}, "messages", "/run") == []
