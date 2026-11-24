"""5.7R.33s 통합: 프로젝트 격리(R15.6)·R0 끄기(R0.1·R10.7).

설치된 모듈 전부(앱 조립, fake 백엔드, TestClient — 실서버 불필요).

- 공간 분리: 프로젝트 A에 만든 정의·메모리·위키·스펙·실행이 B와 공용에 보이지 않는다.
- 경로 지킴: 설정 경로가 프로젝트 폴더 밖이면 422 ``project.outside_folder``, 안쪽이면 202.
- 등록하지 않은 폴더는 실행·기록 뒤에도 파일이 그대로다. 프로젝트 없는 실행은 422.
- ``link-projects-*``·``mod-projects``를 끄면 그 기능만 409이고 공용으로 새지 않는다.
- ``link-projects-runs``를 끄면 프로젝트를 붙인 실행·대화 턴은 409 ``feature_unavailable``
  (5.7R.33t1, K33-10), 프로젝트 없는 실행은 202.
- 비루프백 서버의 폴더 API 403은 0.0.0.0 바인딩을 하지 않는 안전 규칙상 여기서 확인하지 않고
  단위 테스트 ``test_remote_bind_blocks_folders``(ac-mod-projects)를 근거로 한다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_server.testing import (
    API,
    TERMINAL,
    agent_doc,
    make_settings,
    register_project,
    server,
    team_graph,
)


def _snapshot(root: Path) -> dict[str, int]:
    return {str(p.relative_to(root)): p.stat().st_size for p in sorted(root.rglob("*"))}


def _graph(graph_id: str, **settings: Any) -> dict[str, Any]:
    doc = team_graph(graph_id)
    for edge in doc["edges"]:
        edge["config"].pop("input_key", None)
    if settings:
        doc["settings"] = settings
    return doc


def _seed(client: TestClient, project: str | None, graph_id: str = "flow", **settings: Any) -> None:
    q = f"?project={project}" if project else ""
    for doc in (agent_doc("fast", "빠른"), agent_doc("slow", "깊은")):
        client.post(f"{API}/agents{q}", json=doc)
    response = client.post(f"{API}/graphs{q}", json=_graph(graph_id, **settings))
    assert response.status_code == 201, response.text


def _run(client: TestClient, graph_id: str, project: str | None) -> Any:
    body: dict[str, Any] = {"graph_id": graph_id, "input": {"text": "hi"}}
    if project:
        body["project_id"] = project
    return client.post(f"{API}/runs", json=body)


def _wait(client: TestClient, run_id: str, project: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}?project={project}").json()
        if snap.get("run", {}).get("status") in TERMINAL:
            return snap
        time.sleep(0.03)
    raise AssertionError("실행이 끝나지 않았다")


def _ids(client: TestClient, path: str, project: str | None) -> list[str]:
    q = f"{'&' if '?' in path else '?'}project={project}" if project else ""
    response = client.get(f"{API}{path}{q}")
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"] if isinstance(body, dict) else body
    return sorted(str(x.get("id") or x.get("key")) for x in items)


def _write_space(client: TestClient, project: str) -> dict[str, int]:
    """프로젝트 공간에 메모리·위키·스펙을 쓰고 상태 코드를 돌려준다."""
    q = f"?project={project}"
    return {
        "memory": client.post(
            f"{API}/memory/entries{q}",
            json={"scope": {"kind": "shared", "id": ""}, "key": "k-a", "content": "A만"},
        ).status_code,
        "wiki": client.post(f"{API}/wiki/wikis{q}", json={"id": "wiki-a", "name": "w"}).status_code,
        "spec": client.post(f"{API}/sdd/specs{q}", json={"id": "spec-a", "name": "s"}).status_code,
    }


def test_spaces_do_not_leak_and_unregistered_folder_untouched(tmp_path: Path) -> None:
    folders = {"pa": tmp_path / "A", "pb": tmp_path / "B", "un": tmp_path / "unreg"}
    for f in folders.values():
        f.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "pa", folders["pa"])
        register_project(client, "pb", folders["pb"])
        before = _snapshot(folders["un"])
        _seed(client, "pa", "tm-a")
        assert _write_space(client, "pa") == {"memory": 201, "wiki": 201, "spec": 201}
        run = _run(client, "tm-a", "pa")
        assert run.status_code == 202, run.text
        snap = _wait(client, run.json()["id"], "pa")
        assert snap["run"]["project_id"] == "pa"

        for scope in ("pb", None):
            for path in ("/agents", "/graphs", "/memory/entries?limit=200", "/runs", "/sdd/specs"):
                assert _ids(client, path, scope) == [], (scope, path)
            wikis = client.get(f"{API}/wiki/wikis" + (f"?project={scope}" if scope else ""))
            assert wikis.json() == []
            for path in ("/agents/fast", "/graphs/tm-a"):
                q = f"?project={scope}" if scope else ""
                assert client.get(f"{API}{path}{q}").status_code == 404
        assert len(_ids(client, "/agents", "pa")) == 2
        assert _ids(client, "/graphs", "pa") == ["tm-a"]
        assert _ids(client, "/runs", "pa") == [run.json()["id"]]

        # B에서 A의 팀을 실행할 수 없고, 공용에는 그 팀이 없다.
        assert _run(client, "tm-a", "pb").status_code == 422
        assert _run(client, "tm-a", None).status_code == 404
        # 앱 DB에는 프로젝트 기록 0(기록은 그 폴더 DB에).
        assert client.get(f"{API}/runs?project=pa&source=app").json() == []

        # 앱이 쓴 파일은 등록 폴더의 .agent-console/ 안뿐, 미등록 폴더는 그대로.
        for pid in ("pa", "pb"):
            outside = [p for p in _snapshot(folders[pid]) if not p.startswith(".agent-console")]
            assert outside == [], (pid, outside)
        assert _snapshot(folders["un"]) == before == {}


def test_outside_paths_rejected_inside_accepted(tmp_path: Path) -> None:
    folder, other = tmp_path / "A", tmp_path / "unreg"
    folder.mkdir()
    other.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "pa", folder)
        _seed(client, "pa", "ok", working_directory="sub")
        for gid, wd in (("abs", str(other)), ("rel", "../unreg"), ("etc", "/etc")):
            assert (
                client.post(
                    f"{API}/graphs?project=pa", json=_graph(gid, working_directory=wd)
                ).status_code
                == 201
            )
            response = _run(client, gid, "pa")
            assert response.status_code == 422, (gid, response.text)
            assert response.json()["error"]["code"] == "project.outside_folder"
        assert _run(client, "ok", "pa").status_code == 202
        assert _snapshot(other) == {}
        # 프로젝트 없는 실행·없는 프로젝트
        _seed(client, None, "lib")
        assert _run(client, "lib", None).json()["error"]["code"] == "project.required"
        assert _run(client, "lib", "nope").status_code == 404


@pytest.mark.parametrize(
    ("off", "blocked"),
    [
        ("link-projects-memory", {"memory"}),
        ("link-projects-wiki", {"wiki"}),
        ("mod-projects", {"memory", "wiki", "spec"}),
    ],
)
def test_turning_off_a_link_blocks_only_that_and_never_leaks(
    tmp_path: Path, off: str, blocked: set[str]
) -> None:
    folder = tmp_path / "A"
    folder.mkdir()
    with server(make_settings(tmp_path, modules={"disabled": [off]})) as client:
        if off != "mod-projects":
            register_project(client, "pa", folder)
        codes = _write_space(client, "pa")
        for name, code in codes.items():
            assert (code == 409) if name in blocked else (code == 201), (off, name, code)
        # 어느 쪽이든 공용에는 아무것도 쓰이지 않는다.
        assert _ids(client, "/memory/entries?limit=200", None) == []
        assert client.get(f"{API}/wiki/wikis").json() == []
        assert _ids(client, "/sdd/specs", None) == []


def test_runs_link_off_runs_standalone(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, modules={"disabled": ["link-projects-runs"]})) as client:
        _seed(client, None)
        response = _run(client, "flow", None)
        assert response.status_code == 202, response.text


def _scope_warnings(client: TestClient) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = client.get(f"{API}/server-info").json()["warnings"]
    return [
        w
        for w in warnings
        if w["code"] == "feature_unavailable" and w.get("details", {}).get("port") == "runs.scopes"
    ]


def test_runs_link_off_blocks_project_runs_and_turns(tmp_path: Path) -> None:
    """5.7R.33t1(K33-10): 프로젝트가 있는 조립에서 실행 연동을 끄면 프로젝트 실행·대화 턴은 409."""
    folder = tmp_path / "A"
    folder.mkdir()
    with server(make_settings(tmp_path, modules={"disabled": ["link-projects-runs"]})) as client:
        register_project(client, "pa", folder)
        _seed(client, "pa")
        _seed(
            client, None
        )  # 같은 id가 라이브러리에도 있다 - 고치기 전에는 이것으로 서버 폴더에서 돌았다
        assert len(_scope_warnings(client)) == 1  # 화면이 시작 단추를 막는 신호

        blocked = _run(client, "flow", "pa")
        assert blocked.status_code == 409, blocked.text
        error = blocked.json()["error"]
        assert error["code"] == "feature_unavailable"
        assert error["details"]["port"] == "runs.scopes"
        assert error["details"]["project_id"] == "pa"

        # 대화 턴도 같은 이유로 막힌다(대화 자체는 프로젝트 기록에 만들 수 있다)
        conv = client.post(
            f"{API}/conversations", json={"graph_id": "flow", "project_id": "pa", "title": "t"}
        )
        assert conv.status_code == 201, conv.text
        cid = conv.json()["id"]
        sent = client.post(f"{API}/conversations/{cid}/messages?project=pa", json={"text": "안녕"})
        assert sent.status_code == 409, sent.text
        assert sent.json()["error"]["code"] == "feature_unavailable"
        assert client.get(f"{API}/conversations/{cid}/turns?project=pa").json() == []

        # 프로젝트 기준 검증도 같은 오류(실행할 수 없는 프로젝트)
        checked = client.post(f"{API}/graphs/flow/validate?project=pa")
        assert checked.status_code == 409, checked.text

        # Run은 어디에도 없다(프로젝트 기록·앱 DB 모두)
        assert _ids(client, "/runs", "pa") == []
        assert client.get(f"{API}/runs?project=pa&source=app").json() == []
        assert _ids(client, "/runs", None) == []

        # 프로젝트 없는 단독 실행은 그대로
        assert _run(client, "flow", None).status_code == 202
        outside = [p for p in _snapshot(folder) if not p.startswith(".agent-console")]
        assert outside == []


def test_runs_link_on_keeps_project_runs(tmp_path: Path) -> None:
    folder = tmp_path / "A"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "pa", folder)
        _seed(client, "pa")
        assert _scope_warnings(client) == []
        response = _run(client, "flow", "pa")
        assert response.status_code == 202, response.text
        assert _wait(client, response.json()["id"], "pa")["run"]["project_id"] == "pa"
