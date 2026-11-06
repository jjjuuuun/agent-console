"""link-wiki-runs 단위: 층 합치기·리소스 종류·공급자(도구·지침·경고·쓴 주체·알림)·검사·범위·R0."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    BackendCapabilities,
    KnownIssueCodes,
    Resource,
    ResourceAttachment,
    ResourceBundle,
)
from agent_console_contracts.wiki import (
    WIKI_ACCESS_OPS,
    WikiAccessConfig,
    WikiRulesDefinition,
    wiki_access_defaults,
)
from agent_console_link_wiki_runs import (
    DEFAULT_MAX_WRITES_PER_RUN,
    INTEGRATION_RUNS,
    MODULE_ID,
    WEB_ROLES,
    WikiResourceCheck,
    WikiResourceType,
    WikiRunsCodes,
    WikiRunScope,
    WikiRunsSettings,
    WikiToolProvider,
    agent_label,
    known_wiki_ids,
    load_wiki_resource_type,
    merge_access,
    module,
    open_targets,
    wiki_slot,
)
from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
from agent_console_nodes_core import AGENT_LOOKUP, TOOL_PROVIDERS, ToolProvisionContext
from agent_console_resources import ContributeContext
from agent_console_runtime import CancelToken, HostTool, HostToolResult, Services
from agent_console_wiki import RulesDocument, WikiToolTarget, merge_rules

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_link_wiki_runs"
RTYPE = load_wiki_resource_type()
SLOT = wiki_slot(RTYPE)
TOOLS = {op: t["name"] for op, t in wiki_access_defaults()["tools"].items()}


def _rules(instructions: str = "결정만 적으세요.") -> Any:
    rules = WikiRulesDefinition.model_validate(
        {
            "kind": "wiki-rules",
            "id": "house",
            "name": "집 규칙",
            "instructions": {"file": "guide.md"},
            "write_rules": [
                {"id": "no-temp", "deny_patterns": [r"\bTEMPNOTE\b"], "message": "임시 메모 금지"}
            ],
        }
    )
    return merge_rules(["house"], [RulesDocument("house", rules, {"guide.md": instructions})])


def _item(**config: Any) -> dict[str, Any]:
    return {"resource": "r", "layer": "agent", "config": config}


Emitted = list[tuple[str, dict[str, Any]]]


def _ctx(items: list[dict[str, Any]] | None, emitted: Emitted | None = None) -> Any:
    async def emit(event_type: str, payload: Any) -> None:
        if emitted is not None:
            emitted.append((event_type, dict(payload)))

    slots = {SLOT: items} if items is not None else {}
    return ToolProvisionContext(
        run_id="r2",
        root_run_id="r1",
        graph_id="child",
        node_id="keeper",
        node_path=["T", "keeper"],
        agent_id="keeper-agent",
        call=0,
        iteration=0,
        bundle=ResourceBundle(slots=slots),
        backend_capabilities=BackendCapabilities(host_tools=True),
        emit=emit,
        cancel=CancelToken(),
    )


def _call(tool: HostTool, args: dict[str, Any]) -> HostToolResult:
    async def go() -> HostToolResult:
        return await tool.handler(args)

    return asyncio.run(go())


def _agent(agent_id: str, name: str) -> Agent:
    return Agent.model_validate({"id": agent_id, "name": name})


# ---------------------------------------------------------------- 층 합치기


def test_merge_access_nearest_layer_per_wiki_and_key() -> None:
    far = _item(
        wikis=[{"wiki": "notes", "access": ["read"]}, {"wiki": "specs"}],
        path_hint="먼 층",
        tools={"read": {"name": "far_read", "description": "d"}},
    )
    near = _item(
        wikis=[{"wiki": "notes", "access": ["read", "write"]}],
        default_wiki="notes",
        tools={"write": {"name": "near_write", "description": "w"}},
    )
    access, issues = merge_access([far, near])
    assert issues == []
    assert access is not None
    assert [(w.wiki, w.access) for w in access.wikis] == [
        ("notes", ["read", "write"]),
        ("specs", WikiAccessConfig.model_validate({"wikis": [{"wiki": "x"}]}).wikis[0].access),
    ]
    assert (access.default_wiki, access.path_hint) == ("notes", "먼 층")
    assert (access.tools.read.name, access.tools.write.name) == ("far_read", "near_write")


def test_merge_access_same_wiki_twice_in_one_layer_joins_ops() -> None:
    access, _ = merge_access(
        [_item(wikis=[{"wiki": "n", "access": ["read"]}, {"wiki": "n", "access": ["write"]}])]
    )
    assert access is not None
    assert [(w.wiki, w.access) for w in access.wikis] == [("n", ["read", "write"])]


def test_merge_access_empty_and_invalid() -> None:
    assert merge_access([]) == (None, [])
    assert merge_access("nope") == (None, [])
    access, issues = merge_access([_item(wikis=[{"wiki": "n"}], max_result_chars=0)])
    assert access is None
    [issue] = issues
    assert issue.code == WikiRunsCodes.ACCESS_INVALID
    assert issue.details["paths"] == ["/max_result_chars"]


# ---------------------------------------------------------------- 리소스 종류


def test_resource_type_from_data_and_contract_schema() -> None:
    assert RTYPE.contributes == [SLOT]
    assert RTYPE.config_schema == WikiAccessConfig.model_json_schema()
    other = load_wiki_resource_type({"id": "wiki-x", "contributes": ["wx"], "title": "x"})
    assert (other.id, wiki_slot(other)) == ("wiki-x", "wx")
    with pytest.raises(ValueError, match="contributes"):
        load_wiki_resource_type({"id": "y", "contributes": [], "title": "y"})


def test_resource_type_validates_and_contributes_layer() -> None:
    rtype = WikiResourceType()
    bad = Resource(id="b", type=RTYPE.id, name="b", config={"wikis": [{"wiki": "../x"}]})
    assert rtype.validate(bad)
    good = Resource(id="g", type=RTYPE.id, name="g", config={"wikis": [{"wiki": "n"}]})
    [contribution] = rtype.contribute(
        good, None, ContributeContext(ResourceAttachment(ref="g"), layer="team")
    )
    assert contribution.slot == SLOT
    assert contribution.value == [{"resource": "g", "layer": "team", "config": good.config}]


# ---------------------------------------------------------------- 공급자


def _service(**wikis: Any) -> StaticWikiService:
    return StaticWikiService({None: wikis, "proj-a": {}})


def test_provider_without_slot_or_service_gives_nothing() -> None:
    provider = WikiToolProvider(lambda: _service(), slot=SLOT)
    assert provider.provide(_ctx(None)).host_tools == ()
    off = WikiToolProvider(lambda: None, slot=SLOT)
    found = off.provide(_ctx([_item(wikis=[{"wiki": "n"}])]))
    assert (found.host_tools, found.consumed_slots, found.instructions) == ((), frozenset(), ())


def test_provider_gives_allowed_tools_rules_instructions_and_path_hint() -> None:
    repo = memory_repository("notes", rules=_rules())
    service = _service(notes=WikiToolTarget(repo, name="노트", pages_dir="wiki-pages/notes"))
    provider = WikiToolProvider(lambda: service, slot=SLOT)
    found = provider.provide(
        _ctx(
            [_item(wikis=[{"wiki": "notes", "access": ["read", "write"]}], path_hint="{pages_dir}")]
        )
    )
    assert [t.name for t in found.host_tools] == [TOOLS["read"], TOOLS["write"]]
    assert found.consumed_slots == frozenset({SLOT})
    assert list(found.instructions) == [_rules().instructions, "wiki-pages/notes"]
    assert "결정만 적으세요." in found.instructions[0]
    assert found.warnings == ()


def test_provider_include_rules_off_and_empty_hint_gives_no_instructions() -> None:
    service = _service(notes=memory_repository("notes", rules=_rules()))
    provider = WikiToolProvider(lambda: service, slot=SLOT)
    found = provider.provide(
        _ctx([_item(wikis=[{"wiki": "notes"}], include_rules_instructions=False, path_hint="")])
    )
    assert found.instructions == ()
    assert found.host_tools


def test_provider_invalid_access_consumes_slot_and_warns() -> None:
    provider = WikiToolProvider(lambda: _service(), slot=SLOT)
    found = provider.provide(_ctx([_item(wikis=[{"wiki": "n"}], max_result_chars=0)]))
    assert found.host_tools == ()
    assert found.consumed_slots == frozenset({SLOT})
    assert [w.code for w in found.warnings] == [WikiRunsCodes.ACCESS_INVALID]


def test_provider_unknown_wiki_in_space_warns_once_and_tools_fail() -> None:
    service = _service(notes=memory_repository("notes"))
    provider = WikiToolProvider(lambda: service, slot=SLOT, project_id="proj-a")
    emitted: Emitted = []
    found = provider.provide(_ctx([_item(wikis=[{"wiki": "notes"}])], emitted))
    [warning] = found.warnings
    assert warning.code == KnownIssueCodes.WIKI_WIKI_UNAVAILABLE
    assert warning.details == {"wikis": ["notes"], "project_id": "proj-a"}
    read = next(t for t in found.host_tools if t.name == TOOLS["read"])
    result = _call(read, {"path": "x"})
    assert result.is_error
    assert result.text.startswith(f"[{KnownIssueCodes.WIKI_WIKI_UNAVAILABLE}]")
    assert [(t, p["status"]) for t, p in emitted] == [("wiki.read", "wiki_unavailable")]


def test_provider_space_open_failure_reason_in_warning() -> None:
    service = _service(notes=memory_repository("notes"))
    provider = WikiToolProvider(lambda: service, slot=SLOT, project_id="ghost")
    [warning] = provider.provide(_ctx([_item(wikis=[{"wiki": "notes"}])])).warnings
    assert warning.details["reason"] == "LookupError"
    assert open_targets(service, "ghost") == ({}, "LookupError")


def test_author_label_from_agent_definition_and_notify_on_writes() -> None:
    repo = memory_repository("notes")
    service = _service(notes=repo)
    lookup = {"keeper-agent": _agent("keeper-agent", "위키 관리자")}.get
    provider = WikiToolProvider(lambda: service, slot=SLOT, agent_lookup=lookup)
    emitted: Emitted = []
    found = provider.provide(
        _ctx(
            [_item(wikis=[{"wiki": "notes", "access": ["read", "write", "move", "delete"]}])],
            emitted,
        )
    )
    tools = {t.name: t for t in found.host_tools}
    write, move, delete = (tools[TOOLS[op]] for op in ("write", "move", "delete"))
    assert not _call(write, {"path": "a", "content": "# A\n"}).is_error
    assert not _call(move, {"path": "a", "to": "b"}).is_error
    assert not _call(delete, {"path": "b"}).is_error
    assert _call(write, {"path": "", "content": "x"}).is_error  # 실패는 알리지 않음
    assert [(n.wiki_id, n.paths, n.deleted) for n in service.notices] == [
        ("notes", ("a",), False),
        ("notes", ("a", "b"), False),
        ("notes", ("b",), True),
    ]
    assert repo.history is not None
    [first] = repo.history.list("notes", "a", limit=1).items
    author = first.author
    assert (author.kind, author.agent_id, author.label) == ("agent", "keeper-agent", "위키 관리자")
    assert (author.run_id, author.root_run_id, author.graph_id) == ("r2", "r1", "child")
    assert (author.node_id, author.node_path) == ("keeper", ["T", "keeper"])
    assert [t for t, _ in emitted][:3] == ["wiki.write", "wiki.move", "wiki.delete"]


def test_notify_failure_does_not_break_tool() -> None:
    class Broken(StaticWikiService):
        def notify(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("ws down")

    service = Broken({None: {"notes": memory_repository("notes")}})
    provider = WikiToolProvider(lambda: service, slot=SLOT)
    found = provider.provide(_ctx([_item(wikis=[{"wiki": "notes", "access": ["write"]}])]))
    [write] = found.host_tools
    assert not _call(write, {"path": "a", "content": "x"}).is_error


def test_agent_label_missing_or_failing() -> None:
    def boom(_id: str) -> Agent | None:
        raise RuntimeError

    assert agent_label(None, "a") is None
    nobody: dict[str, Agent] = {}
    assert agent_label(nobody.get, "a") is None
    assert agent_label(boom, "a") is None
    assert agent_label({"a": _agent("a", "이름")}.get, None) is None


# ---------------------------------------------------------------- 범위


def test_scope_run_appends_provider_with_new_budget_and_lookup() -> None:
    service = _service()
    scope = WikiRunScope(lambda: service, slot=SLOT, max_writes_per_run=3)
    lookup = {"a": _agent("a", "에이")}.get
    existing = object()
    services = Services({AGENT_LOOKUP: lookup, TOOL_PROVIDERS: (existing,)})
    graph: Any = None
    first = scope.scope_run(graph, services, project_id="p1")
    second = scope.scope_run(graph, services, project_id=None)
    assert first is not None
    assert second is not None
    head, provider = first.services[TOOL_PROVIDERS]
    assert head is existing
    assert isinstance(provider, WikiToolProvider)
    assert (provider.project_id, provider.agent_lookup) == ("p1", lookup)
    other = second.services[TOOL_PROVIDERS][1]
    assert provider.write_budget is not other.write_budget
    assert WikiRunScope(lambda: None, slot=SLOT).scope_run(graph, services, project_id=None) is None


# ---------------------------------------------------------------- 저장 전 검사


class _Project:
    def __init__(self, project_id: str) -> None:
        self.id = project_id


class _Projects:
    def __init__(self, *ids: str) -> None:
        self.ids = ids

    def list_projects(self) -> list[_Project]:
        return [_Project(i) for i in self.ids]


def _doc(**config: Any) -> dict[str, Any]:
    return {"id": "x", "type": RTYPE.id, "name": "x", "config": config}


def test_check_warns_unknown_wiki_ids_across_spaces() -> None:
    service = StaticWikiService(
        {None: {"root": memory_repository("root")}, "p1": {"pw": memory_repository("pw")}}
    )
    check = WikiResourceCheck(
        lambda: service, resource_type=RTYPE.id, projects=lambda: _Projects("p1", "missing")
    )
    doc = _doc(wikis=[{"wiki": "root"}, {"wiki": "pw"}, {"wiki": "ghost"}], default_wiki="nope")
    issues = check.issues("resource", doc)
    assert [(i.code, i.path, i.details) for i in issues] == [
        (KnownIssueCodes.WIKI_UNKNOWN_WIKI, "/config/wikis/2/wiki", {"wiki": "ghost"}),
        (KnownIssueCodes.WIKI_UNKNOWN_WIKI, "/config/default_wiki", {"wiki": "nope"}),
    ]
    assert all(i.severity == "warning" for i in issues)
    # 프로젝트 목록이 없으면 단독 공간만 안다
    alone = WikiResourceCheck(lambda: service, resource_type=RTYPE.id)
    assert [i.details["wiki"] for i in alone.issues("resource", doc)] == ["pw", "ghost", "nope"]
    assert known_wiki_ids(service, _Projects("p1")) == {"root", "pw"}


def test_check_ignores_other_kinds_types_and_missing_service() -> None:
    service = _service()
    check = WikiResourceCheck(lambda: service, resource_type=RTYPE.id)
    assert check.issues("agent", _doc(wikis=[{"wiki": "g"}])) == []
    assert check.issues("resource", {**_doc(wikis=[{"wiki": "g"}]), "type": "memory"}) == []
    assert check.issues("resource", {"type": RTYPE.id, "config": "x"}) == []
    off = WikiResourceCheck(lambda: None, resource_type=RTYPE.id)
    assert off.issues("resource", _doc(wikis=[{"wiki": "g"}])) == []


# ---------------------------------------------------------------- 모듈·R0


def test_module_descriptor_and_settings() -> None:
    d = module.descriptor
    assert (d.id, d.kind, d.web_roles) == (MODULE_ID, "link", WEB_ROLES)
    assert [p.name for p in d.requires] == ["wiki.service"]
    assert {p.name for p in d.provides} == {
        "runs.scopes",
        "runs.services",
        "definitions.checks",
        "wiki.integrations",
    }
    assert WikiRunsSettings().max_writes_per_run == DEFAULT_MAX_WRITES_PER_RUN
    assert WikiRunsSettings(max_writes_per_run=None).max_writes_per_run is None


def test_integration_name_matches_wiki_module() -> None:
    from agent_console_mod_wiki import ports as wiki_ports

    assert wiki_ports.INTEGRATION_RUNS == INTEGRATION_RUNS


def _string_constants(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    docs: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            for stmt in body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                    docs.add(id(stmt.value))
    return {
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    }


def test_no_default_tool_names_in_source() -> None:
    """R0: 도구 이름·설명·경로 안내·머리 줄은 계약 데이터에만 있다(src 문자열 상수에 없다)."""
    defaults = wiki_access_defaults()
    banned = {t["name"] for t in defaults["tools"].values()}
    banned |= {t["description"] for t in defaults["tools"].values()}
    banned |= {defaults["path_hint"], defaults["result_header"]}
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        found |= _string_constants(path) & banned
    assert found == set()
    assert set(WIKI_ACCESS_OPS) == set(defaults["tools"])
