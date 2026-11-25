"""REL.14(REL.12 조건 4, REL.11 K-5·K-7·K-8): 옛 키가 남은 workspace로 서버가 시작하고 안내만 한다.

- workspace `settings.yaml`의 `projects.new_definition_scope`·`logs.projects` → 시작(health 200),
  `/server-info` warnings에 info `settings.ignored_key` 두 개(`projects`·`logs.projects`).
- 옛 등록부(`working_directory`)와 폴더 `project.yaml`의 옛 키(`working_directory`·`log_projects`·
  `uses`·`import_mode`) → `GET /projects` 200, 폴더 인식.
- 서버 설정 `modules.options.mod-projects.snapshot_ttl_seconds`(읽지 않음) → 시작.
- 지운 옛 범위 경로 3개는 405이고 OpenAPI에 없다.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_console_server.testing import API, make_settings, server

QUIET_LOGS = {"startup_scan": False, "scan_interval_seconds": 0}
REMOVED_PATHS = ("/projects/move-plan", "/projects/move", "/projects/scope-issues")


def _old_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "projects").mkdir(parents=True)
    (ws / "settings.yaml").write_text(
        "projects:\n"
        "  new_definition_scope: {agent: project}\n"
        "  fallback: shared\n"
        "logs:\n"
        "  projects:\n"
        "    groups: [{id: g, match: ['/w/**']}]\n"
        "    ungrouped: none\n",
        encoding="utf-8",
    )
    folder = tmp_path / "work" / "demo"
    (folder / ".agent-console").mkdir(parents=True)
    # 옛 등록부: 폴더를 `working_directory`로 적었다(읽을 때 `folder`로 옮긴다).
    (ws / "projects" / "demo.yaml").write_text(
        json.dumps({"id": "demo", "name": "데모", "working_directory": str(folder)}),
        encoding="utf-8",
    )
    manifest = {
        "format": 1,
        "id": "demo",
        "name": "데모",
        "working_directory": str(folder),
        "log_projects": ["grp-a"],
        "uses": [],
        "import_mode": "all",
    }
    (folder / ".agent-console" / "project.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def test_old_keys_start_server_with_info_only(tmp_path: Path) -> None:
    folder = _old_workspace(tmp_path)
    settings = make_settings(
        tmp_path,
        options={"mod-projects": {"snapshot_ttl_seconds": 5}, "mod-logs": QUIET_LOGS},
    )
    with server(settings) as client:
        assert client.get(f"{API}/health").status_code == 200

        info = client.get(f"{API}/server-info")
        assert info.status_code == 200
        ignored = [w for w in info.json()["warnings"] if w["code"] == "settings.ignored_key"]
        assert sorted(w["details"]["key"] for w in ignored) == ["logs.projects", "projects"]
        assert {w["severity"] for w in ignored} == {"info"}

        assert client.get(f"{API}/logs/sources").status_code == 200
        assert client.get(f"{API}/logs/sessions").status_code == 200

        listed = client.get(f"{API}/projects")
        assert listed.status_code == 200, listed.text
        [view] = listed.json()
        assert view["project"]["id"] == "demo"
        assert view["project"]["folder"] == str(folder)
        assert view["status"] == "ready"
        for key in ("working_directory", "log_projects", "uses", "import_mode"):
            assert key not in view["project"]

        for path in REMOVED_PATHS:
            response = client.post(f"{API}{path}", json={})
            assert response.status_code == 405, (path, response.text)
        paths = client.get(f"{API}/openapi.json").json()["paths"]
        assert not {f"{API}{p}" for p in REMOVED_PATHS} & set(paths)

        # 옛 키는 읽고 무시할 뿐 파일에서 지우지 않는다(사용자가 지운다).
        assert "new_definition_scope" in (tmp_path / "ws" / "settings.yaml").read_text("utf-8")
