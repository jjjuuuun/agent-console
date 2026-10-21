"""5.2R.34: 유효 설정 경로의 ``?project=`` — 범위 층 공급자(``settings.scope_layers``)가 준 층을
공통 바로 아래에 끼운다. 이 연동은 범위의 뜻을 모른다(공급자 없으면 무시)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Issue
from agent_console_link_definitions_teams import SCOPE_LAYERS, ScopeLayersSource, module
from agent_console_mod_definitions import module as definitions
from agent_console_modkit import BaseServices, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_teams import Layer
from agent_console_teams.testing import Kit

TOKEN = "t" * 32
API = "/api/v1"
KIT = Kit()


@dataclass
class _Described:
    descriptor: Any


@dataclass
class _Registries:
    """플러그인 레지스트리 묶음 흉내(ac-teams 테스트 도구의 노드·엣지 타입)."""

    node_types: Registry[Any] = field(default_factory=lambda: Registry("node_types"))
    edge_types: Registry[Any] = field(default_factory=lambda: Registry("edge_types"))
    delegation_strategies: Registry[Any] = field(default_factory=lambda: Registry("s"))
    backends: Registry[Any] = field(default_factory=lambda: Registry("backends"))

    def __post_init__(self) -> None:
        for d in KIT.node_types:
            self.node_types.register(d.id, _Described(d))
        for e in KIT.edge_types:
            self.edge_types.register(e.id, _Described(e))


@dataclass(frozen=True)
class _Found:
    layers: Sequence[Layer] = ()
    warnings: Sequence[Issue] = ()


@dataclass
class _Scopes:
    asked: list[str] = field(default_factory=list)

    def scope_layers(self, scope_id: str) -> _Found:
        self.asked.append(scope_id)
        if scope_id == "p":
            return _Found([Layer("scope", "범위", {"working_directory": "/p"}, "scope:p")])
        return _Found(warnings=[Issue(severity="warning", code="t.unknown", message="없음")])


def _client(tmp_path: Path, scopes: _Scopes | None) -> TestClient:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_Registries(),
    )
    extra: list[Any] = []
    if scopes is not None:

        def build(ctx: ModuleContext) -> ModuleParts:
            ctx.provide(SCOPE_LAYERS, scopes)
            return ModuleParts()

        extra.append(fake_module("t-scopes", kind="link", provides=[SCOPE_LAYERS], on_build=build))
    assembly = assemble([definitions, module, *extra], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _seed(client: TestClient) -> None:
    agent = {"id": "a1", "name": "A"}
    assert client.post(f"{API}/agents", json=agent).status_code == 201
    graph = KIT.graph([KIT.person(), KIT.worker("a", "a1")], [KIT.edge("e1", "entry", "me", "a")])
    body = graph.model_dump(mode="json", exclude_none=True)
    assert client.post(f"{API}/graphs", json=body).status_code == 201


def test_project_query_inserts_scope_layer(tmp_path: Path) -> None:
    scopes = _Scopes()
    assert isinstance(scopes, ScopeLayersSource)
    with _client(tmp_path, scopes) as client:
        _seed(client)
        url = f"{API}/graphs/team/nodes/a/effective-settings"
        body = client.get(url, params={"project": "p"}).json()
        assert body["value"]["working_directory"] == "/p"
        assert [layer["id"] for layer in body["layers"]][:2] == ["common", "scope"]
        assert client.get(url).json()["value"].get("working_directory") is None
        assert scopes.asked == ["p"]  # 질의가 없으면 공급자를 부르지 않는다
        other = client.get(url, params={"project": "x"}).json()
        assert [w["code"] for w in other["warnings"]] == ["t.unknown"]
        agent = client.get(f"{API}/agents/a1/effective-settings", params={"project": "p"}).json()
        assert agent["value"]["working_directory"] == "/p"


def test_without_provider_project_is_ignored(tmp_path: Path) -> None:
    with _client(tmp_path, None) as client:
        _seed(client)
        url = f"{API}/graphs/team/nodes/a/effective-settings"
        assert client.get(url, params={"project": "p"}).json() == client.get(url).json()
