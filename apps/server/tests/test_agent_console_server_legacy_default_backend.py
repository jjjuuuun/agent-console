"""옛 최상위 `default_backend`가 남은 workspace(1.1.0): 서버는 시작하고 안내만 하며 값은 읽지
않는다.

- `settings.yaml`의 `default_backend` → 시작(health 200), `/server-info` warnings에 info
  `settings.ignored_key`(`details.key = "default_backend"`, `details.replacement =
  "agent_defaults.backend"`).
- 옛 키만 있고 `agent_defaults.backend`가 없으면 실행 전 점검이 422 `backend.unresolved`(해결 버튼
  포함), Run 기록 0건. `agent_defaults.backend`를 정하면 실행된다.
- 옛 키는 파일에서 지우지 않는다(사용자가 지운다).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import BackendUnresolvedDetails, ErrorCodes
from agent_console_server.testing import API, chat_graph, make_settings, server, wait_run

NO_PROJECT_GATE: dict[str, dict[str, Any]] = {
    "link-projects-runs": {"require_project": False},
    "mod-logs": {"startup_scan": False, "scan_interval_seconds": 0},
}


def test_old_default_backend_starts_with_info_and_is_not_read(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    (ws / "settings.yaml").write_text("default_backend: fake-agent\n", encoding="utf-8")
    with server(make_settings(tmp_path, options=NO_PROJECT_GATE)) as client:
        assert client.get(f"{API}/health").status_code == 200

        warnings = client.get(f"{API}/server-info").json()["warnings"]
        ignored = [w for w in warnings if w["code"] == "settings.ignored_key"]
        assert [(w["severity"], w["details"]) for w in ignored] == [
            ("info", {"key": "default_backend", "replacement": "agent_defaults.backend"})
        ]
        assert "agent_defaults.backend" in ignored[0]["message"]

        # 백엔드를 정하지 않은 에이전트 하나짜리 팀: 옛 키는 공통 층이 아니다
        agent = {
            "id": "asker",
            "name": "안내원",
            "backend_options": {"default": {"response": "네"}},
        }
        assert client.post(f"{API}/agents", json=agent).status_code == 201
        assert client.post(f"{API}/graphs", json=chat_graph()).status_code == 201
        res = client.post(f"{API}/runs", json={"graph_id": "chat", "input": {"text": "hi"}})
        assert res.status_code == 422, res.text
        error = res.json()["error"]
        assert error["code"] == ErrorCodes.BACKEND_UNRESOLVED
        details = BackendUnresolvedDetails.model_validate(error["details"])
        assert [n.id for n in details.nodes] == ["a"]
        actions = error["fix"]["actions"]
        assert {"role": "settings", "section": "common"} in [a["target"] for a in actions]
        assert client.get(f"{API}/runs").json() == []

        # 새 위치에 두면 실행된다(옛 키는 그대로 남아 있어도 된다)
        got = client.get(f"{API}/settings")
        body = {**got.json(), "agent_defaults": {"backend": "fake-agent"}}
        put = client.put(f"{API}/settings", json=body, headers={"If-Match": got.headers["etag"]})
        assert put.status_code == 200, put.text
        run = client.post(f"{API}/runs", json={"graph_id": "chat", "input": {"text": "hi"}})
        assert run.status_code == 202, run.text
        assert wait_run(client, run.json()["id"])["run"]["status"] == "completed"

    assert "default_backend" in (ws / "settings.yaml").read_text("utf-8")
