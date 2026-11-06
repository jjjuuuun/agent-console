"""5.7R.33y3: 세션 이어 가기 상태(`session_states`)·보내기 전 점검(409·fresh)·복원 안내."""

from __future__ import annotations

import pytest

from agent_console_chat import (
    FRESH_SESSION_NOTE,
    ChatService,
    SessionContinuity,
    SessionUnavailableError,
)
from agent_console_chat.testing import (
    FakeLauncher,
    MemoryContinuity,
    MemoryConversations,
    MemoryEvents,
    MemoryGraphs,
    MemoryRuns,
)
from agent_console_contracts import (
    CreateConversationRequest,
    ErrorCodes,
    Graph,
    NodeSpec,
    PostMessageRequest,
    QueuedMessage,
    Run,
    SessionRef,
)

A = SessionRef(backend="fake-agent", session_id="sa")
B = SessionRef(backend="fake-agent", session_id="sb")


def _service(
    continuity: SessionContinuity | None,
) -> tuple[ChatService, FakeLauncher, MemoryConversations]:
    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    conversations = MemoryConversations()
    graph = Graph(id="g", name="g", nodes=[NodeSpec(id=n, type="agent") for n in ("a", "b")])
    service = ChatService(
        conversations,
        MemoryGraphs([graph]),
        launcher=launcher,
        runs=runs,
        events=events,
        continuity=continuity,
    )
    return service, launcher, conversations


def _conversation(service: ChatService, conversations: MemoryConversations) -> str:
    conv = service.create(CreateConversationRequest(graph_id="g", project_id="p1"))
    conversations.save(conv.model_copy(update={"sessions": {"a": A, "b": B}}))
    return conv.id


def test_without_continuity_everything_not_applicable() -> None:
    service, _, conversations = _service(None)
    cid = _conversation(service, conversations)
    states = service.session_states(cid)
    assert states.continuable is True
    assert [(i.node_id, i.state) for i in states.items] == [
        ("a", "not_applicable"),
        ("b", "not_applicable"),
    ]


async def test_missing_session_rejects_send_with_details() -> None:
    continuity = MemoryContinuity({"sb": "missing"})
    service, launcher, conversations = _service(continuity)
    cid = _conversation(service, conversations)
    states = service.session_states(cid)
    assert states.continuable is False
    assert {i.node_id: i.state for i in states.items} == {"a": "available", "b": "missing"}
    with pytest.raises(SessionUnavailableError) as caught:
        await service.post_message(cid, PostMessageRequest(text="hi"))
    assert caught.value.code == ErrorCodes.CHAT_SESSION_UNAVAILABLE
    assert caught.value.details == {"conversation_id": cid, "node_ids": ["b"]}
    assert launcher.started == []
    assert service.get(cid).sessions == {"a": A, "b": B}  # 거절은 아무것도 바꾸지 않는다


async def test_fresh_drops_missing_node_only_and_notes_it() -> None:
    continuity = MemoryContinuity({"sb": "missing"})
    service, launcher, conversations = _service(continuity)
    cid = _conversation(service, conversations)
    run = await service.post_message(cid, PostMessageRequest(text="hi", on_missing_session="fresh"))
    assert isinstance(run, Run)
    turn = launcher.started[0]
    assert turn.sessions == {"a": A}
    assert dict(turn.session_notes) == {"b": FRESH_SESSION_NOTE}
    assert service.get(cid).sessions == {"a": A}
    assert service.session_states(cid).continuable is True
    launcher.finish(run.id)
    await service.wait_idle()


async def test_archived_session_is_restored_before_start_and_noted() -> None:
    continuity = MemoryContinuity({"sa": "archived", "sb": "relocatable"})
    service, launcher, conversations = _service(continuity)
    cid = _conversation(service, conversations)
    assert service.session_states(cid).continuable is True
    run = await service.post_message(cid, PostMessageRequest(text="hi"))
    assert isinstance(run, Run)
    turn = launcher.started[0]
    assert turn.sessions == {"a": A, "b": B}
    assert dict(turn.session_notes) == {"a": "archived", "b": "relocatable"}
    assert sorted(continuity.prepared) == [("p1", "sa"), ("p1", "sb")]
    launcher.finish(run.id)
    await service.wait_idle()
    # 다음 턴은 평소대로(안내 없음)
    run2 = await service.post_message(cid, PostMessageRequest(text="again"))
    assert isinstance(run2, Run)
    assert dict(launcher.started[1].session_notes) == {}
    launcher.finish(run2.id)
    await service.wait_idle()


async def test_restore_failure_at_start_falls_back_to_fresh() -> None:
    """점검 뒤 시작 직전에 복원하지 못하면(대기열에서 꺼낸 턴 등) 메시지를 버리지 않고 새 세션."""

    class Flaky(MemoryContinuity):
        def prepare(self, project_id: str | None, session: SessionRef) -> str:
            return "missing" if session.session_id == "sa" else "available"

    service, launcher, conversations = _service(Flaky({"sa": "archived"}))
    cid = _conversation(service, conversations)
    run = await service.post_message(cid, PostMessageRequest(text="hi"))
    assert isinstance(run, Run)
    assert launcher.started[0].sessions == {"b": B}
    assert dict(launcher.started[0].session_notes) == {"a": FRESH_SESSION_NOTE}
    assert service.get(cid).sessions == {"b": B}
    launcher.finish(run.id)
    await service.wait_idle()


async def test_missing_check_happens_before_queueing() -> None:
    continuity = MemoryContinuity()
    service, launcher, conversations = _service(continuity)
    cid = _conversation(service, conversations)
    first = await service.post_message(cid, PostMessageRequest(text="one"))
    assert isinstance(first, Run)
    continuity.states["sb"] = "missing"
    with pytest.raises(SessionUnavailableError):
        await service.post_message(cid, PostMessageRequest(text="two"))
    queued = await service.post_message(
        cid, PostMessageRequest(text="two", on_missing_session="fresh")
    )
    assert isinstance(queued, QueuedMessage)
    launcher.finish(first.id)
    second = await launcher.wait_started(2)
    assert launcher.started[1].sessions == {"a": A}
    launcher.finish(second.run_id)
    await service.wait_idle()


def test_state_errors_do_not_block() -> None:
    class Broken(MemoryContinuity):
        def state(self, project_id: str | None, session: SessionRef) -> str:
            raise RuntimeError("boom")

    service, _, conversations = _service(Broken())
    cid = _conversation(service, conversations)
    states = service.session_states(cid)
    assert states.continuable is True
    assert {i.state for i in states.items} == {"not_applicable"}
