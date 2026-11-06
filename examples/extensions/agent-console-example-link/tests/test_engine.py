"""엔진 시험: 실행 범위(``NotesRunScope``)가 넣은 X30 공급자로 에이전트가 노트 도구·지침을 받는다.

fake 백엔드 규칙 ``host_tool_calls``로 모델의 도구 호출을 흉내 낸다(모델 호출 없음). 노트는
테스트 대역 ``StaticNotesReader``(메모리)다.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from typing import Any

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    BackendDescriptor,
    Graph,
    KnownResourceSlots,
    ModelInfo,
    Resource,
    Run,
    WorkspaceSettings,
)
from agent_console_example_link import (
    MODULE_ID,
    NotesResourceType,
    NotesRunScope,
    NotesRunsSettings,
    load_resource_type,
    notes_slot,
)
from agent_console_example_link.testing import StaticNote, StaticNotesReader
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    WORKSPACE_SETTINGS,
    instruction_source,
)
from agent_console_resources import SLOT_UNSUPPORTED, InMemoryResources
from agent_console_runtime import (
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

WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake-agent"}})
RTYPE = load_resource_type()
TEXT = NotesRunsSettings().text()
TOOL = TEXT.name
SECRET = "비밀 메모 본문 QZX-41"
APP_NOTES = (
    StaticNote("n1", SECRET, ("회의",)),
    StaticNote("n2", "배포는 금요일", ("배포",)),
    StaticNote("n3", "회고는 월요일", ("회의",)),
)


@dataclass
class Recording:
    """fake 백엔드를 감싸 요청을 기록한다(도구·지침 확인용)."""

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
    scope: NotesRunScope
    backend: Recording

    async def run(self, graph: Graph, text: str, project_id: str | None = None) -> Run:
        services = Services(self.services)
        found = self.scope.scope_run(graph, services, project_id=project_id)
        if found is not None:
            for key, value in found.services.items():
                services = services.with_(key, value)
        runtime = GraphRuntime(
            self.registries,
            self.recorder,
            clock=StepClock(),
            ids=SequentialIds("run-"),
            services=services,
        )
        return await runtime.run(graph, {"text": text})

    def events(self, run: Run, prefix: str) -> list[dict[str, Any]]:
        return [
            dict(e.payload) for e in self.recorder.events.list(run.id) if e.type.startswith(prefix)
        ]

    def warning_codes(self, run: Run) -> list[str]:
        return [str(p["details"].get("code")) for p in self.events(run, "log.warning")]

    def output(self, run: Run, node_id: str) -> Any:
        found = [nr for nr in self.recorder.runs.list_node_runs(run.id) if nr.node_id == node_id]
        return found[0].outputs.get("out")


def make_stack(
    agents: list[Agent],
    resources: list[Resource],
    reader: StaticNotesReader | None,
    *,
    max_notes: int | None = NotesRunsSettings().max_notes_per_call,
) -> Stack:
    regs = Registries()
    eps = [
        ep
        for ep in importlib.metadata.distribution("agent-console-nodes-core").entry_points
        if ep.group in (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, INTERACTION_KINDS_GROUP)
    ]
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    backend = Recording(FakeBackend(ids=SequentialIds("s"), clock=StepClock()))
    regs.backends.register("fake-agent", backend)
    regs.extension(RESOURCE_TYPES_EXTENSION).register(RTYPE.id, NotesResourceType(RTYPE))
    found = {a.id: a for a in agents}
    services: dict[Any, Any] = {
        AGENT_LOOKUP: found.get,
        WORKSPACE_SETTINGS: WORKSPACE,
        RESOURCE_LOOKUP: InMemoryResources(resources),
    }
    scope = NotesRunScope(
        lambda: reader,
        slot=notes_slot(RTYPE),
        text=TEXT,
        provider_id=MODULE_ID,
        max_notes=max_notes,
    )
    return Stack(regs, InMemoryRecorder(), services, scope, backend)


def notes_resource(ref: str = "notes", **config: Any) -> Resource:
    return Resource.model_validate({"id": ref, "type": RTYPE.id, "name": ref, "config": config})


def agent(agent_id: str, *calls: dict[str, Any], resources: tuple[str, ...] = ()) -> Agent:
    rule: dict[str, Any] = {"response": "[$host_1_status]$host_1"}
    if calls:
        rule["host_tool_calls"] = [{"tool": TOOL, "input": c, "append": False} for c in calls]
    return Agent.model_validate(
        {
            "id": agent_id,
            "name": agent_id,
            "backend_options": {"default": rule},
            "resources": [{"ref": r} for r in resources],
        }
    )


def solo(node_id: str) -> Graph:
    def edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> dict[str, Any]:
        return {
            "id": eid,
            "source": {"node": src, "port": sp},
            "target": {"node": dst, "port": tp},
            "kind": kind,
            "config": {},
        }

    return Graph.model_validate(
        {
            "id": "team",
            "name": "team",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {
                    "id": node_id,
                    "type": "agent",
                    "label": node_id,
                    "config": {"agent_ref": node_id},
                },
            ],
            "edges": [
                edge("m", "you", "says", node_id, "in", "message"),
                edge("r", node_id, "out", "you", "hears", "reply"),
            ],
        }
    )


def instructions_of(request: AgentRequest) -> list[str]:
    if request.bundle is None:
        return []
    return [str(x) for x in request.bundle.slots.get(KnownResourceSlots.INSTRUCTIONS) or []]


def tool_names(request: AgentRequest) -> list[str]:
    return [t.name for t in request.host_tools]


# ---------------------------------------------------------------- 도구가 보이고 지침이 붙는다


async def test_agent_with_resource_gets_tool_and_instructions() -> None:
    reader = StaticNotesReader({None: APP_NOTES})
    a = agent("a", {}, resources=("notes",))
    stack = make_stack([a], [notes_resource()], reader)
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error

    [request] = stack.backend.requests
    assert tool_names(request) == [TOOL]
    texts = instructions_of(request)
    assert any(TOOL in t for t in texts)
    assert request.bundle is not None
    refs = [s.ref for s in request.bundle.sources.get(KnownResourceSlots.INSTRUCTIONS, [])]
    assert instruction_source(MODULE_ID) in refs
    # 소비한 칸은 백엔드로 넘어가지 않는다(적용하지 못한 칸 경고 없음)
    assert notes_slot(RTYPE) not in request.bundle.slots
    assert SLOT_UNSUPPORTED not in stack.warning_codes(run)

    out = stack.output(run, "a")
    assert out.startswith("[succeeded]")
    assert "배포는 금요일" in out
    [event] = stack.events(run, TEXT.event_type)
    assert (event["provider"], event["tool"], event["status"], event["count"]) == (
        MODULE_ID,
        TOOL,
        "ok",
        3,
    )
    assert SECRET not in repr(event)  # 이벤트에 본문이 없다
    assert reader.calls == [(None, 20)]  # 설치자 한도(기본 데이터)


async def test_resource_tag_limit_and_installer_cap() -> None:
    reader = StaticNotesReader({None: APP_NOTES})
    a = agent("a", {}, {"limit": 5, "tag": "배포"}, resources=("notes",))
    stack = make_stack([a], [notes_resource(tag="회의", limit=9)], reader, max_notes=1)
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error
    first, second = (e["count"] for e in stack.events(run, TEXT.event_type))
    assert (first, second) == (1, 1)  # 리소스 태그 회의 2건 → 상한 1, 입력 태그 배포 1건
    assert "[n1]" in stack.output(run, "a")  # 첫 호출 결과(리소스 태그 회의, 최근 것부터 1건)


# ---------------------------------------------------------------- 리소스·범위 밖이면 없다


async def test_agent_without_resource_gets_nothing() -> None:
    reader = StaticNotesReader({None: APP_NOTES})
    a = agent("a", {})
    stack = make_stack([a], [], reader)
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error
    [request] = stack.backend.requests
    assert tool_names(request) == []
    assert not any(TOOL in t for t in instructions_of(request))
    assert stack.events(run, TEXT.event_type) == []
    assert reader.calls == []


async def test_without_reader_run_completes_with_one_slot_warning() -> None:
    a = agent("a", {}, resources=("notes",))
    stack = make_stack([a], [notes_resource()], None)
    run = await stack.run(solo("a"), "go")
    assert run.status == "completed", run.error
    [request] = stack.backend.requests
    assert tool_names(request) == []
    assert stack.warning_codes(run).count(SLOT_UNSUPPORTED) == 1
    assert stack.events(run, TEXT.event_type) == []


async def test_project_run_reads_only_its_space() -> None:
    reader = StaticNotesReader({None: APP_NOTES, "p1": (StaticNote("x", "프로젝트 노트"),)})
    a = agent("a", {}, resources=("notes",))
    stack = make_stack([a], [notes_resource()], reader)
    run = await stack.run(solo("a"), "go", project_id="p1")
    out = stack.output(run, "a")
    assert "프로젝트 노트" in out
    assert "배포는 금요일" not in out
    [event] = stack.events(run, TEXT.event_type)
    assert (event["project_id"], event["count"]) == ("p1", 1)


async def test_unknown_space_is_tool_error_and_run_continues() -> None:
    reader = StaticNotesReader({None: APP_NOTES})
    a = agent("a", {}, resources=("notes",))
    stack = make_stack([a], [notes_resource()], reader)
    run = await stack.run(solo("a"), "go", project_id="ghost")
    assert run.status == "completed", run.error
    assert stack.output(run, "a").startswith("[failed]")
    [event] = stack.events(run, TEXT.event_type)
    assert (event["status"], event["count"]) == ("feature_unavailable", 0)


async def test_invalid_resource_config_gives_no_tool() -> None:
    """틀린 리소스 설정은 리소스 검사가 먼저 막는다(칸이 생기지 않아 도구도 없다)."""
    reader = StaticNotesReader({None: APP_NOTES})
    bad = Resource.model_validate(
        {"id": "notes", "type": RTYPE.id, "name": "n", "config": {"limit": 0}}
    )
    a = agent("a", {}, resources=("notes",))
    stack = make_stack([a], [bad], reader)
    run = await stack.run(solo("a"), "go")
    [request] = stack.backend.requests
    assert tool_names(request) == []
    assert "resource.invalid_config" in stack.warning_codes(run)
    assert reader.calls == []
