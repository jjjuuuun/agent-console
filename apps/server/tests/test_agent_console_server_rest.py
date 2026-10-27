"""§5.2 Phase 1 REST 전 엔드포인트(fake 백엔드)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import CONTRACTS_VERSION
from agent_console_server.testing import (
    API,
    TEST_TOKEN,
    agent_doc,
    make_settings,
    seed,
    server,
    team_graph,
    wait_run,
)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with server(make_settings(tmp_path)) as c:
        yield c


def test_agent_console_server_bootstrap(client: TestClient) -> None:
    body = client.get(f"{API}/bootstrap").json()
    assert body["token"] == TEST_TOKEN
    assert body["contracts_version"] == CONTRACTS_VERSION
    assert body["server_version"]


def test_agent_console_server_descriptors(client: TestClient) -> None:
    node_types = {d["id"] for d in client.get(f"{API}/node-types").json()}
    # 설치된 플러그인(entry point)에서 온 것. 서버 코드에는 목록이 없다.
    assert {"agent", "user", "resource"} <= node_types
    assert not {"input", "router", "output"} & node_types  # 보류(등록 해제)
    edge_types = {d["id"] for d in client.get(f"{API}/edge-types").json()}
    assert {"subagent", "handoff", "data", "uses", "message", "reply"} <= edge_types
    backends = {d["id"] for d in client.get(f"{API}/backends").json()}
    assert {"fake-agent", "claude-agent-sdk"} <= backends
    assert client.get(f"{API}/backends/fake-agent/models").json() == []
    missing = client.get(f"{API}/backends/nope/models")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_agent_console_server_resolve_ports(client: TestClient) -> None:
    agent_config = team_graph()["nodes"][1]["config"]
    ports = client.post(f"{API}/node-types/agent/ports", json={"config": agent_config}).json()
    assert [p["name"] for p in ports["outputs"]] == ["out", "delegates"]
    assert client.post(f"{API}/node-types/nope/ports", json={}).status_code == 404
    # 잘못된 config의 포트 계산도 노드 타입이 정한다(고정 포트). 서버는 그대로 전달.
    assert client.post(f"{API}/node-types/user/ports", json={"config": {}}).status_code == 200


def test_agent_console_server_agents_crud(client: TestClient) -> None:
    created = client.post(f"{API}/agents", json=agent_doc("a1", "hi"))
    assert created.status_code == 201
    assert created.headers["etag"]
    assert client.post(f"{API}/agents", json=agent_doc("a1", "hi")).status_code == 409
    assert [a["id"] for a in client.get(f"{API}/agents").json()] == ["a1"]
    updated = client.put(f"{API}/agents/a1", json={**agent_doc("a1", "hi"), "name": "새 이름"})
    assert updated.json()["name"] == "새 이름"
    mismatch = client.put(f"{API}/agents/a1", json=agent_doc("other", "hi"))
    assert mismatch.status_code == 400
    assert client.get(f"{API}/agents/a1").json()["name"] == "새 이름"
    assert client.delete(f"{API}/agents/a1").status_code == 204
    assert client.get(f"{API}/agents/a1").status_code == 404


def test_agent_console_server_graph_crud_and_versions(client: TestClient) -> None:
    created = seed(client)
    version = created["version_hash"]
    assert created["graph"]["id"] == "flow"
    summaries = client.get(f"{API}/graphs").json()
    assert summaries[0]["node_count"] == 3
    assert summaries[0]["edge_count"] == 4
    got = client.get(f"{API}/graphs/flow")
    assert got.headers["etag"] == f'"{version}"'
    assert client.post(f"{API}/graphs", json=team_graph()).json()["error"]["code"] == (
        "already_exists"
    )

    doc = team_graph()
    doc["name"] = "바뀐 이름"
    no_match = client.put(f"{API}/graphs/flow", json=doc)
    assert no_match.status_code == 428
    assert no_match.json()["error"]["code"] == "version_required"
    stale = client.put(f"{API}/graphs/flow", json=doc, headers={"If-Match": "0" * 64})
    assert stale.status_code == 412
    details = stale.json()["error"]["details"]
    assert details["current_version_hash"] == version
    assert details["node_count"] == 3
    saved = client.put(f"{API}/graphs/flow", json=doc, headers={"If-Match": f'"{version}"'})
    assert saved.status_code == 200
    new_version = saved.json()["version_hash"]
    assert new_version != version

    versions = client.get(f"{API}/graphs/flow/versions").json()
    assert {v["version_hash"] for v in versions} >= {version, new_version}
    assert all(v.get("content") is None for v in versions)
    old = client.get(f"{API}/graphs/flow/versions/{version}").json()
    assert old["content"]["name"] == "테스트 흐름"
    assert client.get(f"{API}/graphs/flow/versions/{'f' * 64}").status_code == 404

    assert client.delete(f"{API}/graphs/flow", headers={"If-Match": version}).status_code == 412
    assert client.delete(f"{API}/graphs/flow").status_code == 204
    assert client.get(f"{API}/graphs/flow").status_code == 404
    # 삭제해도 버전 이력은 남는다(과거 Run의 graph_version 조회)
    assert client.get(f"{API}/graphs/flow/versions/{version}").status_code == 200


def test_agent_console_server_graph_body_validation(client: TestClient) -> None:
    bad = client.post(f"{API}/graphs", json={"id": "bad id!", "name": ""})
    assert bad.status_code == 422
    error = bad.json()["error"]
    assert error["code"] == "validation_failed"
    paths = {i["path"] for i in error["details"]["issues"]}
    assert {"/id", "/name"} <= paths
    broken = client.post(
        f"{API}/graphs", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert broken.status_code == 400
    assert broken.json()["error"]["code"] == "bad_request"


def test_agent_console_server_validate(client: TestClient) -> None:
    seed(client)
    assert client.post(f"{API}/graphs/flow/validate").json() == []
    doc = team_graph()
    doc["nodes"][1]["config"] = {"agent_ref": "ghost"}
    doc["nodes"].append({"id": "x", "type": "no-such-type"})
    issues = client.post(f"{API}/graphs/flow/validate", json=doc).json()
    codes = {i["code"] for i in issues}
    assert "unknown_node_type" in codes
    assert any(i.get("node_id") == "a" for i in issues)  # agent_ref 검증(AGENT_LOOKUP 주입)
    assert client.post(f"{API}/graphs/none/validate").status_code == 404


def test_agent_console_server_validate_agent_config(client: TestClient) -> None:
    """에이전트 노드 의미 검증(정의 존재·노드 설정 백엔드)이 조립된 앱의 검증 경로에서 잡힌다."""
    seed(client)
    doc = team_graph()
    doc["nodes"][2]["config"] = {"agent_ref": "ghost", "settings": {"backend": "no-such"}}
    issues = client.post(f"{API}/graphs/flow/validate", json=doc).json()
    found = {(i["code"], i["path"]) for i in issues if i["node_id"] == "b"}
    assert found == {
        ("agent.not_found", "/agent_ref"),
        ("agent.unknown_backend", "/settings/backend"),
    }


def test_agent_console_server_runs(client: TestClient) -> None:
    seed(client)
    created = client.post(
        f"{API}/runs", json={"graph_id": "flow", "input": {"request": "? 짧게"}, "origin": "web"}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    assert run["origin"] == "web"
    snap = wait_run(client, run["id"])
    assert snap["run"]["status"] == "completed"
    assert snap["last_seq"] > 0
    by_node = {nr["node_id"]: nr for nr in snap["node_runs"]}
    assert set(by_node) == {"a", "b"}  # 사용자 노드는 흐름 입력이 없어 실행되지 않는다
    assert by_node["a"]["outputs"] == {"out": "빠른 답: ? 짧게"}
    assert by_node["b"]["outputs"] == {"out": "깊은 답: 빠른 답: ? 짧게"}

    listed = client.get(f"{API}/runs", params={"graph_id": "flow"}).json()
    assert [r["id"] for r in listed] == [run["id"]]
    assert client.get(f"{API}/runs", params={"graph_id": "other"}).json() == []
    assert client.post(f"{API}/runs/{run['id']}/cancel").json()["status"] == "completed"
    assert client.post(f"{API}/runs/nope/cancel").status_code == 404
    assert client.get(f"{API}/runs/nope").status_code == 404

    by_version = client.post(
        f"{API}/runs",
        json={"graph_id": "flow", "version_hash": run["graph_version"], "input": {"request": "x"}},
    )
    assert by_version.status_code == 202
    assert by_version.json()["origin"] == "api"
    wait_run(client, by_version.json()["id"])


def test_agent_console_server_run_invalid_graph(client: TestClient) -> None:
    doc = team_graph("broken")
    doc["nodes"].append({"id": "x", "type": "no-such-type"})
    assert client.post(f"{API}/graphs", json=doc).status_code == 201  # 초안 저장은 허용
    response = client.post(f"{API}/runs", json={"graph_id": "broken", "input": {}})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert any(i["code"] == "unknown_node_type" for i in error["details"]["issues"])
    assert client.post(f"{API}/runs", json={"graph_id": "none"}).status_code == 404


def test_agent_console_server_cancel_running(client: TestClient) -> None:
    slow = agent_doc("slow", "느린 답 " * 50)
    slow["backend_options"]["delay_ms"] = 200
    slow["backend_options"]["chunk_chars"] = 4
    client.post(f"{API}/agents", json=slow)
    client.post(f"{API}/agents", json=agent_doc("fast", "x"))
    client.post(f"{API}/graphs", json=team_graph())
    run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "깊게"}}).json()
    client.post(f"{API}/runs/{run['id']}/cancel")
    assert wait_run(client, run["id"])["run"]["status"] == "cancelled"


def test_agent_console_server_settings(client: TestClient) -> None:
    default = client.get(f"{API}/settings")
    assert default.status_code == 200
    assert default.json() == {}  # 파일 없음 → 원문 없음(기본값은 유효 설정 API가)
    assert "etag" not in default.headers
    saved = client.put(
        f"{API}/settings", json={"default_entry": "flow", "default_backend": "fake-agent"}
    )
    assert saved.status_code == 200
    etag = saved.headers["etag"]
    assert client.get(f"{API}/settings").json()["default_backend"] == "fake-agent"
    stale = client.put(f"{API}/settings", json={}, headers={"If-Match": "nope"})
    assert stale.status_code == 412
    assert client.put(f"{API}/settings", json={}, headers={"If-Match": etag}).status_code == 200


def test_agent_console_server_default_backend_from_settings(client: TestClient) -> None:
    """에이전트에 백엔드가 없으면 설정의 default_backend(DEFAULT_BACKEND 서비스)를 쓴다."""
    for agent_id in ("fast", "slow"):
        doc = agent_doc(agent_id, "기본 백엔드로 실행")
        doc.pop("backend")
        client.post(f"{API}/agents", json=doc)
    client.post(f"{API}/graphs", json=team_graph())
    # 기본 백엔드 없음: 실행을 만들지 않고 422 backend.unresolved(5.2R.4, 실패 기록 없음)
    blocked = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "?"}})
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "backend.unresolved"
    assert client.get(f"{API}/runs").json() == []
    client.put(f"{API}/settings", json={"default_backend": "fake-agent"})
    run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "?"}}).json()
    assert wait_run(client, run["id"])["run"]["status"] == "completed"


def test_agent_console_server_unknown_api_path_is_json_404(client: TestClient) -> None:
    response = client.get(f"{API}/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
