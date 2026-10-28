"""4R.12: 로그·추적 연동(link-logs-trace)을 서버 조립 수준에서 확인한다.

- 설치된 서버에서 `link-logs-trace`가 켜지고 웹 역할 `logs:trace`를 낸다.
- Claude Code 형식 세션(메인 + 서브에이전트 메타)을 수집하면 `/logs/sessions/{id}/trace`가
  위임 호출 id ↔ 메타 `toolUseId`로 부모를 잇는다.
- 연동을 끄면 그 경로만 404이고 로그 경로는 돈다. `mod-logs`를 끄면 연동은 `unsatisfied`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

SESSION = "22222222-2222-4222-8222-222222222222"
QUIET = {"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}}


def _row(kind: str, uuid: str, parent: str | None, second: int, message: Any, **extra: Any) -> str:
    row = {
        "sessionId": SESSION,
        "cwd": "/work/demo",
        "type": kind,
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": f"2026-10-01T00:00:{second:02d}.000Z",
        "message": message,
        **extra,
    }
    return json.dumps(row, ensure_ascii=False)


def _write_session(root: Path) -> Path:
    """projects/<프로젝트>/<세션>.jsonl + subagents/agent-x1.jsonl·.meta.json(합성)."""
    project = root / "projects" / "-work-demo"
    subagents = project / SESSION / "subagents"
    subagents.mkdir(parents=True)
    task = {
        "type": "tool_use",
        "id": "toolu_task",
        "name": "Task",
        "input": {"subagent_type": "qa"},
    }
    main = [
        _row("user", "u1", None, 0, {"role": "user", "content": "검사해 줘"}),
        _row(
            "assistant",
            "a1",
            "u1",
            1,
            {"id": "m1", "role": "assistant", "model": "test", "content": [task]},
        ),
        _row(
            "user",
            "u2",
            "a1",
            5,
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_task", "content": "끝"}],
            },
            toolUseResult={"agentId": "x1"},
        ),
    ]
    (project / f"{SESSION}.jsonl").write_text("\n".join(main) + "\n", encoding="utf-8")
    sub = [
        _row("user", "s1", None, 2, {"role": "user", "content": "테스트를 돌려"}, agentId="x1"),
    ]
    (subagents / "agent-x1.jsonl").write_text("\n".join(sub) + "\n", encoding="utf-8")
    meta = {"agentType": "qa", "description": "검사", "toolUseId": "toolu_task"}
    (subagents / "agent-x1.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return root / "projects"


def _enable(client: Any, roots: Path) -> None:
    # 5.7R.30 후속: 로그는 앱에 등록된 프로젝트 폴더의 세션만 읽는다(픽스처 키 -work-demo).
    project = {"id": "demo", "name": "Demo", "folder": "/work/demo"}
    assert client.post(f"{API}/projects", json=project).status_code == 201
    settings = client.get(f"{API}/settings").json()
    config = {"roots": [str(roots)], "project_scope": "registered"}
    entry = {"id": "claude-code-jsonl", "enabled": True, "config": config}
    settings["logs"] = {"sources": [entry]}
    assert client.put(f"{API}/settings", json=settings).status_code == 200
    assert client.post(f"{API}/logs/scan").status_code == 202


def test_link_is_active_with_web_role_and_builds_trace(tmp_path: Path) -> None:
    roots = _write_session(tmp_path / "claude")
    with server(make_settings(tmp_path, options=QUIET)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos["link-logs-trace"]["status"] == "active", infos["link-logs-trace"]
        assert infos["link-logs-trace"]["web_roles"] == ["logs:trace"]
        assert infos["link-logs-trace"]["kind"] == "link"
        _enable(client, roots)
        res = client.get(f"{API}/logs/sessions/{SESSION}/trace")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["run_id"] == SESSION
        spans = {s["id"]: s for s in body["spans"]}
        sub = spans["thread:agent-x1"]
        assert sub["parent_id"] == f"thread:{SESSION}"
        assert sub["tool_use_id"] == "toolu_task"
        assert sub["kind"] == "delegated"
        assert spans[f"thread:{SESSION}"]["parent_id"] is None
        assert client.get(f"{API}/logs/sessions/none/trace").status_code == 404


def test_disabled_link_route_is_404(tmp_path: Path) -> None:
    roots = _write_session(tmp_path / "claude")
    settings = make_settings(tmp_path, options=QUIET, modules={"disabled": ["link-logs-trace"]})
    with server(settings) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses["link-logs-trace"] == "disabled"
        _enable(client, roots)
        assert client.get(f"{API}/logs/sessions/{SESSION}/trace").status_code == 404
        assert client.get(f"{API}/logs/sessions/{SESSION}/timeline").status_code == 200


def test_without_logs_module_link_is_unsatisfied(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["mod-logs"]})
    with server(settings) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos["link-logs-trace"]["status"] == "unsatisfied"
        assert "logs.query" in json.dumps(infos["link-logs-trace"])
        assert client.get(f"{API}/logs/sessions/{SESSION}/trace").status_code == 404
