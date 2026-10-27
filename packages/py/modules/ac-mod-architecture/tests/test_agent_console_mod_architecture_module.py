"""mod-architecture 조립: 혼자 켠 서버에서 조회·검사·단독 투영, 오류 본문, 끄기(R0), X23 플러그인.

design §5.5R.3 켜고 끄기 표 1행: ``mod-architecture``만 켜도 프로필 조회·검사·단독 투영 API가
동작한다.
모듈을 끄면 그 경로만 404이고 다른 모듈은 그대로다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from agent_console_architecture import ARCHITECTURE_PROFILES_GROUP, load_profile_plugins
from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_contracts.architecture import ArchitectureView
from agent_console_mod_architecture import (
    ARCHITECTURE_CATALOG,
    SETTINGS_INVALID,
    ArchitectureCatalogService,
    ArchitectureModuleSettings,
    module,
)
from agent_console_mod_architecture.plugins import load_plugins, profile_registry
from agent_console_mod_architecture.testing import static_settings_module
from agent_console_modkit import (
    BaseServices,
    ExtensionRegistries,
    ModuleParts,
    ModulesConfig,
    PluginLoadContext,
    PortKey,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module

TOKEN = "t" * 32
API = "/api/v1"
WARNINGS: PortKey[Any] = PortKey("server.warnings", multi=True)


def _other_module() -> Any:
    """다른 기능 흉내(구조도를 끄면 이 경로가 그대로 200인지 본다)."""

    def build(ctx: Any) -> ModuleParts:
        router = APIRouter()

        @router.get("/other")
        def other() -> dict[str, bool]:
            return {"ok": True}

        return ModuleParts(routers=[router])

    return fake_module("other-feature", on_build=build)


@contextmanager
def _client(
    *modules: Any,
    config: ModulesConfig | None = None,
    registries: Any = None,
) -> Iterator[TestClient]:
    base = BaseServices(registries=registries if registries is not None else ExtensionRegistries())
    assembly = assemble([module, *modules], config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _settings(section: dict[str, Any]) -> Any:
    return static_settings_module(WorkspaceSettings.model_validate({"architecture": section}))


def test_module_alone_lists_checks_and_projects(
    flow: dict[str, Any], broken: dict[str, Any], event_rows: list[dict[str, Any]]
) -> None:
    section = {"profiles": {"flow": flow, "bad": broken}, "default_profile": "flow"}
    with _client(_settings(section)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos["mod-architecture"]["state"] == "active"
        assert infos["mod-architecture"]["web_roles"] == ["architecture"]
        assert "architecture.catalog" in infos["mod-architecture"]["provides"]

        listing = client.get(f"{API}/architecture/profiles").json()
        user_rows = [(p["id"], p["origin"]) for p in listing["profiles"] if p["origin"] == "user"]
        assert user_rows == [("flow", "user"), ("bad", "user")]
        assert listing["default_profile"] == "flow"
        bad_info = next(p for p in listing["profiles"] if p["id"] == "bad")
        assert bad_info["issues"] >= 2

        detail = client.get(f"{API}/architecture/profiles/flow").json()
        assert detail["profile"]["title"] == "흐름"
        assert detail["problems"] == []
        assert detail["cells"] == 2

        check = client.post(
            f"{API}/architecture/profiles/check", json={"id": "x", "profile": {"cells": 3}}
        )
        assert check.status_code == 200
        assert [i["code"] for i in check.json()["issues"]] == ["architecture.invalid"]

        projected = client.post(f"{API}/architecture/project", json={"events": event_rows})
        assert projected.status_code == 200
        view = ArchitectureView.model_validate(projected.json())
        assert view.profile == "flow"
        assert {c.id: c.metrics["count"].value for c in view.cells} == {"ask": 1.0, "work": 2.0}
        assert view.unassigned is not None
        assert view.unassigned.metrics["count"].value == 1.0

        preview = client.post(
            f"{API}/architecture/project", json={"inline": flow, "inline_id": "draft"}
        ).json()
        assert (preview["profile"], preview["event_total"]) == ("draft", 0)


def test_errors_use_contract_codes(flow: dict[str, Any], event_rows: list[dict[str, Any]]) -> None:
    config = ModulesConfig(options={"mod-architecture": {"max_request_events": 3}})
    # 패키지 기본 프로필(5.5R.8)이 먼저 오므로 대체 대상은 default_profile로 정한다
    section = {"profiles": {"flow": flow}, "default_profile": "flow"}
    with _client(_settings(section), config=config) as client:
        missing = client.get(f"{API}/architecture/profiles/nope")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "architecture.profile_not_found"
        assert missing.json()["error"]["details"] == {"profile": "nope"}
        too_big = client.post(f"{API}/architecture/project", json={"events": event_rows})
        assert too_big.status_code == 422
        assert too_big.json()["error"]["code"] == "architecture.scope_too_large"
        assert too_big.json()["error"]["details"] == {"events": 4, "limit": 3}
        fallback = client.post(f"{API}/architecture/project", json={"profile": "nope"}).json()
        assert fallback["profile"] == "flow"
        assert [n["code"] for n in fallback["notes"]] == ["architecture.profile_fallback"]


def test_no_profiles_is_empty_200(event_rows: list[dict[str, Any]]) -> None:
    """``include_defaults: false``·프로필 0개 → 빈 목록 200(완료 기준). 투영은 404."""
    with _client(_settings({"include_defaults": False})) as client:
        listing = client.get(f"{API}/architecture/profiles")
        assert listing.status_code == 200
        assert listing.json() == {
            "profiles": [],
            "default_profile": None,
            "include_defaults": False,
        }
        projected = client.post(f"{API}/architecture/project", json={"events": event_rows})
        assert projected.status_code == 404
        assert projected.json()["error"]["code"] == "architecture.profile_not_found"


def test_without_workspace_settings_port_still_works() -> None:
    """설정 포트가 없으면 기본 + 플러그인 프로필만(사용자 설정 없음)."""
    with _client() as client:
        listing = client.get(f"{API}/architecture/profiles")
        assert listing.status_code == 200
        assert all(p["origin"] != "user" for p in listing.json()["profiles"])


def test_disabled_module_is_404_and_others_still_work(flow: dict[str, Any]) -> None:
    config = ModulesConfig(disabled=["mod-architecture"])
    with _client(_settings({"profiles": {"flow": flow}}), _other_module(), config=config) as client:
        statuses = {m["id"]: m["state"] for m in client.get(f"{API}/modules").json()}
        assert statuses["mod-architecture"] == "disabled"
        assert client.get(f"{API}/architecture/profiles").status_code == 404
        assert client.get(f"{API}/architecture/profiles/flow").status_code == 404
        assert (
            client.post(f"{API}/architecture/profiles/check", json={"profile": {}}).status_code
            == 404
        )
        assert client.post(f"{API}/architecture/project", json={}).status_code == 404
        assert client.get(f"{API}/other").json() == {"ok": True}


def test_settings_are_reread_and_invalid_parts_become_server_warnings(
    flow: dict[str, Any],
) -> None:
    current: dict[str, Any] = {"architecture": {"profiles": {"a": flow}}}

    def read() -> WorkspaceSettings:
        return WorkspaceSettings.model_validate(current)

    base = BaseServices(registries=ExtensionRegistries())
    assembly = assemble([module, static_settings_module(read)], None, base=base)
    service = assembly.port(ARCHITECTURE_CATALOG)
    assert isinstance(service, ArchitectureCatalogService)
    assert [p.id for p in service.profile_list().profiles if p.origin == "user"] == ["a"]
    warnings = [w for source in assembly.ports(WARNINGS) for w in source()]
    assert warnings == []
    current = {"architecture": {"profiles": {"a": flow, "b": {"cells": "x"}}}}
    assert [p.id for p in service.profile_list().profiles if p.origin == "user"] == ["a"]
    warnings = [w for source in assembly.ports(WARNINGS) for w in source()]
    assert [(w.code, w.path) for w in warnings] == [(SETTINGS_INVALID, "/architecture/profiles/b")]


def test_installer_settings_schema_has_labels() -> None:
    schema = ArchitectureModuleSettings.model_json_schema()
    for name in ("max_request_events", "max_scope_events"):
        field = schema["properties"][name]
        assert field["title"]
        assert field["description"]
        assert field["x-ui"]["tier"] == "advanced"
    bad = assemble(
        [module], ModulesConfig(options={"mod-architecture": {"nope": 1}}), base=BaseServices()
    )
    assert bad.report[0].state.value == "failed"


_PLUGIN = """
def profiles():
    return {"plug": {"title": "플러그인 프로필", "cells": {"c": {}}}}
