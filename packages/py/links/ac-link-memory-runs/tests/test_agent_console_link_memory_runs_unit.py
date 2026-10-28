"""link-memory-runs 단위: 리소스 종류 데이터·층 합치기·공급자·저장 전 검사·설정(5.7R.15).

서버·실행 엔진 없이 부품만 쓴다. 범위 종류 이름은 테스트 데이터(``notes``·``journal``)이고 패키지
기본 범위 종류에 기대지 않는다.
"""

from __future__ import annotations

import ast
import importlib.metadata
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import (
    BackendCapabilities,
    KnownIssueCodes,
    Resource,
    ResourceAttachment,
    ResourceBundle,
)
from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryEventPayload,
    memory_access_defaults,
)
from agent_console_link_memory_runs import (
    MemoryResourceCheck,
    MemoryResourceType,
    MemoryRunsCodes,
    MemoryRunScope,
    MemoryRunsSettings,
    MemoryServiceLike,
    MemoryToolProvider,
    access_context,
    load_memory_resource_type,
    memory_slot,
    merge_access,
)
from agent_console_link_memory_runs.testing import StaticMemoryService
from agent_console_memory import merge_scope_kinds
from agent_console_nodes_core import TOOL_PROVIDERS, ToolProvider, ToolProvisionContext
from agent_console_resources import ContributeContext
from agent_console_runtime import CancelToken, Services

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_link_memory_runs"
KINDS = {"notes": {"label": "노트", "id": "{/graph_id}"}, "journal": {"label": "일지", "id": ""}}


def _service(kinds: Mapping[str, Any] = KINDS) -> StaticMemoryService:
    return StaticMemoryService(catalog=merge_scope_kinds(include_defaults=False, user=dict(kinds)))


def _item(config: dict[str, Any], layer: str | None = None) -> dict[str, Any]:
    return {"resource": "m", "layer": layer, "config": config}


def _ctx(
    bundle: ResourceBundle,
    events: list[tuple[str, Mapping[str, Any]]] | None = None,
    *,
    run_id: str = "r1",
    root_run_id: str = "r1",
    graph_id: str = "g1",
) -> ToolProvisionContext:
    async def emit(event_type: str, payload: Mapping[str, Any]) -> None:
        if events is not None:
            events.append((event_type, payload))

    return ToolProvisionContext(
        run_id=run_id,
        root_run_id=root_run_id,
        graph_id=graph_id,
        node_id="a",
        node_path=("a",),
        agent_id="writer",
        call=0,
        iteration=0,
        bundle=bundle,
        backend_capabilities=BackendCapabilities(host_tools=True),
        emit=emit,
        cancel=CancelToken(),
    )


# ---------------------------------------------------------------- 리소스 종류(데이터)


def test_descriptor_is_package_data_with_contract_schema() -> None:
    rtype = MemoryResourceType()
    d = rtype.descriptor
    assert d.contributes
    assert memory_slot(d) == d.contributes[0]
    assert d.config_schema == MemoryAccessConfig.model_json_schema()
    # 범위 종류 칸은 계약의 x-ui 위젯(목록은 서버 데이터)
    assert "memory-scope-kind" in repr(d.config_schema)
    # entry point 이름 = 디스크립터 id(리소스 정의의 type이 가리킨다)
    eps = importlib.metadata.distribution("agent-console-link-memory-runs").entry_points
    [ep] = [e for e in eps if e.group == "agent_console.resource_types"]
    assert ep.name == d.id
    assert ep.load() is MemoryResourceType


def test_descriptor_data_can_be_replaced() -> None:
    d = load_memory_resource_type(
        {"id": "team-notes", "title": "노트 접근", "contributes": ["notes_slot"]}
    )
    rtype = MemoryResourceType(d)
    res = Resource(id="x", type="team-notes", name="x", config={"scopes": []})
    [c] = rtype.contribute(res, None, ContributeContext(ResourceAttachment(ref="x"), "agent"))
    assert c.slot == "notes_slot"
    assert c.value == [{"resource": "x", "layer": "agent", "config": {"scopes": []}}]
    with pytest.raises(ValueError, match="contributes"):
        load_memory_resource_type({"id": "x", "title": "x", "contributes": []})


def test_validate_rejects_bad_config_without_values() -> None:
    rtype = MemoryResourceType()
    bad = Resource(
        id="m",
        type=rtype.descriptor.id,
        name="m",
        config={"scopes": [{"kind": "notes", "access": ["fly"]}], "max_result_chars": 0},
    )
    issues = rtype.validate(bad)
    assert issues
    assert all(i.severity == "error" for i in issues)
    assert {i.path for i in issues} >= {"/scopes/0/access/0", "/max_result_chars"}
    good = bad.model_copy(update={"config": {"scopes": [{"kind": "notes"}]}})
    assert rtype.validate(good) == []


# ---------------------------------------------------------------- 층 합치기


