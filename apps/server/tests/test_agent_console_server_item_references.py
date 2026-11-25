"""FU.13(통합 서버): 종류 공통 거꾸로 참조 ``GET /projects/copy/items/{kind}/{id}/references``.

삭제 확인 창의 "이 구성을 쓰는 구성" 목록. 실제 정의·팀 연동(X25 참조 추출)으로 팀 구성 → 에이전트,
에이전트 → 리소스 참조를 찾는다. 서버·이 테스트는 종류 이름을 고정하지 않고 ``copy/items``로 찾는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, agent_doc, make_settings, server, team_graph

ITEMS = f"{API}/projects/copy/items"
QUIET = {
    "mod-logs": {"startup_scan": False, "scan_interval_seconds": 0},
    "mod-wiki": {"scan_interval_seconds": 0},
}
RESOURCE = {
    "id": "guide",
    "type": "instruction",
    "name": "지침",
    "config": {"title": "지침"},
    "content": {"file": "content.md", "media_type": "text/markdown"},
}


def _kinds_by_id(client: Any, project: str | None) -> dict[str, str]:
    params = {} if project is None else {"project": project}
    return {i["id"]: i["kind"] for i in client.get(ITEMS, params=params).json()}


def _users(client: Any, project: str | None, item_id: str) -> dict[str, Any]:
    kind = _kinds_by_id(client, project)[item_id]
    params = {} if project is None else {"project": project}
    resp = client.get(f"{ITEMS}/{kind}/{item_id}/references", params=params)
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _seed(client: Any, query: str) -> None:
    for doc in (agent_doc("fast", "a"), agent_doc("slow", "b", resources=[{"ref": "guide"}])):
        assert client.post(f"{API}/agents{query}", json=doc).status_code == 201
    assert client.post(f"{API}/resources{query}", json=RESOURCE).status_code == 201
    made = client.post(f"{API}/graphs{query}", json=team_graph("flow"))
    assert made.status_code == 201, made.text


def test_team_uses_agent_and_agent_uses_resource_in_project_space(tmp_path: Path) -> None:
    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    with server(make_settings(tmp_path, options=QUIET)) as client:
        registered = client.post(f"{API}/projects", json={"folder": str(folder)})
        assert registered.status_code == 201, registered.text
        project = registered.json()["project"]["id"]
        _seed(client, f"?project={project}")
        kinds = _kinds_by_id(client, project)

        fast = _users(client, project, "fast")
        assert fast["checked"] is True
        assert [(i["kind"], i["id"], i["name"]) for i in fast["items"]] == [
            (kinds["flow"], "flow", "테스트 흐름")
        ]
        assert fast["items"][0]["version"]

        guide = _users(client, project, "guide")
        assert [(i["kind"], i["id"]) for i in guide["items"]] == [(kinds["slow"], "slow")]

        # 아무도 쓰지 않는 팀 구성은 빈 목록(검사는 했다).
        assert _users(client, project, "flow") == {"items": [], "checked": True, "warnings": []}

        # 공용 구성에는 아무것도 없다 — 다른 공간의 사본은 쓰는 곳이 아니다.
        assert client.get(f"{ITEMS}/{kinds['fast']}/fast/references").status_code == 404


def test_library_space_and_delete_after_listing(tmp_path: Path) -> None:
    """공용 구성에서도 같은 경로. 쓰던 팀 구성을 지우면 목록이 빈다."""
    with server(make_settings(tmp_path, options=QUIET)) as client:
        _seed(client, "")
        kinds = _kinds_by_id(client, None)
        assert [i["id"] for i in _users(client, None, "slow")["items"]] == ["flow"]
        gone = client.delete(f"{ITEMS}/{kinds['flow']}/flow")
        assert gone.status_code == 204, gone.text
        assert _users(client, None, "slow")["items"] == []
