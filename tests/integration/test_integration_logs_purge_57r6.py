"""5.7R.6(M-3): 옛 색인의 `api-request-blob` 원문이 purge + 재수집 뒤 검색·상세에 없다.

"옛 색인"은 원문을 저장하던 규칙(사용자 `extra_row_rules`, 5.5R.34 이전 동작과 같음)으로 수집해
만든다. 규칙을 지운 뒤 다시 수집해도 색인은 그대로(INSERT OR IGNORE)이고, purge 뒤 재수집하면
지금 기본 규칙(크기·해시만)으로 다시 들어간다. 행 모양은 합성이다(실제 기록 아님).
`mod-logs`가 꺼진 서버에는 경로가 없다(404).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

MARKER = "PURGE-BLOB-MARKER-57r6"
SOURCE = "claude-code-jsonl"
BLOB: dict[str, Any] = {
    "type": "api-request-blob",
    "id": "blob-1",
    "sessionId": "S",
    "timestamp": "2026-10-27T00:00:00Z",
    "message": {"role": "user", "content": [{"type": "text", "text": f"본문 {MARKER}"}]},
}
REENABLE = [{"match": {"/type": "api-request-blob"}, "category": "meta", "title": "요청 본문"}]
QUIET = {"startup_scan": False, "scan_interval_seconds": 0}


def _settings(root: Path, rules: list[dict[str, Any]] | None) -> dict[str, Any]:
    # 5.7R.30 후속: 등록된 프로젝트(/w = 키 -w)의 세션만 읽는다.
    config: dict[str, Any] = {"roots": [str(root)], "project_scope": "registered"}
    if rules is not None:
        config["classifier"] = {"config": {"extra_row_rules": rules}}
    return {"logs": {"sources": [{"id": SOURCE, "enabled": True, "config": config}]}}


def _visible(client: Any) -> tuple[int, str]:
    """(본문 검색 결과 수, 모든 이벤트 상세 덤프)."""
    found = client.get(f"{API}/logs/events", params={"q": MARKER}).json()["items"]
    items = client.get(f"{API}/logs/events", params={"limit": 200}).json()["items"]
    details = [client.get(f"{API}/logs/events/{e['uid']}").json() for e in items]
    return len(found), json.dumps(details, ensure_ascii=False)


def test_purge_then_rescan_drops_old_blob_body(tmp_path: Path) -> None:
    root = tmp_path / "claude" / "projects"
    session = root / "-w" / "S.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text(json.dumps(BLOB, ensure_ascii=False) + "\n", encoding="utf-8")
    original = session.read_bytes()
    settings = make_settings(tmp_path / "srv", options={"mod-logs": QUIET})
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / "empty-claude")}
    with server(settings, environ=env) as client:
        project = {"id": "w", "name": "W", "working_directory": "/w"}
        assert client.post(f"{API}/projects", json=project).status_code == 201
        put = client.put(f"{API}/settings", json=_settings(root, REENABLE))
        assert put.status_code == 200, put.text
        assert client.post(f"{API}/logs/scan", json={"source_ids": [SOURCE]}).json()["new_events"]
        found, dumped = _visible(client)
        assert found == 1
        assert MARKER in dumped  # 옛 색인: 원문이 있다

        # 기본 규칙으로 돌려도 이미 색인된 원문은 그대로다(K55-2).
        assert client.put(f"{API}/settings", json=_settings(root, None)).status_code == 200
        client.post(f"{API}/logs/scan", json={"source_ids": [SOURCE]})
        assert _visible(client)[0] == 1

        body = {"sources": [SOURCE], "categories": ["meta"]}
        dry = client.post(f"{API}/logs/index/purge", json=body).json()
        assert dry["dry_run"] is True
        assert dry["events"] == 1
        assert _visible(client)[0] == 1  # dry_run은 지우지 않는다

        real = client.post(f"{API}/logs/index/purge", json={**body, "dry_run": False}).json()
        assert (real["dry_run"], real["events"]) == (False, 1)
        assert real["cursors"] >= 1
        rescan = client.post(f"{API}/logs/scan", json={"source_ids": [SOURCE]}).json()
        assert rescan["new_events"] == 1
        found, dumped = _visible(client)
        assert found == 0
        assert MARKER not in dumped
        assert "api-request-blob" in dumped  # 이벤트는 다시 있다(크기·해시만)
    assert session.read_bytes() == original  # 원본은 읽기 전용


def test_purge_route_absent_when_logs_module_disabled(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "off", modules={"disabled": ["mod-logs"]})
    with server(settings) as client:
        res = client.post(f"{API}/logs/index/purge", json={"dry_run": True})
        assert res.status_code == 404
