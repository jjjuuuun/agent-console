"""실행 연결이 선택일 때(3R.14): 없으면 전송만 꺼지고 대화·대기열은 동작한다."""

import pytest

from agent_console_chat import (
    LAUNCHER_DEPENDENCY,
    RUNS_DEPENDENCY,
    ChatFeatureUnavailableError,
    ChatService,
    ConversationNotFoundError,
    MemoryQueue,
    TurnNotFoundError,
    layered_chat_settings,
)
from agent_console_chat.testing import (
    FakeLauncher,
    MemoryConversations,
    MemoryEvents,
    MemoryGraphs,
    MemoryInteractions,
    MemoryRuns,
)
from agent_console_contracts import (
    ChatSettings,
    ConversationSummary,
    CreateConversationRequest,
    ErrorCodes,
    Graph,
    NodeSpec,
    PostMessageRequest,
    Run,
    UpdateConversationRequest,
)


def _graphs() -> MemoryGraphs:
    return MemoryGraphs([Graph(id="team", name="팀", nodes=[NodeSpec(id="pl", type="agent")])])


def _bare(**kwargs: object) -> tuple[ChatService, list[ConversationSummary]]:
    notified: list[ConversationSummary] = []
    service = ChatService(
        MemoryConversations(),
        _graphs(),
        listener=notified.append,
        **kwargs,  # type: ignore[arg-type]
    )
    return service, notified


async def test_without_launcher_conversations_work_and_send_is_unavailable() -> None:
    chat, notified = _bare()
    assert not chat.can_send
    conv = chat.create(CreateConversationRequest(graph_id="team", title="t"))
    assert [c.id for c in chat.list()] == [conv.id]
    assert chat.get(conv.id).title == "t"
    renamed = chat.update(conv.id, UpdateConversationRequest(title="새 이름", archived=True))
    assert renamed.title == "새 이름"
    summary = chat.summary(conv.id)
    assert (summary.last_status, summary.pending_interactions, summary.queued) == (None, 0, 0)
    assert chat.turns(conv.id) == []
    assert chat.queue(conv.id) == []
    assert notified  # 요약 알림은 그대로

    with pytest.raises(ChatFeatureUnavailableError) as caught:
        await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
    assert caught.value.code == ErrorCodes.FEATURE_UNAVAILABLE
    assert caught.value.dependency == LAUNCHER_DEPENDENCY
    assert caught.value.details == {"dependency": LAUNCHER_DEPENDENCY}
    assert chat.queue(conv.id) == []  # 대기열에도 넣지 않는다

    chat.delete(conv.id)
    with pytest.raises(ConversationNotFoundError):
        chat.get(conv.id)


async def test_unknown_conversation_is_not_found_before_unavailable() -> None:
    chat, _ = _bare()
    with pytest.raises(ConversationNotFoundError):
        await chat.post_message("nope", PostMessageRequest(text="x"))


async def test_resume_and_turn_without_links() -> None:
    chat, _ = _bare()
    with pytest.raises(ChatFeatureUnavailableError) as caught:
        await chat.resume_turn("r1", graph=Graph(id="team", name="팀"), seed={})
    assert caught.value.dependency == LAUNCHER_DEPENDENCY
    with pytest.raises(TurnNotFoundError):
        chat.turn("r1")

    runs = MemoryRuns()
    launcher_only, _ = _bare(launcher=FakeLauncher(runs, MemoryEvents()))
    with pytest.raises(ChatFeatureUnavailableError) as caught:
        await launcher_only.resume_turn("r1", graph=Graph(id="team", name="팀"), seed={})
    assert caught.value.dependency == RUNS_DEPENDENCY


async def test_queue_is_kept_until_launcher_connects() -> None:
    """재시작 정책 `run`이어도 실행기가 없으면 항목을 꺼내지(버리지) 않는다. 연결 뒤 흐른다."""
    queue = MemoryQueue()
    conversations = MemoryConversations()
    graphs = _graphs()
    settings = layered_chat_settings(ChatSettings(queue_after_restart="run"))
    first = ChatService(conversations, graphs, settings=settings, queue=queue)
    conv = first.create(CreateConversationRequest(graph_id="team"))
    queue.enqueue("q1", conv.id, "남은 메시지", created_at=1.0)

    applied = await first.apply_restart_policy()
    assert applied == {conv.id: "run"}
    assert [q.text for q in first.queue(conv.id)] == ["남은 메시지"]

    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    first.connect(launcher=launcher, runs=runs, events=events, interactions=MemoryInteractions())
    assert first.can_send
    await first.apply_restart_policy()
    started = await launcher.wait_started(1)
    assert first.queue(conv.id) == []
    launcher.finish(started.run_id)
    await first.wait_idle(conv.id)
    turns = first.turns(conv.id)
    assert [(t.user_text, t.status) for t in turns] == [("남은 메시지", "completed")]


async def test_connect_none_turns_send_off_again() -> None:
    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    chat, _ = _bare(launcher=launcher, runs=runs, events=events)
    conv = chat.create(CreateConversationRequest(graph_id="team"))
    run = await chat.post_message(conv.id, PostMessageRequest(text="하나"))
    assert isinstance(run, Run)
    launcher.finish(run.id)
    await chat.wait_idle(conv.id)
    chat.connect()
    assert not chat.can_send
    assert chat.turns(conv.id) == []
    with pytest.raises(ChatFeatureUnavailableError):
        await chat.post_message(conv.id, PostMessageRequest(text="둘"))
