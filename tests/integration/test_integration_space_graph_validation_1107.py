"""요청 11/07(e2e 제품 간극 ③): 공간 팀 구성 목록(``GET /graphs?project=``)의 ``validation``.

공용 목록처럼 요약을 채우고, 그 프로젝트에서 실행할 때와 같은 정의 출처(공간)로 계산한다. 같은
그래프라도 참조한 에이전트가 공간에 없으면 공간 목록에서만 실행을 막는다.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    register_project,
    server,
    team_graph,
)


def test_space_graph_list_has_validation_from_space(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "p1", folder)
        for agent_id in ("fast", "slow"):
            made = client.post(f"{API}/agents", json=agent_doc(agent_id, "답"))
            assert made.status_code == 201, made.text
        # 공간에는 fast만 있다 → 공간의 flow는 slow를 찾지 못해 실행이 막힌다.
        made = client.post(f"{API}/agents?project=p1", json=agent_doc("fast", "답"))
        assert made.status_code == 201, made.text
        for q in ("", "?project=p1"):
            saved = client.post(f"{API}/graphs{q}", json=team_graph("flow"))
            assert saved.status_code == 201, saved.text

        [lib] = client.get(f"{API}/graphs").json()
        assert lib["validation"] is not None
        assert lib["validation"]["blocks_run"] is False

        [row] = client.get(f"{API}/graphs?project=p1").json()
        assert row["validation"] is not None
        assert row["validation"]["blocks_run"] is True
        assert row["validation"]["error_count"] >= 1

        # 공간에 slow를 더하면(정의 개정이 바뀌면) 다시 계산한다.
        made = client.post(f"{API}/agents?project=p1", json=agent_doc("slow", "답"))
        assert made.status_code == 201, made.text
        [again] = client.get(f"{API}/graphs?project=p1").json()
        assert again["validation"]["blocks_run"] is False

        unchecked = client.get(f"{API}/graphs?project=p1&validate=false").json()
        assert unchecked[0]["validation"] is None


def test_validate_route_with_project_uses_space(tmp_path: Path) -> None:
    """``POST /graphs/{id}/validate?project=``: 그 프로젝트 실행 기준(공간에만 있는 구성도)."""
    folder = tmp_path / "proj"
    folder.mkdir()
    with server(make_settings(tmp_path)) as client:
        register_project(client, "p1", folder)
        made = client.post(f"{API}/agents?project=p1", json=agent_doc("fast", "답"))
        assert made.status_code == 201, made.text
        saved = client.post(f"{API}/graphs?project=p1", json=team_graph("only"))
        assert saved.status_code == 201, saved.text

        # 공용 기준이면 없는 구성
        assert client.post(f"{API}/graphs/only/validate").status_code == 404
        found = client.post(f"{API}/graphs/only/validate?project=p1")
        assert found.status_code == 200, found.text
        issues = found.json()
        errors = [i for i in issues if i["severity"] == "error"]
        assert errors
        assert all(i.get("node_id") != "a" for i in errors)  # fast는 공간에 있다
        assert any(i.get("node_id") == "b" for i in errors)  # slow는 공간에 없다

        # 초안 본문도 그 공간 기준(본문의 b를 fast로 바꾸면 막힘이 없다)
        draft = team_graph("only")
        draft["nodes"][2]["config"]["agent_ref"] = "fast"
        ok = client.post(f"{API}/graphs/only/validate?project=p1", json=draft)
        assert ok.status_code == 200, ok.text
        assert [i for i in ok.json() if i["severity"] == "error"] == []

        # 공간에 없는 구성: 실행 시작과 같은 거부(404가 아니라 프로젝트 오류)
        missing = client.post(f"{API}/graphs/ghost/validate?project=p1")
        assert missing.status_code == 422, missing.text
        assert missing.json()["error"]["code"] == "project.not_imported"
