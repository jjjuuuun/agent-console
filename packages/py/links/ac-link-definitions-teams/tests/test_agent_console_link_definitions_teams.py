"""link-definitions-teams: 사용처·유효 설정·실행 계획·묶음 미리보기, 목록 입구 이름·사용 수,
끄면 404·null, 포트 계약(제공 구현 ↔ 소비 프로토콜)(3R.12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    AgentSettings,
    BackendCapabilities,
    BackendDescriptor,
    BundlePreview,
    Issue,
    ResourceBundle,
    WorkspaceSettings,
)
from agent_console_link_definitions_teams import (
    DEFINITION_DEPENDENCIES,
    DEFINITION_USAGES,
    GRAPH_ENTRY_LABELS,
    SECRET_REDACT,
    WEB_ROLES,
    DefinitionLookup,
    DocumentDependencies,
    TeamDocumentDependencies,
    TeamViews,
    module,
    redact_values,
)
from agent_console_link_definitions_teams import views as views_module
from agent_console_link_definitions_teams.testing import local_definitions_module
from agent_console_mod_definitions import DEFINITIONS_STORE, GraphEntryLabels
from agent_console_mod_definitions import module as definitions
from agent_console_mod_resources import DefinitionUsages
from agent_console_mod_resources import module as resources
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_teams import TeamCatalog
from agent_console_teams.testing import Kit

TOKEN = "t" * 32
API = "/api/v1"
KIT = Kit()


@dataclass
class _Described:
    descriptor: Any


@dataclass
class _Registries:
    """플러그인 레지스트리 묶음 흉내(임의 이름 노드·엣지 타입, ac-teams 테스트 도구)."""

    node_types: Registry[Any] = field(default_factory=lambda: Registry("node_types"))
    edge_types: Registry[Any] = field(default_factory=lambda: Registry("edge_types"))
    delegation_strategies: Registry[Any] = field(default_factory=lambda: Registry("s"))
    backends: Registry[Any] = field(default_factory=lambda: Registry("backends"))

    def __post_init__(self) -> None:
        for d in KIT.node_types:
            self.node_types.register(d.id, _Described(d))
        for e in KIT.edge_types:
            self.edge_types.register(e.id, _Described(e))
        for s in KIT.strategies:
            self.delegation_strategies.register(s.id, _Described(s))


def _graph() -> dict[str, Any]:
    graph = KIT.graph(
        [KIT.person(), KIT.worker("a", "alice"), KIT.material("m", "doc")],
        [KIT.edge("e1", "entry", "me", "a")],
    )
    return graph.model_dump(mode="json", exclude_none=True)


def _assembly(tmp_path: Path, *extra: Any, link: bool = True) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_Registries(),
    )
    config = None if link else ModulesConfig(disabled=["link-definitions-teams"])
    return assemble([definitions, resources, module, *extra], config, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _seed(client: TestClient) -> dict[str, Any]:
    graph = _graph()
    assert client.post(f"{API}/agents", json={"id": "alice", "name": "앨리스"}).status_code == 201
    doc = {"id": "doc", "type": "unknown-x", "name": "문서", "config": {}}
    assert client.post(f"{API}/resources", json=doc).status_code == 201
    assert client.post(f"{API}/graphs", json=graph).status_code == 201
    return graph


def test_views_routes_and_list_extras(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        graph = _seed(client)
        usages = client.get(f"{API}/agents/alice/usages").json()
        assert [(u["kind"], u["id"], u["node_ids"]) for u in usages] == [("graph", "team", ["a"])]
        assert client.get(f"{API}/agents/ghost/usages").status_code == 404
        refs = client.get(f"{API}/resources/doc/usages").json()
        assert [(u["id"], u["node_ids"]) for u in refs] == [("team", ["m"])]
        assert client.get(f"{API}/resources").json()[0]["usage_count"] == 1
        assert client.get(f"{API}/graphs").json()[0]["entry_labels"] == ["A"]
        plan = client.get(f"{API}/graphs/team/plan")
        assert plan.status_code == 200
        assert client.post(f"{API}/graphs/plan", json={"graph": graph}).json() == plan.json()
        node = client.get(f"{API}/graphs/team/nodes/a/effective-settings")
        assert node.status_code == 200
        draft = client.post(
            f"{API}/graphs/effective-settings", json={"graph": graph, "node_id": "a"}
        )
        assert draft.json() == node.json()
        assert client.get(f"{API}/graphs/team/nodes/zz/effective-settings").status_code == 404
        bundle = client.get(f"{API}/graphs/team/nodes/a/bundle-preview")
        assert bundle.status_code == 200
        draft_bundle = client.post(
            f"{API}/graphs/bundle-preview", json={"graph": graph, "node_id": "a"}
        )
        assert draft_bundle.json() == bundle.json()
        assert client.get(f"{API}/agents/alice/effective-settings").status_code == 200


def test_link_off_hides_routes_and_extras(tmp_path: Path) -> None:
    """연동이 꺼지면(§3R.1.4 L9 "없으면") 경로는 404, 목록의 입구 이름·사용 수는 null."""
    with _client(_assembly(tmp_path, link=False)) as client:
        _seed(client)
        assert client.get(f"{API}/graphs/team/plan").status_code == 404
        assert client.get(f"{API}/agents/alice/usages").status_code == 404
        draft = {"graph": _graph(), "node_id": "a"}
        for path in ("plan", "effective-settings", "bundle-preview"):
            # 정의 모듈의 ``/graphs/{id}``와 겹쳐 405일 수 있다(웹은 404·405 모두 "없음"으로 본다).
            status = client.post(f"{API}/graphs/{path}", json=draft).status_code
            assert status in (404, 405), path
        assert client.get(f"{API}/graphs").json()[0]["entry_labels"] is None
        assert client.get(f"{API}/resources").json()[0]["usage_count"] is None
        assert client.get(f"{API}/agents/alice").status_code == 200  # 정의 CRUD는 그대로


def test_web_roles_cover_draft_preview_and_agent_usages(tmp_path: Path) -> None:
    """3R.32a: 웹 역할 ``definitions:teams``(초안 미리보기·에이전트 사용처 패널)를 선언한다.

    호스트 ``/modules``(modkit 보고 형식 ``state``)에 켜지면 active로, 끄면 disabled로 나온다.
    """
    assert WEB_ROLES == ("definitions:teams",)
    assert module.descriptor.web_roles == WEB_ROLES
    with _client(_assembly(tmp_path)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        info = infos["link-definitions-teams"]
        assert (info["state"], info["web_roles"]) == ("active", ["definitions:teams"])
    with _client(_assembly(tmp_path, link=False)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos["link-definitions-teams"]["state"] == "disabled"


def test_port_contracts(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    assert isinstance(assembly.port(DEFINITIONS_STORE), DefinitionLookup)
    labels = assembly.port(GRAPH_ENTRY_LABELS)
    usages = assembly.port(DEFINITION_USAGES)
    assert isinstance(labels, TeamViews)
    assert isinstance(labels, GraphEntryLabels)
    assert isinstance(usages, DefinitionUsages)


def test_standalone_lookup_and_redaction(tmp_path: Path) -> None:
    assembly = assemble(
        [local_definitions_module(workspace=tmp_path / "ws"), module], base=BaseServices()
    )
    assert {r.id: r.state.value for r in assembly.report}["link-definitions-teams"] == "active"
    views = assembly.port(GRAPH_ENTRY_LABELS)
    assert isinstance(views, TeamViews)
    assert views.workspace == WorkspaceSettings()  # 공통 설정 제공자가 없으면 기본값
    assert len(views.types) == 0  # 리소스 종류 제공자가 없으면 빈 레지스트리


def test_redact_values_keeps_json_valid() -> None:
    """묶음 미리보기 가리기는 값 단위다: 따옴표·역슬래시가 든 비밀도 JSON 구조를 깨지 않는다."""
    secret = 'a"b\\c'

    def redact(text: str) -> str:
        return text.replace(secret, "[REDACTED]")

    value = {"slots": {"instructions": [f"key={secret}"], "n": 1}, secret: [secret, 2]}
    assert redact_values(value, redact) == {
        "slots": {"instructions": ["key=[REDACTED]"], "n": 1},
        "[REDACTED]": ["[REDACTED]", 2],
    }


MARKER = "TOPSECRET-VALUE-77"


def _redactor() -> Any:
    """가짜 ``secrets.redact`` 제공 모듈(통합 서버에서는 mod-runs가 해석한 비밀 값을 가린다)."""

    def build(ctx: Any) -> None:
        ctx.provide(SECRET_REDACT, lambda text: text.replace(MARKER, "[REDACTED]"))

    return fake_module("fake-redact", provides=[SECRET_REDACT], on_build=build)


def test_bundle_preview_uses_injected_secret_redact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``secrets.redact``를 주면 묶음 미리보기(저장본·초안)의 문자열을 그것으로 가린다.

    묶음 계산(``ac-teams.bundle_preview``)은 비밀이 든 묶음을 돌려주게 바꿔 둔다(가림만 본다).
    """

    def fake_preview(*_args: Any, **_kwargs: Any) -> BundlePreview:
        bundle = ResourceBundle(slots={"instructions": [f"key={MARKER}"], MARKER: 1})
        return BundlePreview(bundle=bundle)

    monkeypatch.setattr(views_module, "bundle_preview", fake_preview)

    def preview(assembly: Assembly) -> list[str]:
        with _client(assembly) as client:
            graph = _seed(client)
            saved = client.get(f"{API}/graphs/team/nodes/a/bundle-preview")
            draft = client.post(
                f"{API}/graphs/bundle-preview", json={"graph": graph, "node_id": "a"}
            )
            assert saved.status_code == draft.status_code == 200
            return [saved.text, draft.text]

    plain = preview(_assembly(tmp_path / "plain"))
    assert all(MARKER in text for text in plain)  # 가림 제공자가 없으면 그대로(헛돌지 않음)
    for text in preview(_assembly(tmp_path / "redacted", _redactor())):
        assert MARKER not in text
        assert '"key=[REDACTED]"' in text
        assert '"[REDACTED]":1' in text  # 키도 값 단위로 가린다


