"""link-chat-runs: 턴 시작·이어 가기·실행 이벤트 알림·재시작 대기열 정책·종료 순서(3R.14)."""

from __future__ import annotations

from typing import Any, cast

from agent_console_chat import ChatService, MemoryQueue, TurnStart
from agent_console_chat.testing import MemoryConversations
from agent_console_contracts import (
    ConversationSummary,
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    QueuedMessage,
    Run,
    RunEvent,
    SessionRef,
)
from agent_console_link_chat_runs import (
    CHAT_CONVERSATIONS,
    CHAT_INTERACTIONS,
    CHAT_TURN_LAUNCHER,
    RESUME_HANDLERS,
    RUNS_EVENT,
    ChatLike,
    ConversationNotifier,
    ConversationResume,
    RootInteractions,
    RunStarter,
    RuntimeTurnLauncher,
    module,
)
from agent_console_link_chat_runs.testing import (
    LocalRunStarter,
    local_chat_module,
    local_runs_module,
)
from agent_console_modkit import Assembly, assemble
from agent_console_nodes_core import SESSIONS
from agent_console_runtime import ResumeStart

GRAPH = Graph(id="team", name="팀", nodes=[NodeSpec(id="pl", type="agent")])


def _event(run_id: str, type: str) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{type}", run_id=run_id, seq=1, ts=1.0, node_path=[], type=type
    )


def _assembly(
    starter: LocalRunStarter,
    *,
    conversations: MemoryConversations | None = None,
    queue: MemoryQueue | None = None,
    listener: Any = None,
) -> Assembly:
    return assemble(
        [
            module,
            local_chat_module(
                graphs=[GRAPH], conversations=conversations, queue=queue, listener=listener
            ),
            local_runs_module(starter=starter),
        ]
    )


# ---------------------------------------------------------------- 어댑터


async def test_turn_launcher_passes_sessions_as_node_service() -> None:
    starter = LocalRunStarter()
    launcher = RuntimeTurnLauncher(starter)
    sessions = {"pl": SessionRef(backend="fake-agent", session_id="s1", data={"k": 1})}
    handle = await launcher.start_turn(
        TurnStart(
            conversation_id="c1",
            graph=GRAPH,
            input={"text": "hi"},
            text="hi",
            sessions=sessions,
            origin="chat",
            resumed_from="r0",
        )
    )
    call = starter.calls[0]
    assert (call["conversation_id"], call["origin"], call["resumed_from"]) == ("c1", "chat", "r0")
    engine_sessions = call["extra_services"][SESSIONS]
    assert engine_sessions["pl"].session_id == "s1"
    assert engine_sessions["pl"].data == {"k": 1}
    assert launcher.cancel(handle.run_id, "stop") is True
    assert launcher.cancel(handle.run_id, "stop") is False

    await launcher.start_turn(TurnStart(conversation_id="c1", graph=GRAPH, input={}, text=""))
    assert starter.calls[1]["extra_services"] == {}  # 세션이 없으면 노드 서비스를 더하지 않는다


async def test_conversation_resume_accepts_only_chat_turns() -> None:
    calls: list[tuple[str, Any]] = []

    class Chat:
        async def resume_turn(self, run_id: str, *, graph: Graph, seed: Any) -> Run:
            calls.append((run_id, seed))
            return Run(
                id="new",
                graph_id=graph.id,
                graph_version="v",
                status="running",
                input={},
                origin="resume",
                created_at=1.0,
            )

    chat: Any = Chat()
    handler = ConversationResume(lambda: chat)
    turn = Run(
        id="r1",
        graph_id="team",
        graph_version="v",
        status="interrupted",
        input={},
        origin="chat",
        conversation_id="c1",
        created_at=1.0,
    )
    plain = turn.model_copy(update={"conversation_id": None})
    assert handler.accepts(turn)
    assert not handler.accepts(plain)
    assert not ConversationResume(lambda: None).accepts(turn)
    result = await handler.resume(ResumeStart(run=turn, graph=GRAPH, seed={"pl": {"x": 1}}))
    assert result.id == "new"
    assert calls == [("r1", {"pl": {"x": 1}})]


async def test_notifier_filters_events_and_non_chat_runs() -> None:
    notified: list[str] = []

    class Chat:
        def notify(self, conversation_id: str) -> None:
            notified.append(conversation_id)

    starter = LocalRunStarter()
    chat_run = await starter.start_run(GRAPH, {}, conversation_id="c1")
    plain_run = await starter.start_run(GRAPH, {})
    notifier = ConversationNotifier(Chat(), starter)  # type: ignore[arg-type]
    notifier(_event(chat_run.run_id, "interaction.requested"))
    notifier(_event(chat_run.run_id, "run.waiting"))
    notifier(_event(chat_run.run_id, "node.started"))  # 무관한 이벤트
    notifier(_event(plain_run.run_id, "interaction.requested"))  # 대화 턴 아님
    notifier(_event("missing", "run.resumed"))
    assert notified == ["c1", "c1"]