def test_merge_access_nearest_layer_wins_per_scope_kind() -> None:
    far = _item(
        {
            "scopes": [
                {"kind": "notes", "access": ["read", "search"]},
                {"kind": "journal", "access": ["read"]},
            ],
            "default_scope": "journal",
            "tools": {"search": {"name": "far_search", "description": "먼"}},
            "max_result_chars": 100,
        },
        "team",
    )
    near = _item(
        {
            "scopes": [{"kind": "notes", "access": ["write"]}],
            "tools": {"write": {"name": "near_write", "description": "가까운"}},
        },
        "agent",
    )
    access, issues = merge_access([far, near])
    assert issues == []
    assert access is not None
    assert [(s.kind, s.access) for s in access.scopes] == [
        ("notes", ["write"]),
        ("journal", ["read"]),
    ]
    assert access.default_scope == "journal"  # 가까운 층이 정하지 않은 키는 먼 층 값
    assert access.max_result_chars == 100
    assert (access.tools.search.name, access.tools.write.name) == ("far_search", "near_write")
    defaults = memory_access_defaults()["tools"]
    assert access.tools.read.name == defaults["read"]["name"]


def test_merge_access_same_kind_in_one_attachment_unions_ops() -> None:
    one = _item(
        {
            "scopes": [
                {"kind": "notes", "access": ["read"]},
                {"kind": "notes", "access": ["write"]},
                {"kind": "journal"},
            ]
        }
    )
    access, _ = merge_access([one])
    assert access is not None
    default_ops = (
        MemoryAccessConfig.model_validate({"scopes": [{"kind": "journal"}]}).scopes[0].access
    )
    assert [(s.kind, s.access) for s in access.scopes] == [
        ("notes", ["read", "write"]),
        ("journal", default_ops),
    ]


def test_merge_access_empty_and_invalid() -> None:
    assert merge_access([]) == (None, [])
    assert merge_access("x") == (None, [])
    assert merge_access([{"no": "config"}]) == (None, [])
    access, issues = merge_access([_item({"scopes": [], "max_result_chars": -1})])
    assert access is None
    [issue] = issues
    assert issue.code == MemoryRunsCodes.ACCESS_INVALID
    assert issue.details["paths"] == ["/max_result_chars"]


# ---------------------------------------------------------------- 공급자


def test_provider_satisfies_protocol_and_skips_without_slot() -> None:
    service = _service()
    assert isinstance(service, MemoryServiceLike)
    provider = MemoryToolProvider(lambda: service, slot="memory")
    assert isinstance(provider, ToolProvider)
    got = provider.provide(_ctx(ResourceBundle(slots={"other": []})))
    assert got.host_tools == ()
    assert got.consumed_slots == frozenset()


def test_provider_without_service_does_not_consume_slot() -> None:
    provider = MemoryToolProvider(lambda: None, slot="memory")
    bundle = ResourceBundle(slots={"memory": [_item({"scopes": [{"kind": "notes"}]})]})
    got = provider.provide(_ctx(bundle))
    assert got.consumed_slots == frozenset()
    assert got.host_tools == ()


async def test_provider_tools_follow_access_and_emit_payload_without_body() -> None:
    service = _service()
    events: list[tuple[str, Mapping[str, Any]]] = []
    config = {
        "scopes": [{"kind": "notes", "access": ["read", "search", "write"]}],
        "tools": {
            "write": {"name": "notes_put", "description": "기록"},
            "read": {"name": "notes_get", "description": "읽기"},
        },
    }
    provider = MemoryToolProvider(lambda: service, slot="memory", project_id="p1")
    got = provider.provide(_ctx(ResourceBundle(slots={"memory": [_item(config)]}), events))
    assert got.consumed_slots == {"memory"}
    names = [t.name for t in got.host_tools]
    defaults = memory_access_defaults()["tools"]
    assert names == ["notes_get", defaults["search"]["name"], "notes_put"]  # delete 없음
    tools = {t.name: t for t in got.host_tools}
    body = "비밀이 아닌 결정 본문 XYZ-123"
    assert tools["notes_put"].call_handler is not None
    result = await tools["notes_put"].call_handler({"key": "결정/api", "content": body}, "tu-1")
    assert not result.is_error, result.text
    found = await tools["notes_get"].handler({"key": "결정/api"})
    assert body in found.text
    assert [t for t, _ in events] == ["memory.write", "memory.read"]
    write = dict(events[0][1])
    assert write["tool"] == "notes_put"
    assert write["tool_use_id"] == "tu-1"
    assert write["scope"] == {"kind": "notes", "id": "g1"}
    assert write["status"] == "ok"
    assert write["version"] == 1
    assert "tool_use_id" not in events[1][1]  # handler 경로는 호출 id 없음
    for _type, payload in events:
        MemoryEventPayload.model_validate(payload)
        assert body not in repr(payload)
    # 쓴 주체에 실행·노드·프로젝트가 남는다
    entry = service.store.find(write_scope(write), "결정/api")
    assert entry is not None
    by = entry.created_by
    assert (by.kind, by.run_id, by.node_id, by.agent_id, by.project_id) == (
        "agent",
        "r1",
        "a",
        "writer",
        "p1",
    )


