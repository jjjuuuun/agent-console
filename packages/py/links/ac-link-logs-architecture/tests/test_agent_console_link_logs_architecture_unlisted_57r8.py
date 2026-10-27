"""5.7R.8(M-4, X32): 프로필 조건이 목록 본문에 없는 경로를 보면 경고.

- 연동이 켜지면 `/detail/…`·`/raw/…` 조건이 목록 `issues`·상세 `problems`·검사 응답에 warning
  `architecture.condition_path_unlisted`로 보인다(접두는 설치자 옵션 기본값 — 데이터).
- 설치자 옵션으로 접두를 바꾸거나 비울 수 있다.
- 모듈 매트릭스: 연동이 꺼지면 경고는 없고 검사는 정상이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, KnownIssueCodes, WorkspaceSettings
from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_link_logs_architecture import MODULE_ID, UnlistedPathCheck, module
from agent_console_link_logs_architecture.settings import (
    DEFAULT_UNLISTED_PATHS,
    LogsArchitectureSettings,
)
from agent_console_mod_architecture import module as architecture_module
from agent_console_mod_logs import module as logs_module
from agent_console_mod_logs.testing import static_settings_module
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

API = "/api/v1"
TOKEN = "t" * 32
CODE = KnownIssueCodes.ARCHITECTURE_CONDITION_PATH_UNLISTED
QUIET = {"startup_scan": False, "scan_interval_seconds": 0}

PROFILE: dict[str, Any] = {
    "cells": {
        "ok": {"when": {"all": [{"path": "/category", "op": "eq", "value": "tool"}]}},
        "deep": {"when": {"all": [{"path": "/detail/input/command", "op": "exists"}]}},
    },
    "edges": [
        {
            "id": "e",
            "from": "ok",
            "to": "deep",
            "when": {"any": [{"path": "/raw", "op": "exists"}]},
        }
    ],
}


def _client(
    tmp_path: Path, *, disabled: Sequence[str] = (), link_options: Mapping[str, Any] | None = None
) -> TestClient:
    settings = WorkspaceSettings.model_validate(
        {
            "logs": {"sources": []},
            "architecture": {"include_defaults": False, "profiles": {"p": PROFILE}},
        }
    )
    options: dict[str, Any] = {"mod-logs": dict(QUIET)}
    if link_options is not None:
        options[MODULE_ID] = dict(link_options)
    services = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly = assemble(
        [logs_module, architecture_module, module, static_settings_module(settings)],
        ModulesConfig(options=options, disabled=list(disabled)),
        base=services,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _unlisted(issues: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(i["path"], i["details"]["prefix"]) for i in issues if i["code"] == CODE]


def test_default_prefixes_are_data() -> None:
    assert LogsArchitectureSettings().unlisted_paths == list(DEFAULT_UNLISTED_PATHS)
    profile = ArchitectureProfile.model_validate(PROFILE)
    found = UnlistedPathCheck(DEFAULT_UNLISTED_PATHS).check(profile, "p")
    assert [i.path for i in found] == ["/cells/deep/when/all/0/path", "/edges/0/when/any/0/path"]
    assert UnlistedPathCheck([]).check(profile, "p") == []


def test_link_on_warns_in_list_detail_and_check(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        states = {m["id"]: m["state"] for m in client.get(f"{API}/modules").json()}
        assert states[MODULE_ID] == "active"
        listing = client.get(f"{API}/architecture/profiles").json()
        assert [(p["id"], p["issues"]) for p in listing["profiles"]] == [("p", 2)]
        detail = client.get(f"{API}/architecture/profiles/p").json()
        assert _unlisted(detail["problems"]) == [
            ("/cells/deep/when/all/0/path", "/detail"),
            ("/edges/0/when/any/0/path", "/raw"),
        ]
        assert all(i["severity"] == "warning" for i in detail["problems"])
        checked = client.post(
            f"{API}/architecture/profiles/check", json={"id": "p", "profile": PROFILE}
        )
        assert checked.status_code == 200
        assert len(_unlisted(checked.json()["issues"])) == 2


def test_installer_option_changes_prefixes(tmp_path: Path) -> None:
    with _client(tmp_path, link_options={"unlisted_paths": ["/category"]}) as client:
        detail = client.get(f"{API}/architecture/profiles/p").json()
        assert _unlisted(detail["problems"]) == [("/cells/ok/when/all/0/path", "/category")]
    with _client(tmp_path, link_options={"unlisted_paths": []}) as client:
        detail = client.get(f"{API}/architecture/profiles/p").json()
        assert _unlisted(detail["problems"]) == []


@pytest.mark.parametrize(
    "disabled",
    [[MODULE_ID], ["mod-logs"]],
    ids=["link-off", "logs-off"],
)
def test_module_matrix_link_off_means_no_warning(tmp_path: Path, disabled: list[str]) -> None:
    with _client(tmp_path, disabled=disabled) as client:
        states = {m["id"]: m["state"] for m in client.get(f"{API}/modules").json()}
        assert states["mod-architecture"] == "active"
        assert states[MODULE_ID] != "active"
        listing = client.get(f"{API}/architecture/profiles").json()
        assert [(p["id"], p["issues"]) for p in listing["profiles"]] == [("p", 0)]
        checked = client.post(
            f"{API}/architecture/profiles/check", json={"id": "p", "profile": PROFILE}
        )
        assert checked.status_code == 200
        assert checked.json()["issues"] == []
