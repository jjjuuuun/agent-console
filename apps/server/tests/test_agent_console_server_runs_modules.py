"""3R.13 실행 모듈 + 연동(M.8): mod-runs·link-runs-teams·link-runs-trace·link-runs-usage 조립.

- 실행 경로·디스크립터·WS는 `mod-runs`, 검증 경로·목록 검증 요약은 `link-runs-teams`, 흐름·넘김은
  `link-runs-trace`, 토큰 집계는 `link-runs-usage`가 붙인다(웹 역할 포함).
- `link-runs-teams`를 끄면 엔진 검증만으로 실행되고 `team.rules_unavailable` 경고가 나온다.
- 실행 설정의 새 위치(`modules.options.mod-runs.*`)를 읽는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    seed,
    server,
    team_graph,
    wait_run,
)

LINK_ROLES: dict[str, list[str]] = {
    "link-runs-teams": ["runs:team-rules"],
    "link-runs-trace": ["runs:trace"],
    "link-runs-usage": ["usage:tokens"],
}


def _codes(client: Any) -> list[str]:
    return [w["code"] for w in client.get(f"{API}/server-info").json()["warnings"]]


def test_runs_module_and_links_are_active_with_roles(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos["mod-runs"]["status"] == "active"
        assert infos["mod-runs"]["web_roles"] == ["runs"]
        assert "runs.starter" in infos["mod-runs"]["provides"]
        for link_id, roles in LINK_ROLES.items():
            assert infos[link_id]["status"] == "active", infos[link_id]
            assert infos[link_id]["kind"] == "link"
            assert infos[link_id]["web_roles"] == roles
        assert "team.rules_unavailable" not in _codes(client)
        seed(client)
        run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "hi"}})
        assert run.status_code == 202, run.text
        run_id = run.json()["id"]
        assert wait_run(client, run_id)["run"]["status"] == "completed"
        assert client.get(f"{API}/runs/{run_id}/trace").json()["run_id"] == run_id
        assert client.get(f"{API}/runs/handoffs").json()["runs"] == 1  # 고정 경로가 먼저 맞는다
        rollups = client.get(f"{API}/usage", params={"parts": "tokens"}).json()["rollups"]
        assert isinstance(rollups, list)
        assert client.post(f"{API}/graphs/flow/validate").json() == []


def test_without_team_link_runs_use_engine_validation_only(tmp_path: Path) -> None:
    """`link-runs-teams`를 끄면 팀 규칙 없이 엔진 검증만으로 실행되고 경고가 나온다."""
    graph = team_graph("ghost")
    graph["nodes"][1]["config"]["agent_ref"] = "nobody"  # 팀 규칙 error(team.agent_not_found)
    with server(make_settings(tmp_path)) as client:
        seed(client)
        assert client.post(f"{API}/graphs", json=graph).status_code == 201
        blocked = client.post(f"{API}/runs", json={"graph_id": "ghost"})
        assert blocked.status_code == 422
        codes = {i["code"] for i in blocked.json()["error"]["details"]["issues"]}
        assert codes & {"agent.not_found", "team.agent_not_found"}

    settings = make_settings(tmp_path, modules={"disabled": ["link-runs-teams"]})
    with server(settings) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses["link-runs-teams"] == "disabled"
        assert statuses["mod-runs"] == "active"
        assert "team.rules_unavailable" in _codes(client)
        started = client.post(f"{API}/runs", json={"graph_id": "ghost", "input": {"request": "hi"}})
        assert started.status_code == 202, started.text  # 엔진 검증만 — 팀 규칙으로 막지 않는다
        # 노드 서비스(에이전트 조회)도 이 연동이 주므로 에이전트 노드는 원인 코드와 함께 실패한다
        snap = wait_run(client, started.json()["id"])
        errors = {(n["node_id"], (n.get("error") or {}).get("code")) for n in snap["node_runs"]}
        assert ("a", "agent.lookup_unavailable") in errors, snap
        # 3R.16: 메시지에 원인 힌트(에이전트 연동 모듈이 꺼져 있을 수 있음)
        [node_a] = [n for n in snap["node_runs"] if n["node_id"] == "a"]
        assert "link-runs-teams" in node_a["error"]["message"]
        assert client.post(f"{API}/graphs/ghost/validate").status_code == 404
        listed = {g["id"]: g for g in client.get(f"{API}/graphs").json()}
        assert listed["ghost"]["validation"] is None


def test_disabling_runs_module_turns_off_runs_and_dependents(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["mod-runs"]})
    with server(settings) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos["mod-runs"]["status"] == "disabled"
        for module_id in (*LINK_ROLES, "link-chat-runs"):
            assert infos[module_id]["status"] == "unsatisfied", infos[module_id]
        assert infos["mod-chat"]["status"] == "active"
        assert client.get(f"{API}/conversations").status_code == 200
        assert client.get(f"{API}/runs").status_code == 404
        assert client.get(f"{API}/node-types").status_code == 404
        assert client.get(f"{API}/agents").status_code == 200
        assert client.post(f"{API}/agents", json=agent_doc("a", "x")).status_code == 201
        assert client.get(f"{API}/usage").json()["rollups"] == []
        info = client.get(f"{API}/server-info").json()
        assert "recovered_runs" not in info["attributes"]


def test_disabling_trace_link_hides_trace_only(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["link-runs-trace"]})
    with server(settings) as client:
        seed(client)
        run_id = client.post(f"{API}/runs", json={"graph_id": "flow"}).json()["id"]
        wait_run(client, run_id)
        assert client.get(f"{API}/runs/{run_id}").status_code == 200
        assert client.get(f"{API}/runs/{run_id}/trace").status_code == 404


def test_runs_options_new_location(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    settings = make_settings(
        tmp_path,
        modules={
            "options": {
                "mod-runs": {
                    "backends": {"fake": {"models": [{"id": "fake-new"}]}},
                    "working_directory": str(project),
                    "runtime": {"shutdown_timeout": 1},
                }
            }
        },
    )
    with server(settings) as client:
        models = client.get(f"{API}/backends/fake/models").json()
        assert [m["id"] for m in models] == ["fake-new"]
