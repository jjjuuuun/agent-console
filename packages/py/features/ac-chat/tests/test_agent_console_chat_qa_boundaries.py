"""QA 경계 테스트: 시작 중(start_turn 대기 중)의 팀 구성 전환·삭제."""

import asyncio

from agent_console_chat import ChatService
from agent_console_chat.testing import (
    FakeLauncher,
    MemoryConversations,
    MemoryEvents,
    MemoryGraphs,
    MemoryInteractions,
    MemoryRuns,
)
from agent_console_contracts import (
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    SessionRef,
    UpdateConversationRequest,
)


def _graph(gid: str, nodes: list[str]) -> Graph:
    return Graph(id=gid, name=gid, nodes=[NodeSpec(id=n, type="agent") for n in nodes])


class _SlowLauncher(FakeLauncher):
    def __init__(self, *a: object, **k: object) -> None:
        super().__init__(*a, **k)  # type: ignore[arg-type]
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()

    async def start_turn(self, turn):  # type: ignore[no-untyped-def]
        self.entered.set()
        await self.gate.wait()
        return await super().start_turn(turn)


async def test_switch_graph_while_turn_is_starting_is_not_overwritten() -> None:
    convs, runs, events = MemoryConversations(), MemoryRuns(), MemoryEvents()
    launcher = _SlowLauncher(runs, events)
    svc = ChatService(
        convs,
        MemoryGraphs([_graph("a", ["pl", "qa"]), _graph("b", ["pl"])]),
        launcher=launcher,
        runs=runs,
        events=events,
        interactions=MemoryInteractions(),
    )
    conv = svc.create(CreateConversationRequest(graph_id="a"))
    convs.save(
        conv.model_copy(update={"sessions": {"qa": SessionRef(backend="x", session_id="q")}})
    )
    post = asyncio.create_task(svc.post_message(conv.id, PostMessageRequest(text="hi")))
    await launcher.entered.wait()
    svc.update(conv.id, UpdateConversationRequest(graph_id="b"))
    launcher.gate.set()
    await post
    after = svc.get(conv.id)
    assert after.graph_id == "b"
    assert "qa" not in after.sessions
    await svc.aclose()
