"""FU.3: 프로젝트 공간(project_id)을 지원하는지 확인할 경로(R15.6, remaining R2).

경로: 로그 ↔ 기록 상관 ``log_corr`` 쓰기, ``/runs/{id}/trace``·``/runs/handoffs``의 ``?project=``,
``/agents/{id}/activity``, ``/graphs/{id}/validate``, 공간 계산 중 ``resources.lookup``.

처음에는 새는 경로를 ``xfail(strict=True)``로 표시했고(QA 확인), 고친 뒤 표시를 지웠다 — 이제 모두
지켜야 할 동작이다. 설정 파일·원본은 건드리지 않고 fake 백엔드만 쓴다.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

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

LOG_OPTIONS = {
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
}
PLATFORM = "platform-runs"


def _prepare(client: TestClient, folder: Path, pid: str = "p1") -> str:
    """프로젝트 등록 + 공간 에이전트·팀 구성 + 실행 하나(끝날 때까지). run id."""
    register_project(client, pid, folder)
    for name in ("fast", "slow"):
        assert (
            client.post(f"{API}/agents?project={pid}", json=agent_doc(name, "답")).status_code
            == 201
        )
    graph = team_graph("flow")
    for edge in graph["edges"]:
        edge["config"].pop("input_key", None)
    assert client.post(f"{API}/graphs?project={pid}", json=graph).status_code == 201
    started = client.post(
        f"{API}/runs", json={"graph_id": "flow", "input": {"text": "hi"}, "project_id": pid}
    )
    assert started.status_code == 202, started.text
    run_id: str = started.json()["id"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        snap = client.get(f"{API}/runs/{run_id}?project={pid}").json()
        if snap["run"]["status"] in TERMINAL:
            return run_id
        time.sleep(0.05)
    raise AssertionError("Run이 끝나지 않았다")


def _count(client: TestClient, **flt: Any) -> int:
    body = {"group_by": [], "metric": "events", "filter": flt}
    rows = client.post(f"{API}/logs/aggregate", json=body).json()
    return int(rows[0]["value"]) if rows else 0


def _tables(db: Path) -> set[str]:
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()


# ---------------------------------------------------------------- trace


def test_trace_finds_project_run_without_project_param_and_after_restart(tmp_path: Path) -> None:
    """현재 동작: ``?project=`` 없이도 등록 공간을 찾아 읽는다(위치 찾기). 재시작 뒤에도."""
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        run_id = _prepare(client, folder)
        trace = client.get(f"{API}/runs/{run_id}/trace")
        assert trace.status_code == 200, trace.text
        assert {s["node_id"] for s in trace.json()["spans"]} == {"a", "b"}
        assert [lk["edge_id"] for lk in trace.json()["links"]] == ["h1"]
    with server(make_settings(tmp_path)) as client:  # 기억한 자리 없음
        again = client.get(f"{API}/runs/{run_id}/trace")
        assert again.status_code == 200, again.text
        assert again.json()["links"] == trace.json()["links"]


def test_trace_of_unregistered_run_is_not_found(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        assert client.get(f"{API}/runs/nope/trace").status_code == 404


def test_trace_unknown_project_is_404(tmp_path: Path) -> None:
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        run_id = _prepare(client, folder)
        assert client.get(f"{API}/runs/{run_id}?project=ghost").status_code == 404  # 기준선
        ghost = client.get(f"{API}/runs/{run_id}/trace?project=ghost")
        assert ghost.status_code == 404
        assert ghost.json()["error"]["code"] == "project.not_found"
        scoped = client.get(f"{API}/runs/{run_id}/trace?project=p1")
        assert scoped.status_code == 200, scoped.text
        assert {s["node_id"] for s in scoped.json()["spans"]} == {"a", "b"}


def test_handoffs_counts_project_runs(tmp_path: Path) -> None:
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        _prepare(client, folder)
        found = client.get(f"{API}/runs/handoffs?project=p1").json()
        assert found["runs"] == 1
        assert found["cells"], found
        # ?project= 없으면 지금처럼 호스트 기록(GET /runs와 같은 정책), 모르는 프로젝트는 404.
        assert client.get(f"{API}/runs/handoffs").json()["runs"] == 0
        ghost = client.get(f"{API}/runs/handoffs?project=ghost")
        assert ghost.status_code == 404
        assert ghost.json()["error"]["code"] == "project.not_found"


# ---------------------------------------------------------------- activity


def test_activity_reads_only_that_project_records(tmp_path: Path) -> None:
    folder = tmp_path / "P"
    other = tmp_path / "Q"
    folder.mkdir()
    other.mkdir()
    with server(make_settings(tmp_path)) as client:
        _prepare(client, folder)
        register_project(client, "p2", other)
        assert len(client.get(f"{API}/agents/fast/activity?project=p1").json()) > 0
        assert (
            client.get(f"{API}/agents/fast/activity?project=p2").json() == []
        )  # 파일 없음 = 빈 목록
        assert client.get(f"{API}/agents/fast/activity").json() == []  # 공용(앱 DB)으로 새지 않는다
        assert client.get(f"{API}/agents/fast/activity?project=ghost").status_code == 404


# ---------------------------------------------------------------- validate


def test_validate_uses_space_definitions_and_does_not_fall_back_to_library(tmp_path: Path) -> None:
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "p1", folder)
        assert client.post(f"{API}/agents", json=agent_doc("fast", "답")).status_code == 201
        assert client.post(f"{API}/agents", json=agent_doc("slow", "답")).status_code == 201
        assert client.post(f"{API}/graphs", json=team_graph("lib-only")).status_code == 201
        # 공용에만 있는 구성: 공간 기준 검증은 공용으로 넘어가 찾지 않는다.
        assert client.post(f"{API}/graphs/lib-only/validate").status_code == 200
        # (실제 응답은 422 — 공간에 에이전트가 없어 정의 출처가 막는다. 200이 아니면 새지 않은 것.)
        scoped = client.post(f"{API}/graphs/lib-only/validate?project=p1")
        assert scoped.status_code in (404, 422), scoped.text
        assert client.post(f"{API}/graphs/lib-only/validate?project=ghost").status_code == 404


# ---------------------------------------------------------------- log_corr


def test_log_corr_is_written_only_to_app_log_index(tmp_path: Path) -> None:
    """현재 동작: 프로젝트 실행 이벤트는 앱 로그 색인(``log_*`` 표)에 색인되고, 그 폴더 기록 DB에는
    로그 표가 생기지 않는다. 읽기(``/runs/{id}/logs``·``scope=run:``)는 공간을 찾아 동작한다."""
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path, options=LOG_OPTIONS)) as client:
        run_id = _prepare(client, folder)
        for _ in range(40):
            assert (
                client.post(f"{API}/logs/scan", json={"source_ids": [PLATFORM]}).status_code == 202
            )
            if _count(client, source=[PLATFORM], run_id=[run_id]):
                break
            time.sleep(0.25)
        assert _count(client, source=[PLATFORM], run_id=[run_id]) > 0
        assert _count(client, source=[PLATFORM], project=["p1"]) > 0
        assert client.get(f"{API}/runs/{run_id}/logs?source={PLATFORM}").status_code == 200
        scoped = client.get(f"{API}/logs/events", params={"scope": f"run:{run_id}", "limit": 5})
        assert scoped.status_code == 200
    records = _tables(folder / ".agent-console" / "records.sqlite3")
    assert not {t for t in records if t.startswith("log_")}
    app_dbs = [p for p in (tmp_path / "ws").rglob("*.sqlite3") if "log_corr" in _tables(p)]
    assert app_dbs, "앱 로그 색인 DB가 없다"


# ---------------------------------------------------------------- resources.lookup

_MCP = {
    "id": "gh",
    "type": "mcp-server",
    "name": "gh",
    "config": {"name": "gh", "command": "npx"},
}


def _agent_with_bad_override(agent_id: str) -> dict[str, Any]:
    """리소스 종류 스키마에 맞지 않는 덮어쓰기(리소스를 찾았을 때만 422)."""
    return agent_doc(agent_id, "x", resources=[{"ref": "gh", "config_override": {"command": 5}}])


def test_override_check_skipped_when_resource_nowhere(tmp_path: Path) -> None:
    """기준선: 어디에도 리소스가 없으면 덮어쓰기를 검사할 수 없어 저장된다."""
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "p1", folder)
        saved = client.post(f"{API}/agents?project=p1", json=_agent_with_bad_override("a0"))
        assert saved.status_code == 201, saved.text


def test_space_save_does_not_resolve_library_resource(tmp_path: Path) -> None:
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "p1", folder)
        assert client.post(f"{API}/resources", json=_MCP).status_code == 201  # 공용에만 있다
        saved = client.post(f"{API}/agents?project=p1", json=_agent_with_bad_override("a1"))
        assert saved.status_code == 201, saved.text


def test_space_save_checks_against_space_resource(tmp_path: Path) -> None:
    folder = tmp_path / "P"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "p1", folder)
        assert client.post(f"{API}/resources?project=p1", json=_MCP).status_code == 201
        saved = client.post(f"{API}/agents?project=p1", json=_agent_with_bad_override("a2"))
        assert saved.status_code == 422, saved.text
