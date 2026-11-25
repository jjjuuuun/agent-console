"""턴 마무리 순서(5.2R.39): 답변·세션 기록 → 끝난 상태 공개 → 알림.

- Run이 끝났어도 대화가 세션을 기록하기 전에는 턴·요약이 끝난 상태를 보이지 않는다(`running`).
- 끝난 상태를 처음 싣는 대화 알림은 세션 기록 뒤에 나간다.
"""

from collections.abc import Iterable, Mapping

from agent_console_chat import ChatService
from agent_console_chat.testing import (
    FakeLauncher,
    MemoryConversations,
    MemoryEvents,
    MemoryGraphs,
    MemoryRuns,
)
from agent_console_contracts import (
    ConversationSummary,
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    QueuedMessage,
    Run,
    SessionRef,
)

REF = SessionRef(backend="fake-agent", session_id="s")


class SpyRules:
    """세션 수집 시점에 대화가 바깥에 보이는 턴·요약 상태를 기록하는 규칙."""

    def __init__(self) -> None:
        self.service: ChatService | None = None
        self.seen: list[tuple[str, str | None]] = []

    def collect(self, run: Run) -> dict[str, SessionRef]:
        assert self.service is not None
        assert run.conversation_id is not None
        [turn] = self.service.turns(run.conversation_id)
        summary = self.service.summary(run.conversation_id)
        self.seen.append((turn.status, summary.last_status))
        return {"pl": REF}

    def prune(
        self, sessions: Mapping[str, SessionRef], node_ids: Iterable[str]
    ) -> dict[str, SessionRef]:
        return dict(sessions)


async def test_turn_shows_closed_status_only_after_sessions_recorded() -> None:
    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    rules = SpyRules()
    conversations = MemoryConversations()
    notes: list[tuple[str | None, dict[str, SessionRef]]] = []

    def listener(summary: ConversationSummary) -> None:
        stored = conversations.get(summary.id)
        notes.append((summary.last_status, dict(stored.sessions) if stored else {}))

    service = ChatService(
        conversations,
        MemoryGraphs([Graph(id="g", name="g", nodes=[NodeSpec(id="pl", type="agent")])]),
        launcher=launcher,
        runs=runs,
        events=events,
        sessions=rules,
        listener=listener,
    )
    rules.service = service
    conv = service.create(CreateConversationRequest(graph_id="g"))
    run = await service.post_message(conv.id, PostMessageRequest(text="하나"))
    assert isinstance(run, Run)

    launcher.finish(run.id)  # Run은 끝났지만 대화 마무리(감시 태스크)는 아직
    [turn] = service.turns(conv.id)
    assert (turn.status, turn.ended_at) == ("running", None)
    assert service.summary(conv.id).last_status == "running"
    assert service.is_busy(conv.id)

    await service.wait_idle()
    assert rules.seen == [("running", "running")]  # 세션 기록 중에도 끝난 상태는 숨김
    [turn] = service.turns(conv.id)
    assert turn.status == "completed"
    assert turn.ended_at is not None
    assert service.summary(conv.id).last_status == "completed"
    closed = [sessions for status, sessions in notes if status == "completed"]
    assert closed  # 끝난 상태 알림은 세션 기록 뒤
    assert closed[0] == {"pl": REF}


async def test_message_during_closing_is_queued_then_starts_as_new_run() -> None:
    """Run이 끝났어도 마무리 전에 온 메시지는 대기열 응답(id는 Run id가 아니다)이고, 마무리
    뒤 새 Run으로 시작된다(REL.33 — 화면이 끝남을 본 직후 보내면 이 창에 든다)."""
    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    service = ChatService(
        MemoryConversations(),
        MemoryGraphs([Graph(id="g", name="g", nodes=[NodeSpec(id="pl", type="agent")])]),
        launcher=launcher,
        runs=runs,
        events=events,
    )
    conv = service.create(CreateConversationRequest(graph_id="g"))
    first = await service.post_message(conv.id, PostMessageRequest(text="하나"))
    assert isinstance(first, Run)

    launcher.finish(first.id)  # 실행 기록은 끝났고 대화 마무리는 아직
    done = runs.get(first.id)
    assert done is not None
    assert done.status == "completed"
    sent = await service.post_message(conv.id, PostMessageRequest(text="둘"))
    assert isinstance(sent, QueuedMessage)
    assert runs.get(sent.id or "") is None  # 대기열 항목 id로는 Run을 읽을 수 없다

    second = await launcher.wait_started(2)
    assert second.run_id != sent.id
    assert service.get(conv.id).last_run_id == second.run_id
    assert service.queue(conv.id) == []
    launcher.finish(second.run_id)
    await service.wait_idle()
    [_, turn] = service.turns(conv.id)
    assert (turn.user_text, turn.status) == ("둘", "completed")
