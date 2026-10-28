"""link-memory-runs + fake-agent 실행(엔진 수준, 5.7R.15 완료 기준).

실행 범위(``MemoryRunScope.scope_run``)가 넣은 X30 공급자로 에이전트가 메모리 도구를 받는다. fake
백엔드 규칙 ``host_tool_calls``로 모델의 도구 호출을 흉내 낸다(실제 SDK 호출 없음). 범위 종류는 이
테스트의 데이터(``notes``·``journal``·``proj``·``top``)만 쓴다(패키지 기본 범위 종류를 끈다).
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from typing import Any

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    EdgeSpec,
    Graph,
    NodeSpec,
    Resource,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_contracts.memory import MemoryEventPayload
from agent_console_link_memory_runs import (
    MemoryResourceType,
    MemoryRunScope,
    load_memory_resource_type,
    memory_slot,
)
from agent_console_link_memory_runs.testing import StaticMemoryService
from agent_console_memory import merge_scope_kinds
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    TEAM_LOOKUP,
    WORKSPACE_SETTINGS,
)
from agent_console_resources import SLOT_UNSUPPORTED, InMemoryResources
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    INTERACTION_KINDS_GROUP,
    NODE_TYPES_GROUP,
    GraphRuntime,
    Registries,
    Services,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock

DISTS = ("agent-console-nodes-core", "agent-console-delegation-host")
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)
WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake-agent"}})
KINDS = {
    "notes": {"label": "노트", "id": "{/graph_id}"},
    "journal": {"label": "일지", "id": ""},
    "proj": {"label": "프로젝트 기록", "id": "{/project_id}"},
    "top": {"label": "최상위 팀", "id": "{/root_graph_id}"},
}
RTYPE = load_memory_resource_type()
SECRET_BODY = "결정 본문 — 버전 2를 쓴다 ZQX-889"


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder
    services: dict[Any, Any]
    scope: MemoryRunScope | None
    runs: int = 0

    async def run(self, graph: Graph, text: str, project_id: str | None = None) -> Run:
        self.runs += 1
        services = Services(self.services)
        if self.scope is not None:
            found = self.scope.scope_run(graph, services, project_id=project_id)
            if found is not None:
                for key, value in found.services.items():
                    services = services.with_(key, value)
        runtime = GraphRuntime(
            self.registries,
            self.recorder,
            clock=StepClock(),
            ids=SequentialIds(f"run{self.runs}-"),
            services=services,
        )
        return await runtime.run(graph, {"text": text})

    def events(self, run: Run, prefix: str = "") -> list[RunEvent]:
        out: list[RunEvent] = []
        for r in [run, *[c for c in self.recorder.runs.list() if c.parent_run_id == run.id]]:
            out += [e for e in self.recorder.events.list(r.id) if e.type.startswith(prefix)]
        return out

    def memory(self, run: Run) -> list[tuple[str, dict[str, Any]]]:
        return [(e.type, dict(e.payload)) for e in self.events(run, "memory.")]

    def warnings(self, run: Run) -> list[dict[str, Any]]:
        return [dict(e.payload["details"]) for e in self.events(run, "log.warning")]

    def output(self, run: Run, node_id: str) -> Any:
        found = [nr for nr in self.recorder.runs.list_node_runs(run.id) if nr.node_id == node_id]
        return found[0].outputs.get("out")


def make_stack(
    agents: list[Agent],
    resources: list[Resource],
    *,
    service: StaticMemoryService | None,
    max_writes: int | None = None,
    teams: dict[str, Graph] | None = None,
) -> Stack:
    regs = Registries()
    eps = [
        ep
        for dist in DISTS
        for ep in importlib.metadata.distribution(dist).entry_points
        if ep.group in GROUPS
    ]
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    regs.backends.register("fake-agent", FakeBackend(ids=SequentialIds("s"), clock=StepClock()))
    regs.extension(RESOURCE_TYPES_EXTENSION).register(RTYPE.id, MemoryResourceType(RTYPE))
    found = {a.id: a for a in agents}
    services: dict[Any, Any] = {
        AGENT_LOOKUP: found.get,
        WORKSPACE_SETTINGS: WORKSPACE,
        RESOURCE_LOOKUP: InMemoryResources(resources),
    }
    if teams:
        services[TEAM_LOOKUP] = lambda team_id, version: teams.get(team_id)
    scope = MemoryRunScope(lambda: service, slot=memory_slot(RTYPE), max_writes_per_run=max_writes)
    return Stack(regs, InMemoryRecorder(), services, scope)


def memory_service() -> StaticMemoryService:
    return StaticMemoryService(catalog=merge_scope_kinds(include_defaults=False, user=KINDS))


def access(ref: str, scopes: list[dict[str, Any]], **config: Any) -> Resource:
    return Resource.model_validate(
        {"id": ref, "type": RTYPE.id, "name": ref, "config": {"scopes": scopes, **config}}
    )


def agent(
    agent_id: str,
    response: str,
    *tool_calls: tuple[str, dict[str, Any]],
    resources: tuple[str, ...] = (),
) -> Agent:
    rule: dict[str, Any] = {"response": response}
    if tool_calls:
        rule["host_tool_calls"] = [{"tool": t, "input": i, "append": False} for t, i in tool_calls]
    return Agent.model_validate(
        {
            "id": agent_id,
            "name": agent_id,
            "backend_options": {"default": rule},
            "resources": [{"ref": r} for r in resources],
        }
    )


def node(node_id: str, ref: str | None = None, *, type: str = "agent", **config: Any) -> NodeSpec:
    cfg = dict(config)
    if type == "agent":
        cfg["agent_ref"] = ref or node_id
    return NodeSpec.model_validate({"id": node_id, "type": type, "label": node_id, "config": cfg})


def edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> EdgeSpec:
    return EdgeSpec.model_validate(
        {
            "id": eid,
            "source": {"node": src, "port": sp},
            "target": {"node": dst, "port": tp},
            "kind": kind,
            "config": {},
        }
    )


def team(
    nodes: list[NodeSpec],
    edges: list[EdgeSpec],
    graph_id: str = "team",
    settings: dict[str, Any] | None = None,
) -> Graph:
    doc: dict[str, Any] = {
        "id": graph_id,
        "name": graph_id,
        "nodes": [{"id": "you", "type": "user", "label": "나"}] + [x.model_dump() for x in nodes],
        "edges": [x.model_dump() for x in edges],
    }
    if settings is not None:
        doc["settings"] = settings
    return Graph.model_validate(doc)


def solo(node_id: str, graph_id: str = "team", **settings: Any) -> Graph:
    return team(
        [node(node_id)],
        [
            edge("m", "you", "says", node_id, "in", "message"),
            edge("r", node_id, "out", "you", "hears", "reply"),
        ],
        graph_id,
        settings or None,
    )


def pipeline(first: str, second: str) -> Graph:
    return team(
        [node(first), node(second)],
        [
            edge("m", "you", "says", first, "in", "message"),
            edge("h", first, "out", second, "in", "handoff"),
            edge("r", second, "out", "you", "hears", "reply"),
        ],
    )


def no_body(events: list[tuple[str, dict[str, Any]]], *bodies: str) -> None:
    for _type, payload in events:
        MemoryEventPayload.model_validate(payload)
        for body in bodies:
            assert body not in repr(payload)


# ---------------------------------------------------------------- 한 바퀴


async def test_write_then_other_agent_searches_and_reads() -> None:
    service = memory_service()
    rw = access("rw", [{"kind": "notes", "access": ["read", "search", "write"]}])
    writer = agent(
        "writer",
        "$host_1",
        ("memory_write", {"key": "결정/api", "content": "$prompt", "tags": ["결정"]}),
        resources=("rw",),
    )
    reader = agent(
        "reader",
        "[$host_1_status|$host_2]",
        ("memory_search", {"query": "버전"}),
        ("memory_read", {"key": "결정/api"}),
        resources=("rw",),
    )
    stack = make_stack([writer, reader], [rw], service=service)
    run = await stack.run(pipeline("writer", "reader"), SECRET_BODY)
    assert run.status == "completed", run.error

    out = stack.output(run, "reader")
    assert out.startswith("[succeeded|")
    assert SECRET_BODY in out
    events = stack.memory(run)
    assert [t for t, _ in events] == ["memory.write", "memory.search", "memory.read"]
    write, search, read = (p for _, p in events)
    assert write["scope"] == {"kind": "notes", "id": "team"}
    assert (write["status"], write["version"], write["key"]) == ("ok", 1, "결정/api")
    assert search["results"] == 1
    assert search["query_chars"] == 2
    assert read["entry_id"] == write["entry_id"]
    assert read["sha256"] == write["sha256"]
    # 도구 호출 id는 백엔드의 도구 호출 이벤트와 같다
    calls = [e.payload["tool_use_id"] for e in stack.events(run, "agent.tool_call")]
    assert [p["tool_use_id"] for _, p in events] == calls
    no_body(events, SECRET_BODY, "버전")
    by_node = {e.type: e.node_path for e in stack.events(run, "memory.")}
    assert by_node == {
        "memory.write": ["writer"],
        "memory.search": ["reader"],
        "memory.read": ["reader"],
    }
    # 쓴 주체: 에이전트·실행·노드
    entry = service.store.find(write_scope(write), "결정/api")
    assert entry is not None
    assert entry.content == SECRET_BODY
    assert (entry.created_by.agent_id, entry.created_by.run_id) == ("writer", run.id)
    # 소비한 칸은 "적용하지 못한 칸" 경고가 아니다
    assert not any(w["code"] == SLOT_UNSUPPORTED for w in stack.warnings(run))


def write_scope(payload: dict[str, Any]) -> Any:
    from agent_console_contracts.memory import MemoryScopeRef

    return MemoryScopeRef.model_validate(payload["scope"])


async def test_denied_scope_returns_error_and_event() -> None:
    res = access(
        "mixed",
        [
            {"kind": "notes", "access": ["read", "write"]},
            {"kind": "journal", "access": ["read"]},
        ],
    )
    a = agent(
        "a",
        "$host_1_status:$host_1",
        ("memory_write", {"key": "k", "content": "x", "scope": "journal"}),
        resources=("mixed",),
    )
    stack = make_stack([a], [res], service=memory_service())
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error
    assert str(stack.output(run, "a")).startswith("failed:[memory.denied]")
    [(kind, payload)] = stack.memory(run)
    assert kind == "memory.write"
    assert payload["status"] == "denied"


async def test_project_scope_unavailable_without_project() -> None:
    res = access("p", [{"kind": "proj", "access": ["read", "write"]}])
    a = agent(
        "a",
        "$host_1_status",
        ("memory_write", {"key": "k", "content": "x"}),
        resources=("p",),
    )
    service = memory_service()
    stack = make_stack([a], [res], service=service)
    run = await stack.run(solo("a"), "go")
    assert stack.output(run, "a") == "failed"
    [(_, payload)] = stack.memory(run)
    assert payload["status"] == "scope_unavailable"
    assert "scope" not in payload
    run = await stack.run(solo("a"), "go", project_id="p1")
    assert stack.output(run, "a") == "succeeded"
    [(_, payload)] = stack.memory(run)
    assert payload["scope"] == {"kind": "proj", "id": "p1"}


async def test_nested_team_uses_child_graph_and_root_graph() -> None:
    res = access(
        "nested",
        [{"kind": "notes", "access": ["write"]}, {"kind": "top", "access": ["write"]}],
    )
    c1 = agent(
        "c1",
        "ok",
        ("memory_write", {"key": "k", "content": "x", "scope": "notes"}),
        ("memory_write", {"key": "k", "content": "y", "scope": "top"}),
        resources=("nested",),
    )
    child = solo("c1", "child")
    parent = team(
        [node("lead"), node("T", type="team", team_ref="child")],
        [
            edge("m", "you", "says", "lead", "in", "message"),
            edge("h", "lead", "out", "T", "in", "handoff"),
            edge("r", "T", "out", "you", "hears", "reply"),
        ],
        "parent",
    )
    stack = make_stack(
        [agent("lead", "$prompt"), c1], [res], service=memory_service(), teams={"child": child}
    )
    run = await stack.run(parent, "hi")
    assert run.status == "completed", run.error
    scopes = [p["scope"] for _, p in stack.memory(run)]
    assert scopes == [{"kind": "notes", "id": "child"}, {"kind": "top", "id": "parent"}]


async def test_host_delegate_target_gets_its_own_tools() -> None:
    res = access("w", [{"kind": "journal", "access": ["write"]}])
    lead = agent("pl", "[$host_1]", ("delegate", {"target": "be", "task": "$prompt"}))
    be = agent(
        "be",
        "<$host_1_status>",
        ("memory_write", {"key": "be/note", "content": "$prompt"}),
        resources=("w",),
    )
    graph = team(
        [node("pl"), node("be")],
        [
            edge("m", "you", "says", "pl", "in", "message"),
            edge("pl->be", "pl", "delegates", "be", "delegated", "delegate"),
            edge("r", "pl", "out", "you", "hears", "reply"),
        ],
    )
    stack = make_stack([lead, be], [res], service=memory_service())
    run = await stack.run(graph, "일")
    assert run.status == "completed", run.error
    assert stack.output(run, "pl") == "[<succeeded>]"
    [event] = stack.events(run, "memory.")
    assert event.node_path == ["pl", "be"]
    assert event.payload["scope"] == {"kind": "journal", "id": ""}


async def test_renamed_tools_and_nearest_layer() -> None:
    """팀 층은 읽기만, 에이전트 층이 쓰기를 더하고 도구 이름을 바꾼다(가까운 층이 이긴다)."""
    team_res = access("team-read", [{"kind": "notes", "access": ["read"]}])
    mine = access(
        "mine",
        [{"kind": "notes", "access": ["read", "write"]}],
        tools={"write": {"name": "jot", "description": "적기"}},
    )
    a = agent(
        "a",
        "$host_1_status/$host_2_status",
        ("jot", {"key": "k", "content": "x"}),
        ("memory_write", {"key": "k", "content": "x"}),
        resources=("mine",),
    )
    graph = solo("a", resources=[{"ref": "team-read"}])
    stack = make_stack([a], [team_res, mine], service=memory_service())
    run = await stack.run(graph, "go")
    assert run.status == "completed", run.error
    assert stack.output(run, "a") == "succeeded/failed"  # 기본 이름은 없다
    [(_, payload)] = stack.memory(run)
    assert payload["tool"] == "jot"


async def test_write_budget_per_run() -> None:
    res = access("w", [{"kind": "journal", "access": ["write"]}])
    a = agent(
        "a",
        "$host_1_status/$host_2_status",
        ("memory_write", {"key": "a", "content": "1"}),
        ("memory_write", {"key": "b", "content": "2"}),
        resources=("w",),
    )
    stack = make_stack([a], [res], service=memory_service(), max_writes=1)
    run = await stack.run(solo("a"), "go")
    assert stack.output(run, "a") == "succeeded/failed"
    assert [p["status"] for _, p in stack.memory(run)] == ["ok", "rate_limited"]
    # 다음 Run은 새 한도
    run = await stack.run(solo("a"), "go")
    assert [p["status"] for _, p in stack.memory(run)] == ["ok", "rate_limited"]


async def test_write_budget_is_shared_with_nested_team_child_run() -> None:
    """5.7R.28 (5): 한도는 루트 Run 하나에 하나 — 중첩 팀 자식 Run도 같은 한도를 쓴다."""
    res = access("w", [{"kind": "journal", "access": ["write"]}])
    lead = agent(
        "lead", "$prompt", ("memory_write", {"key": "lead", "content": "1"}), resources=("w",)
    )
    c1 = agent(
        "c1", "$host_1_status", ("memory_write", {"key": "child", "content": "2"}), resources=("w",)
    )
    parent = team(
        [node("lead"), node("T", type="team", team_ref="child")],
        [
            edge("m", "you", "says", "lead", "in", "message"),
            edge("h", "lead", "out", "T", "in", "handoff"),
            edge("r", "T", "out", "you", "hears", "reply"),
        ],
        "parent",
    )
    stack = make_stack(
        [lead, c1],
        [res],
        service=memory_service(),
        max_writes=1,
        teams={"child": solo("c1", "child")},
    )
    run = await stack.run(parent, "hi")
    assert run.status == "completed", run.error
    assert [p["status"] for _, p in stack.memory(run)] == ["ok", "rate_limited"]


async def test_without_memory_service_run_completes_with_one_slot_warning() -> None:
    res = access("w", [{"kind": "journal", "access": ["write"]}])
    a = agent(
        "a",
        "$host_1_status",
        ("memory_write", {"key": "a", "content": "1"}),
        resources=("w",),
    )
    stack = make_stack([a], [res], service=None)
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error
    assert stack.output(run, "a") == "failed"  # 도구가 없다(SDK처럼 오류 결과)
    assert stack.memory(run) == []
    slot_warnings = [w for w in stack.warnings(run) if w["code"] == SLOT_UNSUPPORTED]
    assert len(slot_warnings) == 1
    assert slot_warnings[0]["slot"] == memory_slot(RTYPE)


async def test_agent_without_resource_gets_no_tools() -> None:
    a = agent("a", "$host_1_status", ("memory_search", {}))
    stack = make_stack([a], [], service=memory_service())
    run = await stack.run(solo("a"), "go")
    assert stack.output(run, "a") == "failed"
    assert stack.memory(run) == []
