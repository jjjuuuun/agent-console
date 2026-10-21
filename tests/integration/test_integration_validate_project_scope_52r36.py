"""5.2R.36 결함 B: 팀 구성 검증(`POST /graphs/{id}/validate`)에 프로젝트 범위 경고가 붙는다.

- 공용 팀 g-shared가 alpha 전용 에이전트 pa-2를 쓰면 검증 결과에 `project.shared_uses_project`
  경고와 제안 `project.move_to_shared`가 온다(`POST /projects/scope-issues`와 같은 코드).
- 프로젝트 모듈(`mod-projects`)을 끄면 검증 결과는 엔진 + 팀 규칙 그대로(범위 경고 없음)다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import KnownIssueCodes, KnownSuggestionIds
from agent_console_server.testing import API, agent_doc, make_settings, server

SHARED_USES_PROJECT = KnownIssueCodes.PROJECT_SHARED_USES_PROJECT
MOVE_TO_SHARED = KnownSuggestionIds.PROJECT_MOVE_TO_SHARED
OPTIONS = {"mod-projects": {"snapshot_ttl_seconds": 0}}


def _graph(graph_id: str, agent_ref: str) -> dict[str, Any]:
    return {
        "id": graph_id,
        "name": graph_id,
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": agent_ref}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "a", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r1",
                "source": {"node": "a", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }


def _seed(client: TestClient, *, project: bool) -> None:
    if project:
        created = client.post(f"{API}/projects", json={"id": "alpha", "name": "알파"})
        assert created.status_code == 201, created.text
    agent = agent_doc("pa-2", "답: $prompt", **({"project": "alpha"} if project else {}))
    assert client.post(f"{API}/agents", json=agent).status_code == 201
    response = client.post(f"{API}/graphs", json=_graph("g-shared", "pa-2"))
    assert response.status_code == 201, response.text


def _codes(issues: list[dict[str, Any]]) -> set[str]:
    return {i["code"] for i in issues}


def test_validate_reports_project_scope_warning(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, options=OPTIONS)) as client:
        _seed(client, project=True)
        assert SHARED_USES_PROJECT in _codes(client.post(f"{API}/projects/scope-issues").json())

        saved = client.post(f"{API}/graphs/g-shared/validate").json()
        draft = client.post(
            f"{API}/graphs/g-shared/validate", json=_graph("g-shared", "pa-2")
        ).json()
        for issues in (saved, draft):
            [warning] = [i for i in issues if i["code"] == SHARED_USES_PROJECT]
            assert warning["severity"] == "warning"
            assert [s["id"] for s in warning["suggestions"]] == [MOVE_TO_SHARED]
            assert warning["details"]["id"] == "pa-2"
            assert all(i["severity"] != "error" for i in issues)


def test_validate_without_projects_module_has_no_scope_warning(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, options=OPTIONS, modules={"disabled": ["mod-projects"]})
    with server(settings) as client:
        mods = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert mods["mod-projects"] == "disabled"
        _seed(client, project=False)
        # 꺼진 모듈의 project 필드가 파일에 남아 있어도 아무도 거르지 않는다(지금과 같음)
        agent = client.get(f"{API}/agents/pa-2")
        body = {**agent.json(), "project": "alpha"}
        etag = {"If-Match": agent.headers["ETag"]}
        put = client.put(f"{API}/agents/pa-2", json=body, headers=etag)
        assert put.status_code == 200, put.text
        issues = client.post(f"{API}/graphs/g-shared/validate").json()
        assert not any(i["code"].startswith("project.") for i in issues)
        assert issues == []
