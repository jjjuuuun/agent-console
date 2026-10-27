"""5.5R.21: 구조도 기본 프로필을 끄고 바꿔도 나머지가 동작한다(R0.1, R8.8).

세 경로를 서버 조립 수준에서 본다. 각 경로마다 로그 조회, 실행(fake-agent), 사용량,
다른 모듈(구조도 API)이 정상이고, 구조도는 "프로필 없음"(404 + 빈 목록) 또는 사용자 프로필을 낸다.
 1. ``architecture.include_defaults: false``
 2. 기본 프로필 id를 ``null``로 지움(``profiles: {id: null}``)
 3. 같은 id의 사용자 프로필로 바꿈
테스트 데이터는 전부 임시 폴더 안에서 만든다(저장소에 사용자 데이터를 두지 않는다).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_server.testing import API, make_settings, seed, server, wait_run

DEFAULT_ID = "agent-architecture"
QUIET = {"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}}
MINE: dict[str, Any] = {
    "title": "내 구조도",
    "cells": {
        "ask": {"when": {"all": [{"path": "/category", "op": "eq", "value": "input"}]}},
    },
    "unassigned": True,
}


def _write_logs(root: Path) -> None:
    root.mkdir(parents=True)
    base = {"schema_version": 1, "session": "S1", "thread": "main"}
    rows = [
        {**base, "category": "input", "title": "요청", "time": 1_760_000_000},
        {**base, "category": "tool_call", "title": "호출", "tool": "Read", "time": 1_760_000_001},
    ]
    (root / "a.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _configure(client: TestClient, root: Path, architecture: dict[str, Any]) -> None:
    body = client.get(f"{API}/settings").json()
    body["logs"] = {
        "sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}]
    }
    body["architecture"] = architecture
    assert client.put(f"{API}/settings", json=body).status_code == 200
    assert client.post(f"{API}/logs/scan").status_code == 202


def _others_work(client: TestClient) -> None:
    """로그·실행·사용량·모듈 목록이 구조도 상태와 무관하게 동작한다."""
    events = client.get(f"{API}/logs/events", params={"session": "S1"})
    assert events.status_code == 200, events.text
    assert len(events.json()["items"]) == 2
    assert client.get(f"{API}/logs/sessions").status_code == 200
    statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
    assert statuses["mod-logs"] == statuses["mod-runs"] == "active"
    assert statuses["mod-architecture"] == statuses["link-logs-architecture"] == "active"
    seed(client)
    run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "hi"}})
    assert run.status_code == 202, run.text
    assert wait_run(client, run.json()["id"])["run"]["status"] == "completed"
    assert client.get(f"{API}/usage", params={"parts": "tokens"}).status_code == 200
    assert client.get(f"{API}/health").status_code == 200


@pytest.mark.parametrize(
    "architecture",
    [
        {"include_defaults": False},
        {"profiles": {DEFAULT_ID: None}},
    ],
    ids=["include_defaults-false", "default-id-null"],
)
def test_defaults_off_gives_no_rules_and_rest_works(
    tmp_path: Path, architecture: dict[str, Any]
) -> None:
    root = tmp_path / "logs"
    _write_logs(root)
    with server(make_settings(tmp_path / "s", options=QUIET)) as client:
        # 대조: 설정 전에는 기본 프로필이 보인다(꺼진 효과를 확인하기 위한 기준선).
        before = client.get(f"{API}/architecture/profiles").json()
        assert [p["id"] for p in before["profiles"]] == [DEFAULT_ID]
        _configure(client, root, architecture)
        listing = client.get(f"{API}/architecture/profiles").json()
        # 끈 기본 프로필은 "꺼짐"으로 남아 [다시 켜기]가 가능하다(null 경로). 쓸 프로필은 0개.
        assert [p["id"] for p in listing["profiles"] if not p["disabled"]] == []
        assert all(p["disabled"] for p in listing["profiles"])
        assert listing["default_profile"] is None
        res = client.get(f"{API}/logs/architecture", params={"session": "S1"})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "architecture.profile_not_found"
        _others_work(client)
        # 다시 켜면 기본 프로필이 돌아온다(끄기는 되돌릴 수 있다).
        _configure(client, root, {})
        back = client.get(f"{API}/architecture/profiles").json()
        assert [p["id"] for p in back["profiles"]] == [DEFAULT_ID]
        assert client.get(f"{API}/logs/architecture", params={"session": "S1"}).status_code == 200


def test_same_id_user_profile_replaces_default(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write_logs(root)
    with server(make_settings(tmp_path / "s", options=QUIET)) as client:
        _configure(client, root, {"profiles": {DEFAULT_ID: MINE}})
        listing = client.get(f"{API}/architecture/profiles").json()
        assert [(p["id"], p["title"], p["origin"]) for p in listing["profiles"]] == [
            (DEFAULT_ID, "내 구조도", "user")
        ]
        res = client.get(f"{API}/logs/architecture", params={"session": "S1"})
        assert res.status_code == 200, res.text
        view = res.json()
        assert view["profile"] == DEFAULT_ID
        assert [c["id"] for c in view["cells"]] == ["ask"]  # 기본 프로필 칸이 섞이지 않는다
        _others_work(client)
