"""5.7R.8(X32): 선택 여러 제공자 포트 ``architecture.profile_checks``.

제공자가 이 모듈의 포트를 요구해 더 늦게 만들어져도(부를 때 읽음) 목록 ``issues`` 수·상세
``problems``·``POST /architecture/profiles/check``에 결과가 더해진다. 예외를 낸 검사는 건너뛰고,
제공자가 없으면 기본 검사만 한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Issue, WorkspaceSettings
from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_mod_architecture import ARCHITECTURE_CATALOG, PROFILE_CHECKS, module
from agent_console_mod_architecture.testing import static_settings_module
from agent_console_modkit import (
    BaseServices,
    ExtensionRegistries,
    ModuleContext,
    ModuleParts,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module

TOKEN = "t" * 32
API = "/api/v1"
CODE = "test.extra"


class CellCountCheck:
    """칸마다 경고 하나(테스트용 검사 보탬)."""

    def __init__(self) -> None:
        self.seen: list[str | None] = []

    def check(self, profile: ArchitectureProfile, profile_id: str | None) -> list[Issue]:
        self.seen.append(profile_id)
        return [
            Issue(severity="warning", code=CODE, message="칸", path=f"/cells/{cid}")
            for cid in profile.cells
        ]


class BrokenCheck:
    def check(self, profile: ArchitectureProfile, profile_id: str | None) -> list[Issue]:
        raise RuntimeError("boom")


def _provider(*checks: Any) -> Any:
    def build(ctx: ModuleContext) -> ModuleParts:
        assert ctx.port(ARCHITECTURE_CATALOG) is not None  # 카탈로그보다 늦게 만들어진다
        for check in checks:
            ctx.provide(PROFILE_CHECKS, check)
        return ModuleParts()

    return fake_module(
        "checks-provider",
        kind="link",
        provides=[PROFILE_CHECKS],
        requires=[ARCHITECTURE_CATALOG],
        on_build=build,
    )


@contextmanager
def _client(*modules: Any) -> Iterator[TestClient]:
    base = BaseServices(registries=ExtensionRegistries())
    assembly = assemble([module, *modules], None, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _settings(flow: dict[str, Any]) -> Any:
    section = {"include_defaults": False, "profiles": {"flow": flow}}
    return static_settings_module(WorkspaceSettings.model_validate({"architecture": section}))


def test_checks_add_to_list_detail_and_check(flow: dict[str, Any]) -> None:
    extra = CellCountCheck()
    with _client(_settings(flow), _provider(extra, BrokenCheck())) as client:
        listing = client.get(f"{API}/architecture/profiles").json()
        assert [(p["id"], p["issues"]) for p in listing["profiles"]] == [("flow", 2)]
        detail = client.get(f"{API}/architecture/profiles/flow").json()
        assert [(i["code"], i["path"]) for i in detail["problems"]] == [
            (CODE, "/cells/ask"),
            (CODE, "/cells/work"),
        ]
        checked = client.post(
            f"{API}/architecture/profiles/check", json={"id": "draft", "profile": flow}
        ).json()
        assert [i["code"] for i in checked["issues"]] == [CODE, CODE]
        assert extra.seen[-1] == "draft"
        invalid = client.post(
            f"{API}/architecture/profiles/check", json={"profile": {"cells": 3}}
        ).json()
        assert [i["code"] for i in invalid["issues"]] == ["architecture.invalid"]


def test_without_provider_only_builtin_checks(flow: dict[str, Any]) -> None:
    with _client(_settings(flow)) as client:
        listing = client.get(f"{API}/architecture/profiles").json()
        assert [(p["id"], p["issues"]) for p in listing["profiles"]] == [("flow", 0)]
        checked = client.post(f"{API}/architecture/profiles/check", json={"profile": flow})
        assert checked.status_code == 200
        assert checked.json()["issues"] == []
