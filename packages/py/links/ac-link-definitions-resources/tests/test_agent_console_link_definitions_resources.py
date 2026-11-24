"""link-definitions-resources: 저장 전 리소스 검사(definitions.checks), 끄면 검사 없이 저장,
평문 점검 기여, 포트 계약(제공 구현 ↔ 소비 프로토콜)(3R.12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_definitions_resources import (
    DEFINITIONS_SPACES,
    DefinitionChecker,
    DefinitionLookup,
    LookupResources,
    SpaceDefinitionCheck,
    module,
)
from agent_console_link_definitions_resources.testing import local_sources_module
from agent_console_mod_definitions import DEFINITION_CHECKS, DEFINITIONS_LOOKUP, SERVER_WARNINGS
from agent_console_mod_definitions import DefinitionCheck as DefinitionsCheckProtocol
from agent_console_mod_definitions import SpaceDefinitionCheck as DefinitionsSpaceCheckProtocol
from agent_console_mod_definitions import module as definitions
from agent_console_mod_resources import RESOURCE_TYPES, RESOURCES_LOOKUP
from agent_console_mod_resources import module as resources
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_resources import InMemoryResources, ResourceLookup, new_resource_types
from agent_console_store import (
    DEFAULT_KINDS,
    InMemoryDefinitionStore,
    MappedSpaces,
    SpacesUnavailable,
    UnknownSpace,
)

TOKEN = "t" * 32
API = "/api/v1"
PLAIN = "sk-live-123456"
MCP = {
    "id": "gh",
    "type": "mcp-server",
    "name": "gh",
    "config": {"name": "gh", "command": "npx", "env": {"API_KEY": "secret://T"}},
}
AGENT = {
    "id": "a",
    "name": "a",
    "backend": "fake-agent",
    "resources": [{"ref": "gh", "config_override": {"env": {"API_KEY": PLAIN}}}],
}


def _assembly(tmp_path: Path, *, link: bool = True) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    config = None if link else ModulesConfig(disabled=["link-definitions-resources"])
    return assemble([definitions, resources, module], config, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_plain_secret_override_is_rejected_and_reported(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        assert client.post(f"{API}/resources", json=MCP).status_code == 201
        rejected = client.post(f"{API}/agents", json=AGENT)
        assert rejected.status_code == 422
        assert PLAIN not in rejected.text
        paths = [i["path"] for i in rejected.json()["error"]["details"]["issues"]]
        assert paths == ["/resources/0/config_override/env/API_KEY"]
    # 이미 저장된 평문(손으로 고친 파일 등)은 평문 점검이 위치를 알린다(검사의 평문 이슈 코드)
    store = assembly.port(DEFINITIONS_LOOKUP)
    assert store is not None
    store.create("agent", AGENT)
    [warnings] = assembly.ports(SERVER_WARNINGS)
    found = [(w.details["kind"], w.path) for w in warnings() if w.code == "secret.plain_found"]
    assert ("agent", "/resources/0/config_override/env/API_KEY") in found


def test_link_off_saves_without_resource_checks(tmp_path: Path) -> None:
    """연동이 꺼지면(§3R.1.4 L8 "없으면") 정의는 리소스 검사 없이 저장된다."""
    assembly = _assembly(tmp_path, link=False)
    states = {r.id: r.state.value for r in assembly.report}
    assert states == {
        "link-definitions-resources": "disabled",
        "mod-definitions": "active",
        "mod-resources": "active",
    }
    with _client(assembly) as client:
        client.post(f"{API}/resources", json=MCP)
        assert client.post(f"{API}/agents", json=AGENT).status_code == 201


def test_requires_definitions_and_resource_types(tmp_path: Path) -> None:
    alone = assemble([definitions, module], base=BaseServices())
    report = {r.id: r for r in alone.report}["link-definitions-resources"]
    assert report.missing == ("resources.types",)


def test_port_contracts(tmp_path: Path) -> None:
    """제공 구현 ↔ 소비 프로토콜: 정의·리소스 모듈이 주는 것을 이 연동이 받고, 이 연동이 주는
    검사를 정의 모듈이 받는다."""
    assembly = _assembly(tmp_path)
    assert isinstance(assembly.port(DEFINITIONS_LOOKUP), DefinitionLookup)
    assert isinstance(assembly.port(RESOURCE_TYPES), Registry)
    assert isinstance(assembly.port(RESOURCES_LOOKUP), ResourceLookup)
    checks = assembly.ports(DEFINITION_CHECKS)
    linked = [c for c in checks if isinstance(c, DefinitionChecker)]
    assert len(linked) == 1
    assert isinstance(linked[0], DefinitionsCheckProtocol)


def test_fallback_lookup_and_standalone_sources(tmp_path: Path) -> None:
    assembly = assemble(
        [local_sources_module(workspace=tmp_path / "ws"), module],
        base=BaseServices(),
    )
    assert {r.id: r.state.value for r in assembly.report}["link-definitions-resources"] == "active"
    [checker] = assembly.ports(DEFINITION_CHECKS)
    lookup = assembly.port(DEFINITIONS_LOOKUP)
    assert lookup is not None
    lookup.create("resource", MCP)
    fallback = LookupResources(lookup)
    found: Any = fallback.get_resource("gh")
    assert found is not None
    assert found.id == "gh"
    assert fallback.get_resource("ghost") is None
    issues = checker.issues("agent", AGENT)
    assert [i.path for i in issues if i.severity == "error"] == [
        "/resources/0/config_override/env/API_KEY"
    ]
    assert checker.issues("unknown-kind", {}) == []
    assert checker.issues("agent", {"id": "!"}) == []  # 모델 검증은 저장소 몫


# ---------------------------------------------------------------- 공간 기준 검사(FU.3)

BAD_OVERRIDE = {
    "id": "b",
    "name": "b",
    "resources": [{"ref": "gh", "config_override": {"command": 5}}],
}
"""리소스 종류 스키마에 맞지 않는 덮어쓰기(리소스를 찾았을 때만 error)."""


def _errors(issues: Any) -> list[str | None]:
    return [i.path for i in issues if i.severity == "error"]


def _spaced(tmp_path: Path, spaces: dict[str, Any] | None) -> Assembly:
    """라이브러리(파일 저장소) + 공간 제공자(``spaces``가 None이면 없음) + 이 연동."""
    mods: list[Any] = [local_sources_module(workspace=tmp_path / "ws"), module]
    if spaces is not None:

        def build(ctx: Any) -> None:
            ctx.provide(DEFINITIONS_SPACES, MappedSpaces(spaces))

        mods.append(fake_module("spaces", provides=[DEFINITIONS_SPACES], on_build=build))
    assembly = assemble(mods, base=BaseServices())
    lookup = assembly.port(DEFINITIONS_LOOKUP)
    assert lookup is not None
    lookup.create("resource", MCP)  # 라이브러리에만 있다
    return assembly


def test_space_issues_resolve_refs_only_in_that_space(tmp_path: Path) -> None:
    empty = InMemoryDefinitionStore(DEFAULT_KINDS)
    holder = InMemoryDefinitionStore(DEFAULT_KINDS)
    holder.create("resource", {**MCP, "config": {"name": "gh", "command": "npx"}})
    assembly = _spaced(tmp_path, {"p-empty": empty, "p-holder": holder})
    [checker] = assembly.ports(DEFINITION_CHECKS)
    assert isinstance(checker, SpaceDefinitionCheck)
    assert isinstance(checker, DefinitionsSpaceCheckProtocol)
    # 라이브러리 기준: 라이브러리 리소스로 풀어 잘못된 덮어쓰기를 막는다(지금 동작).
    command = "/resources/0/config_override/command"
    assert _errors(checker.issues("agent", BAD_OVERRIDE)) == [command]
    # 공간에 리소스가 없으면 라이브러리로 넘어가 찾지 않는다(찾을 수 없음 = 덮어쓰기 검사 생략).
    in_empty = checker.space_issues("p-empty", "agent", BAD_OVERRIDE)
    assert _errors(in_empty) == []
    assert [i.path for i in in_empty] == ["/resources/0/ref"]
    # 공간에만 있는 리소스는 그 공간 검사가 본다.
    in_holder = checker.space_issues("p-holder", "agent", BAD_OVERRIDE)
    assert _errors(in_holder) == [command]
    # 리소스 정의 자체의 종류 검사는 공간을 열지 않는다.
    assert checker.space_issues("p-empty", "resource", MCP) == checker.issues("resource", MCP)


def test_space_issues_unknown_space_and_no_provider(tmp_path: Path) -> None:
    [checker] = _spaced(tmp_path / "a", {}).ports(DEFINITION_CHECKS)
    assert isinstance(checker, DefinitionChecker)
    with pytest.raises(UnknownSpace):
        checker.space_issues("ghost", "agent", BAD_OVERRIDE)
    [alone] = _spaced(tmp_path / "b", None).ports(DEFINITION_CHECKS)
    assert isinstance(alone, DefinitionChecker)
    with pytest.raises(SpacesUnavailable):
        alone.space_issues("p1", "agent", BAD_OVERRIDE)
    # 함수로 쓰는 검사도 공간 조회가 없으면 같은 오류(라이브러리로 넘어가지 않는다).
    bare = DefinitionChecker(
        types=new_resource_types, resources=InMemoryResources, plan_of=lambda graph: None
    )
    with pytest.raises(SpacesUnavailable):
        bare.space_issues("p1", "agent", BAD_OVERRIDE)


def test_space_saves_through_definitions_module(tmp_path: Path) -> None:
    """정의 모듈의 공간 저장(``?project=``)이 공간 기준 검사를 부른다."""
    space = InMemoryDefinitionStore(DEFAULT_KINDS)

    def build(ctx: Any) -> None:
        ctx.provide(DEFINITIONS_SPACES, MappedSpaces({"p1": space}))

    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    spaces = fake_module("spaces", provides=[DEFINITIONS_SPACES], on_build=build)
    with _client(assemble([definitions, resources, module, spaces], base=base)) as client:
        assert client.post(f"{API}/resources", json=MCP).status_code == 201  # 라이브러리
        assert client.post(f"{API}/agents", json=BAD_OVERRIDE).status_code == 422
        assert client.post(f"{API}/agents?project=p1", json=BAD_OVERRIDE).status_code == 201
        assert client.post(f"{API}/resources?project=p1", json=MCP).status_code == 201
        again = {**BAD_OVERRIDE, "id": "c", "name": "c"}
        assert client.post(f"{API}/agents?project=p1", json=again).status_code == 422