async def test_notifier_sends_child_run_events_to_root_conversation() -> None:
    """자식 Run(중첩 팀)은 ``conversation_id``가 없다 → 루트 Run의 대화로 알린다(5R.13)."""
    notified: list[str] = []

    class Chat:
        def notify(self, conversation_id: str) -> None:
            notified.append(conversation_id)

    starter = LocalRunStarter()
    root = await starter.start_run(GRAPH, {}, conversation_id="c1")
    child = root.run.model_copy(
        update={
            "id": "child",
            "conversation_id": None,
            "parent_run_id": root.run_id,
            "root_run_id": root.run_id,
        }
    )
    orphan = child.model_copy(update={"id": "orphan", "root_run_id": "gone"})
    starter.runs.save(child)
    starter.runs.save(orphan)
    notifier = ConversationNotifier(Chat(), starter)  # type: ignore[arg-type]
    notifier(_event("child", "interaction.requested"))
    notifier(_event("child", "run.waiting"))
    notifier(_event("orphan", "interaction.requested"))  # 루트가 없으면 알리지 않는다
    assert notified == ["c1", "c1"]


def test_root_interactions_collect_turn_by_root_run() -> None:
    calls: list[dict[str, Any]] = []

    class Source:
        def list(self, **kwargs: Any) -> list[Any]:
            calls.append(kwargs)
            return []

    reader = RootInteractions(Source())
    reader.list(run_id="r1")
    reader.list(conversation_id="c1", status="pending")
    assert calls == [
        {"root_run_id": "r1", "conversation_id": None, "status": None},
        {"root_run_id": None, "conversation_id": "c1", "status": "pending"},
    ]


# ---------------------------------------------------------------- 모듈


async def test_module_connects_chat_to_runs() -> None:
    starter = LocalRunStarter()
    notified: list[ConversationSummary] = []
    assembly = _assembly(starter, listener=notified.append)
    assert [(r.id, r.state.value) for r in assembly.report] == [
        ("link-chat-runs", "active"),
        ("local-chat", "active"),
        ("local-runs", "active"),
    ]
    assert assembly.order.index("local-chat") < assembly.order.index("link-chat-runs")
    assert isinstance(assembly.port(CHAT_TURN_LAUNCHER), RuntimeTurnLauncher)
    assert assembly.port(CHAT_INTERACTIONS) is None  # interactions.port가 없으면 주지 않는다
    [handler] = assembly.ports(RESUME_HANDLERS)
    assert isinstance(handler, ConversationResume)

    chat = cast(ChatService, assembly.port(CHAT_CONVERSATIONS))
    await assembly.start()
    try:
        assert chat.can_send
        conv = chat.create(CreateConversationRequest(graph_id="team"))
        run = await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
        assert isinstance(run, Run)
        assert starter.calls[0]["conversation_id"] == conv.id
        # runs.event 구독 → 대화 알림(요약 리스너)
        notified.clear()
        assembly.services.events.publish(RUNS_EVENT, _event(run.id, "interaction.requested"))
        await assembly.services.events.drain()
        assert [s.id for s in notified] == [conv.id]
        starter.finish(run.id)
        await chat.wait_idle(conv.id)
        assert [t.status for t in chat.turns(conv.id)] == ["completed"]
    finally:
        await assembly.stop()


async def test_shutdown_stops_dispatch_before_runs_are_interrupted() -> None:
    """종료: 대기열 꺼내기 멈춤 → 실행 정리. 끊긴 턴 뒤에 대기열을 꺼내지 않는다."""
    starter = LocalRunStarter()
    queue = MemoryQueue()
    conversations = MemoryConversations()
    assembly = _assembly(starter, conversations=conversations, queue=queue)
    chat = cast(ChatService, assembly.port(CHAT_CONVERSATIONS))
    await assembly.start()
    conv = chat.create(CreateConversationRequest(graph_id="team"))
    first = await chat.post_message(conv.id, PostMessageRequest(text="하나"))
    queued = await chat.post_message(conv.id, PostMessageRequest(text="둘"))
    assert isinstance(first, Run)
    assert isinstance(queued, QueuedMessage)
    await assembly.stop()
    assert starter.shutdowns == 1
    assert starter.current_run(first.id).status == "interrupted"  # type: ignore[union-attr]
    assert len(starter.calls) == 1  # 끊긴 턴 뒤에 "둘"을 시작하지 않았다
    assert [item.text for item in queue.list(conv.id)] == ["둘"]

    # 재시작: 기본 정책(ask)이면 남은 항목을 멈춰 둔다(연동의 시작 훅)
    again = LocalRunStarter()
    restarted = _assembly(again, conversations=conversations, queue=queue)
    chat2 = cast(ChatService, restarted.port(CHAT_CONVERSATIONS))
    await restarted.start()
    try:
        assert [(q.text, q.held) for q in chat2.queue(conv.id)] == [("둘", True)]
        assert again.calls == []
    finally:
        await restarted.stop()


async def test_without_link_chat_cannot_send() -> None:
    assembly = assemble([local_chat_module(graphs=[GRAPH]), local_runs_module()])
    chat = cast(ChatService, assembly.port(CHAT_CONVERSATIONS))
    await assembly.start()
    try:
        assert not chat.can_send
    finally:
        await assembly.stop()


def test_module_unsatisfied_without_chat_or_runs() -> None:
    report = {r.id: r for r in assemble([module, local_runs_module()]).report}
    assert report["link-chat-runs"].state.value == "unsatisfied"
    assert "chat.conversations" in report["link-chat-runs"].missing
    report = {r.id: r for r in assemble([module, local_chat_module()]).report}
    assert set(report["link-chat-runs"].missing) == {"runs.starter", "runs.reader", "runs.events"}


def test_testing_fakes_satisfy_consumer_protocols() -> None:
    assert isinstance(LocalRunStarter(), RunStarter)
    assert isinstance(ChatService(MemoryConversations(), _NoGraphs()), ChatLike)


class _NoGraphs:
    def get_graph(self, graph_id: str) -> Graph | None:
        return None
