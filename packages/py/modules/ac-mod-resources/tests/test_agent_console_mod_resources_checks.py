"""mod-resources: 저장 전 정의 검사(``definitions.checks``)를 만들기·저장 응답에 싣는다(5.7R.28).

error는 422(종류 검사와 같은 경로), warning·info는 저장하고 ``X-Console-Issues`` 헤더로 싣는다.
제공 모듈이 없으면 헤더도 없다. 검사 하나가 예외를 내도 저장은 계속된다. 같은 코드·path의
이슈는 한 번만 싣는다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Issue
from agent_console_mod_resources import DEFINITION_CHECKS, DefinitionCheck, module
from agent_console_mod_resources.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module

TOKEN = "t" * 32
API = "/api/v1"
SKILL = {"id": "review", "type": "skill", "name": "리뷰", "config": {"name": "review"}}


class _Check:
    """리소스 이름으로 이슈 심각도를 고르는 가짜 검사(값은 메시지에 담지 않는다)."""

    def __init__(self, code: str = "test.flag") -> None:
        self.code = code
        self.calls: list[str] = []

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        self.calls.append(kind)
        if kind != "resource":
            return []
        flag = document.get("name")
        if flag not in ("warning", "info", "error"):
            return []
        return [Issue(severity=flag, code=self.code, message="플래그", path="/name")]


class _Broken:
    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        raise RuntimeError("검사 실패")


def _provider(*checks: Any) -> Any:
    def build(ctx: Any) -> None:
        for check in checks:
            ctx.provide(DEFINITION_CHECKS, check)

    return fake_module("checks", provides=[DEFINITION_CHECKS], on_build=build)


def _assembly(tmp_path: Path, *extra: Any) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    return assemble([module, local_definitions_module(), *extra], base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _with(flag: str) -> dict[str, Any]:
    return {**SKILL, "name": flag}


def test_protocol_matches_check() -> None:
    assert isinstance(_Check(), DefinitionCheck)


def test_warning_saved_and_carried_in_header(tmp_path: Path) -> None:
    check = _Check()
    with _client(_assembly(tmp_path, _provider(check))) as client:
        created = client.post(f"{API}/resources", json=_with("warning"))
        assert created.status_code == 201
        [issue] = json.loads(created.headers["x-console-issues"])
        assert (issue["severity"], issue["code"], issue["path"]) == (
            "warning",
            "test.flag",
            "/name",
        )
        etag = created.headers["etag"]
        info = client.put(f"{API}/resources/review", json=_with("info"), headers={"If-Match": etag})
        assert info.status_code == 200
        assert json.loads(info.headers["x-console-issues"])[0]["severity"] == "info"
        clean = client.put(
            f"{API}/resources/review",
            json=SKILL,
            headers={"If-Match": info.headers["etag"]},
        )
        assert clean.status_code == 200
        assert "x-console-issues" not in clean.headers
        assert set(check.calls) == {"resource"}


def test_error_from_check_rejects_with_422(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path, _provider(_Check()))) as client:
        rejected = client.post(f"{API}/resources", json=_with("error"))
        assert rejected.status_code == 422
        [issue] = rejected.json()["error"]["details"]["issues"]
        assert issue["code"] == "test.flag"
        assert client.get(f"{API}/resources/review").status_code == 404


def test_without_provider_no_header(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        created = client.post(f"{API}/resources", json=_with("warning"))
        assert created.status_code == 201
        assert "x-console-issues" not in created.headers


def test_broken_check_skipped_and_duplicates_once(tmp_path: Path) -> None:
    provider = _provider(_Broken(), _Check(), _Check())
    with _client(_assembly(tmp_path, provider)) as client:
        created = client.post(f"{API}/resources", json=_with("warning"))
        assert created.status_code == 201
        assert len(json.loads(created.headers["x-console-issues"])) == 1