def write_scope(payload: Mapping[str, Any]) -> Any:
    from agent_console_contracts.memory import MemoryScopeRef

    return MemoryScopeRef.model_validate(payload["scope"])


async def test_provider_invalid_merge_consumes_slot_and_warns() -> None:
    provider = MemoryToolProvider(_service, slot="memory")
    bundle = ResourceBundle(slots={"memory": [_item({"max_result_chars": "많이"})]})
    got = provider.provide(_ctx(bundle))
    assert got.consumed_slots == {"memory"}
    assert got.host_tools == ()
    assert [w.code for w in got.warnings] == [MemoryRunsCodes.ACCESS_INVALID]


def test_access_context_root_and_child_values() -> None:
    root = access_context(_ctx(ResourceBundle()), project_id="p1")
    assert (root.graph_id, root.root_graph_id, root.project_id) == ("g1", "g1", "p1")
    child_ctx = _ctx(ResourceBundle(), run_id="c1", root_run_id="r1", graph_id="child")
    assert access_context(child_ctx).root_graph_id == ""
    given = access_context(child_ctx, project_id=None, root_graph_id="parent")
    assert (given.graph_id, given.root_graph_id, given.project_id) == ("child", "parent", "")
    assert given.node_path == ["a"]


# ---------------------------------------------------------------- 실행 범위


def test_run_scope_adds_provider_after_existing() -> None:
    service = _service()
    scope = MemoryRunScope(lambda: service, slot="memory", max_writes_per_run=3)
    from agent_console_contracts import Graph

    graph = Graph.model_validate({"id": "g1", "name": "g", "nodes": [], "edges": []})
    sentinel = object()
    services = Services({TOOL_PROVIDERS: (sentinel,)})
    found = scope.scope_run(graph, services, project_id="p1")
    assert found is not None
    assert found.warnings == ()
    providers = found.services[TOOL_PROVIDERS]
    assert providers[0] is sentinel
    provider = providers[1]
    assert isinstance(provider, MemoryToolProvider)
    assert (provider.project_id, provider.root_graph_id) == ("p1", "g1")
    assert provider.write_budget is not None
    assert provider.write_budget.limit == 3
    # Run마다 새 공급자·새 쓰기 한도
    again = scope.scope_run(graph, Services(), project_id=None)
    assert again is not None
    [other] = again.services[TOOL_PROVIDERS]
    assert other.write_budget is not provider.write_budget
    off = MemoryRunScope(lambda: None, slot="memory")
    assert off.scope_run(graph, Services(), project_id=None) is None


# ---------------------------------------------------------------- 저장 전 검사


def test_check_warns_unknown_scope_kinds_only_for_memory_resources() -> None:
    check = MemoryResourceCheck(_service, resource_type="memory")
    doc = {
        "id": "m",
        "type": "memory",
        "name": "m",
        "config": {
            "scopes": [{"kind": "notes"}, {"kind": "ghost"}],
            "default_scope": "phantom",
        },
    }
    issues = check.issues("resource", doc)
    assert [(i.code, i.path, i.details["kind"], i.severity) for i in issues] == [
        (KnownIssueCodes.MEMORY_UNKNOWN_SCOPE_KIND, "/config/scopes/1/kind", "ghost", "warning"),
        (KnownIssueCodes.MEMORY_UNKNOWN_SCOPE_KIND, "/config/default_scope", "phantom", "warning"),
    ]
    assert check.issues("resource", Resource.model_validate(doc)) == issues
    assert check.issues("agent", doc) == []
    assert check.issues("resource", {**doc, "type": "rule"}) == []
    assert MemoryResourceCheck(lambda: None, resource_type="memory").issues("resource", doc) == []


# ---------------------------------------------------------------- 설정·하드코딩


def test_settings_schema_has_labels() -> None:
    schema = MemoryRunsSettings.model_json_schema()
    field = schema["properties"]["max_writes_per_run"]
    assert field["title"]
    assert field["description"]
    assert field["x-ui"]["tier"] == "advanced"
    assert MemoryRunsSettings(max_writes_per_run=None).max_writes_per_run is None
    with pytest.raises(ValueError, match="greater than or equal"):
        MemoryRunsSettings(max_writes_per_run=0)


def _string_constants(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_no_hardcoded_scope_kind_tool_or_resource_type_names() -> None:
    """소스 문자열 상수에 기본 범위 종류 id·기본 도구 이름이 없다(R0).

    리소스 종류 id·칸 이름은 패키지 데이터에서 읽는다(데이터를 바꿔도 같은 동작 —
    ``test_descriptor_data_can_be_replaced``).
    """
    from agent_console_memory import load_default_scope_kinds

    banned = set(load_default_scope_kinds())
    banned |= {t["name"] for t in memory_access_defaults()["tools"].values()}
    for path in SRC.glob("*.py"):
        if path.name == "testing.py":
            continue
        leaked = _string_constants(path) & banned
        assert not leaked, (path.name, leaked)
