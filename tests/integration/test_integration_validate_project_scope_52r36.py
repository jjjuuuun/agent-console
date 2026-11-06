"""5.2R.36 결함 B → 5.7R.33f 개정: 팀 구성 검증에 옛 프로젝트 범위 경고가 붙지 않는다.

- 정의의 `project` 필드(옛 프로젝트 전용 범위)는 design §PI(K33-5)에서 없어졌다. `mod-projects`는
  `definitions.checks` 범위 경고를 더 내지 않는다(5.7R.33f). 옛 [정리] 화면용
  `POST /projects/scope-issues`(deprecated, 33t 삭제)만 같은 코드를 낸다.
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


def _seed(client: TestClient, *, project: bool, folder: Path | None = None) -> None:
    if project:
        assert folder is not None
        folder.mkdir(parents=True, exist_ok=True)
        created = client.post(
            f"{API}/projects", json={"id": "alpha", "name": "알파", "folder": str(folder)}
        )
        assert created.status_code == 201, created.text
    agent = agent_doc("pa-2", "답: $prompt", **({"project": "alpha"} if project else {}))
    assert client.post(f"{API}/agents", json=agent).status_code == 201
    response = client.post(f"{API}/graphs", json=_graph("g-shared", "pa-2"))
    assert response.status_code == 201, response.text


def _codes(issues: list[dict[str, Any]]) -> set[str]:
    return {i["code"] for i in issues}


def test_validate_has_no_project_scope_warning(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, options=OPTIONS)) as client:
        _seed(client, project=True, folder=tmp_path / "alpha")
        scope = client.post(f"{API}/projects/scope-issues").json()
        [old] = [i for i in scope if i["code"] == SHARED_USES_PROJECT]
        assert [s["id"] for s in old["suggestions"]] == [MOVE_TO_SHARED]

        saved = client.post(f"{API}/graphs/g-shared/validate").json()
        draft = client.post(
            f"{API}/graphs/g-shared/validate", json=_graph("g-shared", "pa-2")
        ).json()
        for issues in (saved, draft):
            assert not [i for i in issues if i["code"].startswith("project.")]
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
