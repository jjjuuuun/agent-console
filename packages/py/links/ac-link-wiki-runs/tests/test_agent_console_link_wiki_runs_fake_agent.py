"""link-wiki-runs + fake-agent 실행(엔진 수준, 7R.14 완료 기준).

실행 범위(``WikiRunScope.scope_run``)가 넣은 X30 공급자로 에이전트가 위키 도구·지침을 받는다. fake
백엔드 규칙 ``host_tool_calls``로 모델의 도구 호출을 흉내 낸다(실제 SDK 호출 없음). 위키·규칙은 이
테스트의 데이터(메모리 저장소)만 쓴다.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from typing import Any

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    BackendDescriptor,
    EdgeSpec,
    Graph,
    KnownIssueCodes,
    KnownResourceSlots,
    ModelInfo,
    NodeSpec,
    Resource,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_contracts.wiki import WikiEventPayload, WikiRulesDefinition, wiki_access_defaults
from agent_console_link_wiki_runs import (
    DEFAULT_PROVIDER_ID,
    WikiResourceType,
    WikiRunScope,
    load_wiki_resource_type,
    wiki_slot,
)
from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    CONTEXT_PREPARED_EVENT,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    TEAM_LOOKUP,
    WORKSPACE_SETTINGS,
    instruction_source,
)
from agent_console_resources import SLOT_UNSUPPORTED, InMemoryResources
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    INTERACTION_KINDS_GROUP,
    NODE_TYPES_GROUP,
    AgentRequest,
    AgentResult,
    BackendEventSink,
    CancelToken,
    GraphRuntime,
    Registries,
    Services,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock
from agent_console_wiki import RulesDocument, WikiRepository, WikiToolTarget, merge_rules

DISTS = ("agent-console-nodes-core", "agent-console-delegation-host")
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)
WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake-agent"}})
RTYPE = load_wiki_resource_type()
TOOLS = {op: t["name"] for op, t in wiki_access_defaults()["tools"].items()}
SECRET_BODY = "결정 본문 — 응답 형식은 JSON v2 ZQX-889"
GUIDE = "결정은 decisions/ 아래에 쓰세요."


def _rules() -> Any:
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
    return merge_rules(["house"], [RulesDocument("house", rules, {"guide.md": GUIDE})])


@dataclass
class Recording:
    """fake 백엔드를 감싸 요청을 기록한다(지침 칸 확인용)."""

    inner: FakeBackend
    requests: list[AgentRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.descriptor: BackendDescriptor = self.inner.descriptor

    async def list_models(self) -> list[ModelInfo]:
        return await self.inner.list_models()

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        self.requests.append(req)
        return await self.inner.run(req, sink, cancel)


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder
    services: dict[Any, Any]
    scope: WikiRunScope | None
    backend: Recording
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

    def wiki(self, run: Run) -> list[tuple[str, dict[str, Any]]]:
        return [(e.type, dict(e.payload)) for e in self.events(run, "wiki.")]

    def warnings(self, run: Run) -> list[dict[str, Any]]:
        return [dict(e.payload["details"]) for e in self.events(run, "log.warning")]

    def output(self, run: Run, node_id: str) -> Any:
        found = [nr for nr in self.recorder.runs.list_node_runs(run.id) if nr.node_id == node_id]
        return found[0].outputs.get("out")


def make_stack(
    agents: list[Agent],
    resources: list[Resource],
    *,
    service: StaticWikiService | None,
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
    backend = Recording(FakeBackend(ids=SequentialIds("s"), clock=StepClock()))
    regs.backends.register("fake-agent", backend)
    regs.extension(RESOURCE_TYPES_EXTENSION).register(RTYPE.id, WikiResourceType(RTYPE))
    found = {a.id: a for a in agents}
    services: dict[Any, Any] = {
        AGENT_LOOKUP: found.get,
        WORKSPACE_SETTINGS: WORKSPACE,
        RESOURCE_LOOKUP: InMemoryResources(resources),
    }
    if teams:
        services[TEAM_LOOKUP] = lambda team_id, version: teams.get(team_id)
    scope = WikiRunScope(lambda: service, slot=wiki_slot(RTYPE), max_writes_per_run=max_writes)
    return Stack(regs, InMemoryRecorder(), services, scope, backend)


def wiki_service(**spaces: dict[str, WikiRepository | WikiToolTarget]) -> StaticWikiService:
    table: dict[str | None, dict[str, WikiRepository | WikiToolTarget]] = {}
    for name, wikis in spaces.items():
        table[None if name == "root" else name] = wikis
    return StaticWikiService(table)


def access(ref: str, wikis: list[dict[str, Any]], **config: Any) -> Resource:
    return Resource.model_validate(
        {"id": ref, "type": RTYPE.id, "name": ref, "config": {"wikis": wikis, **config}}
    )


def agent(
    agent_id: str,
    response: str,
    *tool_calls: tuple[str, dict[str, Any]],
    resources: tuple[str, ...] = (),
    name: str | None = None,
) -> Agent:
    rule: dict[str, Any] = {"response": response}
    if tool_calls:
        rule["host_tool_calls"] = [{"tool": t, "input": i, "append": False} for t, i in tool_calls]
    return Agent.model_validate(
        {
            "id": agent_id,
            "name": name or agent_id,
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
        WikiEventPayload.model_validate(payload)
        for body in bodies:
            assert body not in repr(payload)


def instructions_of(request: AgentRequest) -> list[Any]:
    if request.bundle is None:
        return []
    return list(request.bundle.slots.get(KnownResourceSlots.INSTRUCTIONS) or [])


# ---------------------------------------------------------------- 한 바퀴


async def test_keeper_writes_then_other_agent_searches_and_reads() -> None:
    repo = memory_repository("notes", rules=_rules())
    service = wiki_service(root={"notes": WikiToolTarget(repo, pages_dir="/w/notes")})
    rw = access("rw", [{"wiki": "notes", "access": ["read", "search", "write"]}])
    keeper = agent(
        "keeper",
        "$host_1",
        (TOOLS["write"], {"path": "decisions/api", "content": "$prompt"}),
        resources=("rw",),
        name="위키 관리자",
    )
    reader = agent(
        "reader",
        "[$host_1_status|$host_2]",
        (TOOLS["search"], {"query": "응답 형식"}),
        (TOOLS["read"], {"path": "decisions/api"}),
        resources=("rw",),
    )
    stack = make_stack([keeper, reader], [rw], service=service)
    run = await stack.run(pipeline("keeper", "reader"), SECRET_BODY)
    assert run.status == "completed", run.error

    out = stack.output(run, "reader")
    assert out.startswith("[succeeded|")
    assert SECRET_BODY in out
    events = stack.wiki(run)
    assert [t for t, _ in events] == ["wiki.write", "wiki.search", "wiki.read"]
    write, search, read = (p for _, p in events)
    assert (write["status"], write["wiki"], write["path"]) == ("ok", "notes", "decisions/api")
    assert search["results"] == 1
    assert read["sha256"] == write["sha256"]
    calls = [e.payload["tool_use_id"] for e in stack.events(run, "agent.tool_call")]
    assert [p["tool_use_id"] for _, p in events] == calls
    no_body(events, SECRET_BODY, "응답 형식")
    by_node = {e.type: e.node_path for e in stack.events(run, "wiki.")}
    assert by_node == {"wiki.write": ["keeper"], "wiki.search": ["reader"], "wiki.read": ["reader"]}
    # 쓴 주체: 에이전트·실행·노드 + 기록 시점 이름
    assert repo.history is not None
    [version] = repo.history.list("notes", "decisions/api").items
    author = version.author
    assert (author.kind, author.agent_id, author.node_id, author.label) == (
        "agent",
        "keeper",
        "keeper",
        "위키 관리자",
    )
    assert (author.run_id, author.root_run_id, author.graph_id) == (run.id, run.id, "team")
    assert [(n.wiki_id, n.paths) for n in service.notices] == [("notes", ("decisions/api",))]
    # 소비한 칸은 "적용하지 못한 칸" 경고가 아니다
    assert not any(w["code"] == SLOT_UNSUPPORTED for w in stack.warnings(run))
    # 지침(규칙 지침 + 경로 안내)이 요청 묶음 지침 칸 끝에 공급자 출처로 붙는다
    first = stack.backend.requests[0]
    texts = [str(x) for x in instructions_of(first)]
    assert any(GUIDE in t for t in texts)
    assert any("/w/notes" in t for t in texts)
    assert first.bundle is not None
    refs = [s.ref for s in first.bundle.sources.get(KnownResourceSlots.INSTRUCTIONS, [])]
    assert instruction_source(DEFAULT_PROVIDER_ID) in refs
    prepared = stack.events(run, CONTEXT_PREPARED_EVENT)
    assert prepared
    assert GUIDE not in repr([e.payload for e in prepared])


async def test_label_stays_after_agent_definition_is_removed() -> None:
    repo = memory_repository("notes")
    service = wiki_service(root={"notes": repo})
    rw = access("rw", [{"wiki": "notes", "access": ["write"]}])
    keeper = agent(
        "keeper",
        "$host_1_status",
        (TOOLS["write"], {"path": "a", "content": "x"}),
        resources=("rw",),
        name="처음 이름",
    )
    stack = make_stack([keeper], [rw], service=service)
    run = await stack.run(solo("keeper"), "go")
    assert stack.output(run, "keeper") == "succeeded"
    stack.services[AGENT_LOOKUP] = {}.get  # 정의를 지웠다
    assert repo.history is not None
    [version] = repo.history.list("notes", "a").items
    assert version.author.label == "처음 이름"


async def test_write_rule_rejection_is_tool_error() -> None:
    service = wiki_service(root={"notes": memory_repository("notes", rules=_rules())})
    rw = access("rw", [{"wiki": "notes", "access": ["write"]}])
    a = agent(
        "a",
        "$host_1_status:$host_1",
        (TOOLS["write"], {"path": "x", "content": "TEMPNOTE 나중에"}),
        resources=("rw",),
    )
    stack = make_stack([a], [rw], service=service)
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error
    out = str(stack.output(run, "a"))
    assert out.startswith(f"failed:[{KnownIssueCodes.WIKI_RULE_REJECTED}]")
    assert "no-temp" in out
    [(kind, payload)] = stack.wiki(run)
    assert (kind, payload["status"], payload["rule_ids"]) == (
        "wiki.write",
        "rule_rejected",
        ["no-temp"],
    )
    assert service.notices == []


async def test_project_run_sees_only_its_space() -> None:
    a_repo = memory_repository("notes")
    b_repo = memory_repository("notes", files={"secret.md": "B 프로젝트"})
    service = wiki_service(
        pa={"notes": a_repo}, pb={"notes": b_repo, "only-b": memory_repository("only-b")}
    )
    res = access(
        "rw",
        [{"wiki": "notes", "access": ["read", "write"]}, {"wiki": "only-b", "access": ["read"]}],
    )
    a = agent(
        "a",
        "$host_1_status/$host_2_status/$host_3_status",
        (TOOLS["write"], {"path": "mine", "content": "A"}),
        (TOOLS["read"], {"path": "secret"}),
        (TOOLS["read"], {"path": "x", "wiki": "only-b"}),
        resources=("rw",),
    )
    stack = make_stack([a], [res], service=service)
    run = await stack.run(solo("a"), "go", project_id="pa")
    assert stack.output(run, "a") == "succeeded/failed/failed"
    statuses = [p["status"] for _, p in stack.wiki(run)]
    assert statuses == ["ok", "not_found", "wiki_unavailable"]
    assert a_repo.current("mine") is not None
    assert b_repo.current("mine") is None
    [warning] = [
        w for w in stack.warnings(run) if w["code"] == KnownIssueCodes.WIKI_WIKI_UNAVAILABLE
    ]
    assert warning["wikis"] == ["only-b"]
    assert warning["project_id"] == "pa"
    assert [n.space for n in service.notices] == ["pa"]


async def test_nested_team_and_shared_budget() -> None:
    repo = memory_repository("notes")
    service = wiki_service(root={"notes": repo})
    res = access("w", [{"wiki": "notes", "access": ["write"]}])
    lead = agent(
        "lead", "$prompt", (TOOLS["write"], {"path": "lead", "content": "1"}), resources=("w",)
    )
    c1 = agent(
        "c1",
        "$host_1_status",
        (TOOLS["write"], {"path": "child", "content": "2"}),
        resources=("w",),
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
        [lead, c1], [res], service=service, max_writes=1, teams={"child": solo("c1", "child")}
    )
    run = await stack.run(parent, "hi")
    assert run.status == "completed", run.error
    assert [p["status"] for _, p in stack.wiki(run)] == ["ok", "rate_limited"]
    # 다음 Run은 새 한도, 자식 Run의 쓴 주체는 자식 팀·루트 Run
    stack2 = make_stack([c1], [res], service=service, teams={"child": solo("c1", "child")})
    run2 = await stack2.run(
        team(
            [node("T", type="team", team_ref="child")],
            [
                edge("m", "you", "says", "T", "in", "message"),
                edge("r", "T", "out", "you", "hears", "reply"),
            ],
            "outer",
        ),
        "go",
    )
    assert run2.status == "completed", run2.error
    assert repo.history is not None
    [version] = repo.history.list("notes", "child").items
    assert (version.author.graph_id, version.author.root_run_id) == ("child", run2.id)
    assert version.author.run_id != run2.id


async def test_host_delegate_target_gets_its_own_tools() -> None:
    service = wiki_service(root={"notes": memory_repository("notes")})
    res = access("w", [{"wiki": "notes", "access": ["write"]}])
    lead = agent("pl", "[$host_1]", ("delegate", {"target": "be", "task": "$prompt"}))
    be = agent(
        "be",
        "<$host_1_status>",
        (TOOLS["write"], {"path": "be/note", "content": "$prompt"}),
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
    stack = make_stack([lead, be], [res], service=service)
    run = await stack.run(graph, "일")
    assert run.status == "completed", run.error
    assert stack.output(run, "pl") == "[<succeeded>]"
    [event] = stack.events(run, "wiki.")
    assert event.node_path == ["pl", "be"]


async def test_renamed_tools_and_nearest_layer() -> None:
    """팀 층은 읽기만, 에이전트 층이 쓰기를 더하고 도구 이름을 바꾼다(가까운 층이 이긴다)."""
    service = wiki_service(root={"notes": memory_repository("notes")})
    team_res = access("team-read", [{"wiki": "notes", "access": ["read"]}])
    mine = access(
        "mine",
        [{"wiki": "notes", "access": ["read", "write"]}],
        tools={"write": {"name": "jot_page", "description": "적기"}},
    )
    a = agent(
        "a",
        "$host_1_status/$host_2_status",
        ("jot_page", {"path": "k", "content": "x"}),
        (TOOLS["write"], {"path": "k", "content": "x"}),
        resources=("mine",),
    )
    graph = solo("a", resources=[{"ref": "team-read"}])
    stack = make_stack([a], [team_res, mine], service=service)
    run = await stack.run(graph, "go")
    assert run.status == "completed", run.error
    assert stack.output(run, "a") == "succeeded/failed"  # 기본 이름은 없다
    [(_, payload)] = stack.wiki(run)
    assert payload["tool"] == "jot_page"


async def test_without_wiki_service_run_completes_with_one_slot_warning() -> None:
    res = access("w", [{"wiki": "notes", "access": ["write"]}])
    a = agent(
        "a", "$host_1_status", (TOOLS["write"], {"path": "a", "content": "1"}), resources=("w",)
    )
    stack = make_stack([a], [res], service=None)
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error
    assert stack.output(run, "a") == "failed"
    assert stack.wiki(run) == []
    slot_warnings = [w for w in stack.warnings(run) if w["code"] == SLOT_UNSUPPORTED]
    assert len(slot_warnings) == 1
    assert slot_warnings[0]["slot"] == wiki_slot(RTYPE)


async def test_agent_without_resource_gets_no_tools_or_instructions() -> None:
    service = wiki_service(root={"notes": memory_repository("notes", rules=_rules())})
    a = agent("a", "$host_1_status", (TOOLS["search"], {"query": "x"}))
    stack = make_stack([a], [], service=service)
    run = await stack.run(solo("a"), "go")
    assert stack.output(run, "a") == "failed"
    assert stack.wiki(run) == []
    assert all(GUIDE not in str(instructions_of(r)) for r in stack.backend.requests)