class _Noted:
    """``preview_notes`` 훅을 가진 백엔드 흉내(관측 설정 hook_probe가 켜지면 안내 하나)."""

    descriptor = BackendDescriptor(id="b1", title="b", capabilities=BackendCapabilities())

    def preview_notes(self, effective: AgentSettings, bundle: ResourceBundle) -> list[Issue]:
        on = effective.observe is not None and effective.observe.hook_probe is True
        return [Issue(severity="info", code="x.hook_probe", message="켜짐")] if on else []


def test_bundle_preview_includes_backend_preview_notes(tmp_path: Path) -> None:
    """4R.9: 백엔드 선택 훅 ``preview_notes``(예: claude-sdk "hook 감싸기 켜짐")가 붙는다."""
    registries = _Registries()
    registries.backends.register("b1", _Noted())
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )
    with _client(assemble([definitions, resources, module], None, base=base)) as client:
        _seed(client)
        quiet = client.get(f"{API}/graphs/team/nodes/a/bundle-preview").json()
        assert all(w["code"] != "x.hook_probe" for w in quiet["warnings"])
        agent = {"id": "alice", "name": "앨리스", "backend": "b1", "observe": {"hook_probe": True}}
        assert client.put(f"{API}/agents/alice", json=agent).status_code == 200
        noted = client.get(f"{API}/graphs/team/nodes/a/bundle-preview").json()
        assert [w["code"] for w in noted["warnings"]] == ["x.hook_probe"]


