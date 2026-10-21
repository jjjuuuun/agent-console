"""link-exports-teams: 내보내기 의존 자동 포함, 끄면 고른 항목만, 포트 계약(3R.12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_exports_teams import (
    EXPORT_DEPENDENCIES,
    DefinitionLookup,
    TeamExportDependencies,
    module,
)
from agent_console_link_exports_teams.testing import local_definitions_module
from agent_console_mod_definitions import DEFINITIONS_STORE
from agent_console_mod_definitions import module as definitions
from agent_console_mod_exports import ExportDependencies
from agent_console_mod_exports import module as exports
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_registry import Registry
from agent_console_teams.testing import Kit

TOKEN = "t" * 32
API = "/api/v1"
KIT = Kit()
AGENT = {"id": "alice", "name": "앨리스", "resources": [{"ref": "doc"}]}
DOC = {"id": "doc", "type": "rule", "name": "규칙", "config": {"paths": ["src/**"], "text": "먼저"}}


@dataclass
class _Described:
    descriptor: Any


@dataclass
class _Registries:
    node_types: Registry[Any] = field(default_factory=lambda: Registry("node_types"))
    edge_types: Registry[Any] = field(default_factory=lambda: Registry("edge_types"))

    def __post_init__(self) -> None:
        for d in KIT.node_types:
            self.node_types.register(d.id, _Described(d))
        for e in KIT.edge_types:
            self.edge_types.register(e.id, _Described(e))


def _assembly(tmp_path: Path, *, link: bool = True) -> Assembly:
    base = BaseServices(
        environ={"HOME": str(tmp_path / "home")},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_Registries(),
    )
    config = None if link else ModulesConfig(disabled=["link-exports-teams"])
    assembly = assemble([definitions, exports, module], config, base=base)
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    store.create("resource", DOC)
    store.create("agent", AGENT)
    graph = KIT.graph(
        [KIT.person(), KIT.worker("a", "alice")], [KIT.edge("e1", "entry", "me", "a")]
    )
    store.create("graph", graph.model_dump(mode="json", exclude_none=True))
    return assembly


def _planned(assembly: Assembly, kind: str, item_id: str) -> set[str]:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        body = {"exporter": "claude-dir", "items": [{"kind": kind, "id": item_id}]}
        res = client.post(f"{API}/exports/plan", json=body)
        assert res.status_code == 200, res.text
        return {f["path"] for f in res.json()["files"]}


def test_dependencies_are_included(tmp_path: Path) -> None:
    alone = _planned(_assembly(tmp_path / "off", link=False), "agent", "alice")
    linked = _planned(_assembly(tmp_path / "on"), "agent", "alice")
    assert alone < linked  # 에이전트가 쓰는 리소스가 함께 나간다


def test_link_off_exports_only_selected(tmp_path: Path) -> None:
    """연동이 꺼지면(§3R.1.4 L10 "없으면") 의존 자동 포함 없이 고른 항목만 내보낸다."""
    assembly = _assembly(tmp_path, link=False)
    assert assembly.port(EXPORT_DEPENDENCIES) is None
    assert _planned(assembly, "agent", "alice")  # 고른 에이전트는 그대로 나간다


def test_port_contracts_and_direct_use(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    store = assembly.port(DEFINITIONS_STORE)
    assert isinstance(store, DefinitionLookup)
    deps = assembly.port(EXPORT_DEPENDENCIES)
    assert isinstance(deps, TeamExportDependencies)
    assert isinstance(deps, ExportDependencies)
    assert [(d.kind, d.id) for d in deps.dependencies("agent", "alice")] == [("resource", "doc")]
    assert deps.dependencies("resource", "doc") == []


def test_standalone_provider(tmp_path: Path) -> None:
    assembly = assemble([local_definitions_module(workspace=tmp_path), module], base=BaseServices())
    assert {r.id: r.state.value for r in assembly.report}["link-exports-teams"] == "active"
