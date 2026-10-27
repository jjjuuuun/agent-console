"""5.7R.8(M-4, X32): 설치된 서버에서 프로필 검사 보탬(목록 본문 밖 조건 경로 경고) 모듈 매트릭스.

- 전부 켜짐: `link-logs-architecture`가 `architecture.profile_checks`를 내고, 검사 응답에 warning
  `architecture.condition_path_unlisted`가 보인다.
- 연동 꺼짐·로그 꺼짐(연동 unsatisfied): 경고 없음, 검사는 정상(200, 이슈 0).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_console_server.testing import API, make_settings, server

QUIET = {"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}}
CODE = "architecture.condition_path_unlisted"
PROFILE: dict[str, Any] = {
    "cells": {
        "a": {"when": {"all": [{"path": "/category", "op": "eq", "value": "tool"}]}},
        "b": {"when": {"all": [{"path": "/detail/input", "op": "exists"}]}},
    },
}


def _check(client: Any) -> list[dict[str, Any]]:
    res = client.post(f"{API}/architecture/profiles/check", json={"id": "p", "profile": PROFILE})
    assert res.status_code == 200, res.text
    issues: list[dict[str, Any]] = res.json()["issues"]
    return issues


def test_all_on_warns(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, options=QUIET)) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses["link-logs-architecture"] == "active"
        issues = _check(client)
        assert [(i["code"], i["path"], i["details"]["prefix"]) for i in issues] == [
            (CODE, "/cells/b/when/all/0/path", "/detail")
        ]


@pytest.mark.parametrize(
    ("off", "state"),
    [("link-logs-architecture", "disabled"), ("mod-logs", "unsatisfied")],
)
def test_link_off_no_warning(tmp_path: Path, off: str, state: str) -> None:
    settings = make_settings(tmp_path, options=QUIET, modules={"disabled": [off]})
    with server(settings) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses["link-logs-architecture"] == state
        assert statuses["mod-architecture"] == "active"
        assert _check(client) == []
