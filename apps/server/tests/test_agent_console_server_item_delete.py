"""요청 11/07 후속(통합 서버): 종류 공통 항목 삭제 ``DELETE /projects/copy/items/{kind}/{id}``.

실제 SDD·위키 모듈이 종류 기여에 삭제 콜백을 준다 — 프로젝트 공간의 스펙·위키를 종류 공통 경로로
지우면 각 기능 목록에서 사라진다. 서버·이 테스트는 종류 이름을 고정하지 않고 ``copy/kinds``와
``copy/items``로 찾는다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

ITEMS = f"{API}/projects/copy/items"
QUIET = {
    "mod-logs": {"startup_scan": False, "scan_interval_seconds": 0},
    "mod-wiki": {"scan_interval_seconds": 0},
}


def _kind_of(client: Any, project: str, item_id: str) -> str:
    """그 공간에서 ``item_id``를 가진 종류 이름(종류 이름 표 없이)."""
    items = client.get(ITEMS, params={"project": project}).json()
    kind: str = next(i["kind"] for i in items if i["id"] == item_id)
    return kind


def test_contributed_items_delete_through_common_route(tmp_path: Path) -> None:
    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    with server(make_settings(tmp_path, options=QUIET)) as client:
        registered = client.post(f"{API}/projects", json={"folder": str(folder)})
        assert registered.status_code == 201, registered.text
        project = registered.json()["project"]["id"]

        kinds = client.get(f"{API}/projects/copy/kinds", params={"project": project}).json()
        assert kinds
        assert all(k["deletable"] for k in kinds), kinds

        spec = client.post(f"{API}/sdd/specs?project={project}", json={"name": "S", "id": "s1"})
        assert spec.status_code == 201, spec.text
        wiki = client.post(f"{API}/wiki/wikis?project={project}", json={"name": "Notes"})
        assert wiki.status_code == 201, wiki.text
        wiki_id = wiki.json()["wiki"]["id"]

        spec_kind = _kind_of(client, project, "s1")
        stale = client.delete(
            f"{ITEMS}/{spec_kind}/s1", params={"project": project}, headers={"If-Match": '"x"'}
        )
        assert stale.status_code == 412, stale.text
        gone = client.delete(f"{ITEMS}/{spec_kind}/s1", params={"project": project})
        assert gone.status_code == 204, gone.text
        assert client.get(f"{API}/sdd/specs?project={project}").json() == []

        wiki_kind = _kind_of(client, project, wiki_id)
        gone = client.delete(f"{ITEMS}/{wiki_kind}/{wiki_id}", params={"project": project})
        assert gone.status_code == 204, gone.text
        assert client.get(f"{API}/wiki/wikis?project={project}").json() == []

        again = client.delete(f"{ITEMS}/{wiki_kind}/{wiki_id}", params={"project": project})
        assert again.status_code == 404, again.text