def test_document_dependencies_port(tmp_path: Path) -> None:
    """``definitions.dependencies``: 저장 전 문서에서 쓰는 정의(자식 팀 구성 포함, 5R.15)."""
    assembly = _assembly(tmp_path)
    deps = assembly.port(DEFINITION_DEPENDENCIES)
    assert isinstance(deps, DocumentDependencies)
    graph = KIT.graph(
        [KIT.person(), KIT.worker("a", "alice"), KIT.nest("t", "crew")],
        [KIT.edge("e1", "entry", "me", "a")],
    ).model_dump(mode="json", exclude_none=True)
    found = [(d.kind, d.id, d.node_id) for d in deps.dependencies_of("graph", graph)]
    assert found == [("agent", "alice", "a"), ("graph", "crew", "t")]
    agent = {"id": "alice", "name": "앨리스", "resources": [{"ref": "doc"}]}
    assert [(d.kind, d.id) for d in deps.dependencies_of("agent", agent)] == [("resource", "doc")]
    assert deps.dependencies_of("resource", {"id": "doc"}) == []
    standalone = TeamDocumentDependencies(
        lambda: TeamCatalog(tuple(KIT.node_types), tuple(KIT.edge_types))
    )
    assert [d.id for d in standalone.dependencies_of("graph", graph)] == ["alice", "crew"]


def test_definition_references_port(tmp_path: Path) -> None:
    """``definitions.references``(X25, 여러 제공자): 참조 추출 함수 ``(kind, doc) -> [(kind, id)]``.

    ``definitions.dependencies``와 같은 계산이고, 모르는 종류·잘못된 문서는 빈 목록이다(5.2R.31).
    """
    from agent_console_link_definitions_teams import DEFINITION_REFERENCES

    assert DEFINITION_REFERENCES.name == "definitions.references"
    assert DEFINITION_REFERENCES.multi
    assert DEFINITION_REFERENCES in module.descriptor.provides
    [refs] = _assembly(tmp_path).ports(DEFINITION_REFERENCES)
    graph = KIT.graph(
        [KIT.person(), KIT.worker("a", "alice"), KIT.worker("b", "alice"), KIT.nest("t", "crew")],
        [KIT.edge("e1", "entry", "me", "a")],
    ).model_dump(mode="json", exclude_none=True)
    assert list(refs("graph", graph)) == [("agent", "alice"), ("graph", "crew")]  # 중복 없음
    agent = {"id": "alice", "name": "앨리스", "resources": [{"ref": "doc"}]}
    assert list(refs("agent", agent)) == [("resource", "doc")]
    assert list(refs("resource", {"id": "doc"})) == []
    assert list(refs("graph", {"id": "broken", "nodes": "x"})) == []
    assert _assembly(tmp_path / "off", link=False).ports(DEFINITION_REFERENCES) == []
