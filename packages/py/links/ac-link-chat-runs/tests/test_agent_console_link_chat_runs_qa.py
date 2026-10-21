"""QA(3R.14): 종료 순서 전체, 재시작 대기열 정책 run/drop, 늦은 연결(connect) 경계."""

from __future__ import annotations

from typing import Any, cast

import pytest

from agent_console_chat import (
    ChatFeatureUnavailableError,
    ChatService,
    MemoryQueue,
    layered_chat_settings,
)
from agent_console_chat.testing import MemoryConversations
from agent_console_contracts import (
    ChatSettings,
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    QueuedMessage,
    Run,
)
from agent_console_link_chat_runs import CHAT_CONVERSATIONS, CHAT_TURN_LAUNCHER, module
from agent_console_link_chat_runs.testing import (
    LocalRunStarter,
    local_chat_module,
    local_runs_module,
)
from agent_console_modkit import assemble

GRAPH = Graph(id="team", name="팀", nodes=[NodeSpec(id="pl", type="agent")])


def _build(starter: LocalRunStarter, conversations: Any, queue: Any, mode: str = "ask") -> Any:
    return assemble(
        [
            module,
            local_chat_module(
                graphs=[GRAPH],
                conversations=conversations,
                queue=queue,
                settings=layered_chat_settings(ChatSettings(queue_after_restart=mode)),  # type: ignore[arg-type]
            ),
            local_runs_module(starter=starter),
        ]
    )


async def test_shutdown_order_dispatch_then_runs_then_watchers() -> None:
    order: list[str] = []
    starter = LocalRunStarter()
    original = starter.shutdown

    async def shutdown() -> None:
        order.append("runs.starter.shutdown")
        await original()

    starter.shutdown = shutdown  # type: ignore[method-assign]
    assembly = _build(starter, MemoryConversations(), MemoryQueue())
    chat = cast(ChatService, assembly.port(CHAT_CONVERSATIONS))
    stop_dispatch, aclose = chat.stop_dispatch, chat.aclose

    def rec_stop() -> None:
        order.append("chat.stop_dispatch")
        stop_dispatch()

    async def rec_close() -> None:
        order.append("chat.aclose")
        await aclose()

    chat.stop_dispatch = rec_stop  # type: ignore[method-assign]
    chat.aclose = rec_close  # type: ignore[method-assign]
    await assembly.start()
    conv = chat.create(CreateConversationRequest(graph_id="team"))
    run = await chat.post_message(conv.id, PostMessageRequest(text="a"))
    assert isinstance(run, Run)
    await assembly.stop()
    assert order == ["chat.stop_dispatch", "runs.starter.shutdown", "chat.aclose"]


@pytest.mark.parametrize(
    ("mode", "expect_started", "expect_queue"),
    [
        ("run", 1, []),
        ("drop", 0, []),
        ("ask", 0, [("남음", True)]),
    ],
)
async def test_restart_policy_through_link(
    mode: str, expect_started: int, expect_queue: list[tuple[str, bool]]
) -> None:
    conversations, queue = MemoryConversations(), MemoryQueue()
    first = _build(LocalRunStarter(), conversations, queue, mode)
    chat = cast(ChatService, first.port(CHAT_CONVERSATIONS))
    await first.start()
    conv = chat.create(CreateConversationRequest(graph_id="team"))
    await chat.post_message(conv.id, PostMessageRequest(text="실행"))
    queued = await chat.post_message(conv.id, PostMessageRequest(text="남음"))
    assert isinstance(queued, QueuedMessage)
    await first.stop()

    starter = LocalRunStarter()
    again = _build(starter, conversations, queue, mode)
    chat2 = cast(ChatService, again.port(CHAT_CONVERSATIONS))
    await again.start()
    try:
        assert len(starter.calls) == expect_started
        assert [(q.text, q.held) for q in chat2.queue(conv.id)] == expect_queue
    finally:
        await again.stop()


def _can_send(chat: ChatService) -> bool:
    return chat.can_send


async def test_send_before_start_hook_is_unavailable_then_connect_twice_is_idempotent() -> None:
    starter = LocalRunStarter()
    assembly = _build(starter, MemoryConversations(), MemoryQueue())
    chat = cast(ChatService, assembly.port(CHAT_CONVERSATIONS))
    conv = chat.create(CreateConversationRequest(graph_id="team"))
    assert not _can_send(chat)  # 시작 훅 전: 전송 불가(대기열에도 넣지 않는다)

    with pytest.raises(ChatFeatureUnavailableError):
        await chat.post_message(conv.id, PostMessageRequest(text="일찍"))
    assert chat.queue(conv.id) == []
    await assembly.start()
    try:
        assert _can_send(chat)
        run = await chat.post_message(conv.id, PostMessageRequest(text="이제"))
        assert isinstance(run, Run)
        # 두 번째 connect: 같은 포트로 다시 붙여도 진행 중 턴·전송이 유지된다
        launcher = assembly.port(CHAT_TURN_LAUNCHER)
        chat.connect(launcher=launcher, runs=starter.runs, events=starter.events)
        assert _can_send(chat)
        starter.finish(run.id)
        await chat.wait_idle(conv.id)
        assert [t.status for t in chat.turns(conv.id)] == ["completed"]
    finally:
        await assembly.stop()
