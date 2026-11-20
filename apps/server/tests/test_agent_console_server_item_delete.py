"""요청 11/07 후속(통합 서버): 종류 공통 항목 삭제 ``DELETE /projects/copy/items/{kind}/{id}``.

실제 SDD·위키 모듈이 종류 기여에 삭제 콜백을 준다 — 프로젝트 공간의 스펙·위키를 종류 공통 경로로
지우면 각 기능 목록에서 사라진다. 서버·이 테스트는 종류 이름을 고정하지 않고 ``copy/kinds``와
``copy/items``로 찾는다."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

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


@pytest.mark.skipif(os.geteuid() == 0, reason="root는 쓰기 권한 검사를 통과한다")
def test_delete_in_folder_turned_read_only_after_open_is_409(tmp_path: Path) -> None:
    """열 때 쓸 수 있던 폴더가 나중에 읽기 전용이 되면 409 `project.config_readonly`여야 한다."""
    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    with server(make_settings(tmp_path, options=QUIET)) as client:
        registered = client.post(f"{API}/projects", json={"folder": str(folder)})
        assert registered.status_code == 201, registered.text
        project = registered.json()["project"]["id"]
        graph = client.post(
            f"{API}/graphs?project={project}",
            json={"schema_version": 1, "id": "g1", "name": "G", "nodes": [], "edges": []},
        )
        assert graph.status_code == 201, graph.text
        kind = _kind_of(client, project, "g1")
        locked = [p for p in (folder, *folder.rglob("*")) if p.is_dir()]
        try:
            for d in locked:
                d.chmod(d.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
            resp = client.delete(f"{ITEMS}/{kind}/g1", params={"project": project})
            assert resp.status_code == 409, resp.text
        finally:
            for d in locked:
                d.chmod(d.stat().st_mode | stat.S_IWUSR)


def _lock(folder: Path) -> list[Path]:
    """폴더와 그 아래 폴더 전부를 읽기 전용으로. 되돌릴 목록을 돌려준다."""
    locked = [p for p in (folder, *folder.rglob("*")) if p.is_dir()]
    for d in locked:
        d.chmod(d.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return locked


@pytest.mark.skipif(os.geteuid() == 0, reason="root는 쓰기 권한 검사를 통과한다")
def test_other_writes_in_folder_turned_read_only_after_open_are_409(tmp_path: Path) -> None:
    """5.7R.33n: 삭제 말고도 정의 만들기·저장·삭제, 복사 적용, 위키·스펙 만들기, 프로젝트 고치기가
    열린 뒤 읽기 전용이 된 폴더에서 500이 아니라 409 ``project.config_readonly``다."""
    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    graph = {"schema_version": 1, "id": "g1", "name": "G", "nodes": [], "edges": []}
    with server(make_settings(tmp_path, options=QUIET)) as client:
        registered = client.post(f"{API}/projects", json={"folder": str(folder)})
        assert registered.status_code == 201, registered.text
        project = registered.json()["project"]["id"]
        made = client.post(f"{API}/graphs?project={project}", json=graph)
        assert made.status_code == 201, made.text
        etag = made.headers["etag"]
        lib = client.post(f"{API}/graphs", json={**graph, "id": "lib1"})
        assert lib.status_code == 201, lib.text
        plan = client.post(
            f"{API}/projects/copy/plan",
            json={
                "source": {"project_id": None},
                "target": {"project_id": project},
                "items": [{"kind": "graph", "id": "lib1"}],
            },
        )
        assert plan.status_code == 200, plan.text
        apply_items = [
            {
                "kind": i["kind"],
                "id": i["id"],
                "action": i["default_action"] or "overwrite",
                "source_version": i["source_version"],
                "target_version": i["target_version"],
            }
            for i in plan.json()["items"]
        ]
        project_etag = client.get(f"{API}/projects/{project}").headers["etag"]

        locked = _lock(folder)
        try:
            view = client.get(f"{API}/projects/{project}")
            assert view.json()["config_writable"] is False, view.text
            replies = {
                "graph create": client.post(
                    f"{API}/graphs?project={project}", json={**graph, "id": "g2"}
                ),
                "graph save": client.put(
                    f"{API}/graphs/g1?project={project}",
                    json={**graph, "name": "G2"},
                    headers={"If-Match": etag},
                ),
                "graph delete": client.delete(f"{API}/graphs/g1?project={project}"),
                "copy apply": client.post(
                    f"{API}/projects/copy/apply",
                    json={
                        "source": {"project_id": None},
                        "target": {"project_id": project},
                        "items": apply_items,
                    },
                ),
                "wiki create": client.post(
                    f"{API}/wiki/wikis?project={project}", json={"name": "Notes"}
                ),
                "spec create": client.post(
                    f"{API}/sdd/specs?project={project}", json={"name": "S", "id": "s1"}
                ),
                "project update": client.put(
                    f"{API}/projects/{project}",
                    json={"description": "바뀜"},
                    headers={"If-Match": project_etag},
                ),
            }
            got = {name: (r.status_code, r.json()["error"]["code"]) for name, r in replies.items()}
            assert got == dict.fromkeys(replies, (409, "project.config_readonly")), got
        finally:
            for d in locked:
                d.chmod(d.stat().st_mode | stat.S_IWUSR)
        kept = client.get(f"{API}/graphs/g1?project={project}")
        assert kept.status_code == 200, kept.text
        assert kept.json()["graph"]["name"] == "G"