"""


@pytest.fixture
def plugin_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    name = f"arch_mod_plugin_{tmp_path.name.replace('-', '_')}"
    (tmp_path / f"{name}.py").write_text(_PLUGIN, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return name


def test_plugin_profiles_from_host_registry(plugin_module: str) -> None:
    """X23: 호스트 묶음의 ``architecture_profiles`` 확장에 든 프로필이 ``plugin:`` 출처로 보인다."""
    registries = ExtensionRegistries()
    registry = profile_registry(registries)
    ep = EntryPoint(
        name="demo", value=f"{plugin_module}:profiles", group=ARCHITECTURE_PROFILES_GROUP
    )
    [report] = load_profile_plugins(registry, entry_points=[ep])
    assert report.status == "loaded"
    with _client(registries=registries) as client:
        rows = client.get(f"{API}/architecture/profiles").json()["profiles"]
        plug = next(p for p in rows if p["id"] == "plug")
        assert plug["origin"].startswith("plugin:")
        assert plug["cells"] == 1
    # 꺼진(enabled에 없는) 항목은 로더가 건너뛴다
    other = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=other, enabled=frozenset()))
    assert all(r.status == "skipped" for _group, r in reports)
    assert profile_registry(other).list() == []


def test_profile_registry_rejects_other_shapes() -> None:
    registries = ExtensionRegistries()
    registry = profile_registry(registries)
    raw: Any = {"p": {}}
    with pytest.raises(Exception, match="ProfileSource"):
        registry.register("raw", raw)
