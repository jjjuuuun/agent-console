"""5.7R.33y: 프로젝트 대화의 팀 구성 출처(선택 능력 `ProjectGraphLookup`).

- 조회가 `get_project_graph`를 가지면 `project_id`가 있는 대화는 그 프로젝트에서만 찾는다
  (만들기·팀 구성 바꾸기·턴 시작). 라이브러리로 넘어가 찾지 않는다.
- 같은 id가 라이브러리와 프로젝트에 다르게 있으면 프로젝트 사본으로 턴을 시작한다.
- 프로젝트 없는 대화, 능력이 없는 조회(`MemoryGraphs`)는 지금 동작.
"""

import pytest

from agent_console_chat import (
    ChatService,
    GraphNotFoundError,
    ProjectGraphLookup,
)
from agent_console_chat.testing import (
    FakeLauncher,
    MemoryConversations,
    MemoryEvents,
    MemoryGraphs,
    MemoryProjectGraphs,
    MemoryRuns,
)
from agent_console_contracts import (
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    UpdateConversationRequest,
)


def _graph(graph_id: str, *nodes: str) -> Graph:
    return Graph(id=graph_id, name=graph_id, nodes=[NodeSpec(id=n, type="agent") for n in nodes])


def _service(graphs: MemoryGraphs) -> tuple[ChatService, FakeLauncher]:
    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    service = ChatService(
        MemoryConversations(), graphs, launcher=launcher, runs=runs, events=events
    )
    return service, launcher


def _graphs() -> MemoryProjectGraphs:
    return MemoryProjectGraphs(
        [_graph("team", "library-node"), _graph("library-only", "x")],
        {"p1": [_graph("team", "project-node"), _graph("project-only", "y")]},
    )


async def test_project_conversation_uses_project_copy_only() -> None:
    graphs = _graphs()
    assert isinstance(graphs, ProjectGraphLookup)
    service, launcher = _service(graphs)
    conv = service.create(CreateConversationRequest(graph_id="team", project_id="p1"))
    await service.post_message(conv.id, PostMessageRequest(text="hi"))
    [start] = launcher.started
    assert [n.id for n in start.graph.nodes] == ["project-node"]
    assert start.project_id == "p1"
    assert all(project == "p1" for project, _ in graphs.calls)  # 라이브러리 조회 없음


def test_library_only_graph_is_not_found_in_project() -> None:
    service, _ = _service(_graphs())
    with pytest.raises(GraphNotFoundError):
        service.create(CreateConversationRequest(graph_id="library-only", project_id="p1"))
    with pytest.raises(GraphNotFoundError):
        service.create(CreateConversationRequest(graph_id="team", project_id="ghost"))
    conv = service.create(CreateConversationRequest(graph_id="project-only", project_id="p1"))
    with pytest.raises(GraphNotFoundError):  # 팀 구성 바꾸기도 그 프로젝트에서만
        service.update(conv.id, UpdateConversationRequest(graph_id="library-only"))
    changed = service.update(conv.id, UpdateConversationRequest(graph_id="team"))
    assert changed.graph_id == "team"


async def test_without_project_or_capability_uses_get_graph() -> None:
    graphs = _graphs()
    service, launcher = _service(graphs)
    conv = service.create(CreateConversationRequest(graph_id="team"))
    await service.post_message(conv.id, PostMessageRequest(text="hi"))
    assert [n.id for n in launcher.started[0].graph.nodes] == ["library-node"]
    assert all(project is None for project, _ in graphs.calls)
    # 능력이 없는 조회는 프로젝트 대화도 get_graph(지금 동작)
    plain = MemoryGraphs([_graph("team", "library-node")])
    assert not isinstance(plain, ProjectGraphLookup)
    service, launcher = _service(plain)
    conv = service.create(CreateConversationRequest(graph_id="team", project_id="p1"))
    await service.post_message(conv.id, PostMessageRequest(text="hi"))
    assert [n.id for n in launcher.started[0].graph.nodes] == ["library-node"]
