"""5.2R.34: 유효 설정 경로의 ``?project=`` — 범위 층 공급자(``settings.scope_layers``)가 준 층을
공통 바로 아래에 끼운다. 이 연동은 범위의 뜻을 모른다(공급자 없으면 무시).

검증 11/08 D5: 저장된 정의를 읽는 경로는 같은 ``?project=``의 정의 공간(``definitions.spaces``)에서
읽는다(공간에만 있는 팀 구성의 실행 계획 200)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Issue
from agent_console_link_definitions_teams import (
    DEFINITIONS_SPACES,
    SCOPE_LAYERS,
    ScopeLayersSource,
    StoreResourceLookup,
    TeamViews,
    module,
)
from agent_console_mod_definitions import module as definitions
from agent_console_modkit import BaseServices, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore, MappedSpaces
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


# ---- 검증 11/08 D5: 공간에만 있는 팀 구성 ---------------------------------------


def _space_client(tmp_path: Path, space: Any) -> TestClient:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_Registries(),
    )

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(DEFINITIONS_SPACES, MappedSpaces({"p2": space}))
        return ModuleParts()

    spaces = fake_module("t-spaces", kind="link", provides=[DEFINITIONS_SPACES], on_build=build)
    assembly = assemble([definitions, module, spaces], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_space_only_graph_routes_read_the_space(tmp_path: Path) -> None:
    """``?project=``의 공간에만 있는 팀 구성·에이전트: 실행 계획·유효 설정·묶음 미리보기·사용처가
    200(라이브러리에서 찾지 않는다). 질의가 없으면 라이브러리라 404, 모르는 공간은 404."""
    space = InMemoryDefinitionStore(DEFAULT_KINDS)
    space.create("agent", {"id": "a1", "name": "A", "model": "m-space"})
    graph = KIT.graph([KIT.person(), KIT.worker("a", "a1")], [KIT.edge("e1", "entry", "me", "a")])
    graph = graph.model_copy(update={"id": "pt"})
    space.create("graph", graph.model_dump(mode="json", exclude_none=True))
    p2 = {"project": "p2"}
    with _space_client(tmp_path, space) as client:
        assert client.get(f"{API}/graphs/pt", params=p2).status_code == 200
        plan = client.get(f"{API}/graphs/pt/plan", params=p2)
        assert plan.status_code == 200, plan.text
        assert client.get(f"{API}/graphs/pt/plan").status_code == 404
        unknown = client.get(f"{API}/graphs/pt/plan", params={"project": "nope"})
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "project.not_found"
        node = client.get(f"{API}/graphs/pt/nodes/a/effective-settings", params=p2)
        assert node.status_code == 200, node.text
        assert node.json()["value"]["model"] == "m-space"  # 에이전트도 그 공간에서 읽는다
        bundle = client.get(f"{API}/graphs/pt/nodes/a/bundle-preview", params=p2)
        assert bundle.status_code == 200, bundle.text
        agent = client.get(f"{API}/agents/a1/effective-settings", params=p2)
        assert agent.status_code == 200, agent.text
        usages = client.get(f"{API}/agents/a1/usages", params=p2)
        assert usages.status_code == 200, usages.text
        assert [(u["kind"], u["id"]) for u in usages.json()] == [("graph", "pt")]
        draft = {"graph": graph.model_dump(mode="json", exclude_none=True), "node_id": "a"}
        drafted = client.post(f"{API}/graphs/effective-settings", params=p2, json=draft)
        assert drafted.status_code == 200, drafted.text
        assert drafted.json()["value"]["model"] == "m-space"


# ---- 요청 11/08 후속: 공간 안 계산의 리소스 ---------------------------------------


def _resource_stores() -> tuple[InMemoryDefinitionStore, InMemoryDefinitionStore]:
    library = InMemoryDefinitionStore(DEFAULT_KINDS)
    library.create("resource", {"id": "r-lib", "type": "t", "name": "공용"})
    space = InMemoryDefinitionStore(DEFAULT_KINDS)
    stored = space.create("resource", {"id": "r1", "type": "t", "name": "공간"})
    space.write_content(
        "resource", "r1", b"body", file="r1.md", expected_version=stored.version_hash
    )
    return library, space


def test_in_space_reads_resources_of_the_space() -> None:
    """공간 안 계산(유효 설정·묶음 미리보기)의 리소스는 그 공간 저장소에서 읽는다(라이브러리
    ``resources.lookup``으로 넘어가지 않는다)."""
    library, space = _resource_stores()
    port = StoreResourceLookup(library)
    views = TeamViews(library, resources=lambda: port, spaces=lambda: MappedSpaces({"p2": space}))
    scoped = views.in_space("p2").resources
    found = scoped.get_resource("r1")
    assert found is not None
    assert found.name == "공간"
    assert scoped.read_content(found) == b"body"
    assert scoped.get_resource("r-lib") is None
    assert views.resources.get_resource("r-lib") is not None  # 공간 밖은 그대로 포트
    assert views.in_space(None).resources is port


def test_in_space_resources_off_or_without_provider() -> None:
    library, space = _resource_stores()
    off = TeamViews(library, spaces=lambda: MappedSpaces({"p2": space}))
    assert off.in_space("p2").resources.get_resource("r1") is None  # 리소스 기능 꺼짐 = 빈 조회
    port = StoreResourceLookup(library)
    alone = TeamViews(library, resources=lambda: port)
    assert alone.in_space("p2").resources is port  # 공간 제공자 없음 = 라이브러리


def test_store_resource_lookup_missing_is_none() -> None:
    library, _ = _resource_stores()
    lookup = StoreResourceLookup(library)
    found = lookup.get_resource("r-lib")
    assert found is not None
    assert lookup.read_content(found) is None  # 본문 없음
    ghost = found.model_copy(update={"id": "ghost"})
    assert lookup.read_content(ghost) is None
    assert lookup.read_files(ghost) is None
