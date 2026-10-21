"""저장 대기열(`QueueStore`)·재시작 뒤 처리(`chat.queue_after_restart`)·끊긴 턴 이어 가기(2R.14).

재시작은 같은 대기열·대화·Run 저장소를 공유하는 **새** `ChatService`로 흉내 낸다(서버가 SQLite
저장소를 다시 열 때와 같다).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_console_chat import (
    RESTART_HOLD_REASON,
    ChatOptions,
    ChatService,
    ConversationBusyError,
    MemoryQueue,
    QueuedMessageNotFoundError,
    TurnNotFoundError,
    TurnNotResumableError,
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
    GraphSettings,
    NodeSpec,
    PostMessageRequest,
    QueuedMessage,
    Run,
)


def _graph(graph_id: str = "team", chat: ChatSettings | None = None) -> Graph:
    return Graph(
        id=graph_id,
        name=graph_id,
        nodes=[NodeSpec(id="pl", type="agent"), NodeSpec(id="rv", type="user")],
        settings=GraphSettings(chat=chat) if chat is not None else None,
    )


@dataclass
class World:
    """재시작해도 남는 것(저장소)."""

    graphs: MemoryGraphs
    common: ChatSettings
    queue: MemoryQueue = field(default_factory=MemoryQueue)
    conversations: MemoryConversations = field(default_factory=MemoryConversations)
    runs: MemoryRuns = field(default_factory=MemoryRuns)
    events: MemoryEvents = field(default_factory=MemoryEvents)
    interactions: MemoryInteractions = field(default_factory=MemoryInteractions)
    n: int = 0
    boots: int = 0

    def ids(self) -> str:
        self.n += 1
        return f"id-{self.n}"

    def boot(self) -> tuple[ChatService, FakeLauncher, list[ConversationSummary]]:
        """서버 프로세스 하나(메모리 상태는 새로)."""
        self.boots += 1
        launcher = FakeLauncher(
            self.runs, self.events, clock=lambda: float(self.n), run_prefix=f"p{self.boots}-run-"
        )
        notified: list[ConversationSummary] = []
        service = ChatService(
            self.conversations,
            self.graphs,
            launcher=launcher,
            runs=self.runs,
            events=self.events,
            interactions=self.interactions,
            settings=layered_chat_settings(lambda: self.common),
            listener=notified.append,
            ids=self.ids,
            options=ChatOptions(),
            queue=self.queue,
        )
        return service, launcher, notified


def _world(*graphs: Graph, **common: Any) -> World:
    return World(MemoryGraphs(graphs or [_graph()]), ChatSettings(**common))


async def _post(service: ChatService, conv: str, text: str) -> Run | QueuedMessage:
    return await service.post_message(conv, PostMessageRequest(text=text))


async def _before_restart(world: World) -> tuple[str, Run]:
    """첫 프로세스: 턴 하나 실행 중 + 대기열 2건을 남기고 '죽는다'."""
    service, _, _ = world.boot()
    conv = service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(service, conv.id, "하나")
    assert isinstance(run, Run)
    assert isinstance(await _post(service, conv.id, "둘"), QueuedMessage)
    assert isinstance(await _post(service, conv.id, "셋"), QueuedMessage)
    await service.aclose()  # 대기열은 저장소에 남는다
    # 재시작 복구가 끝나지 않은 Run을 interrupted로 바꾼 상태
    world.runs.save(run.model_copy(update={"status": "interrupted"}))
    return conv.id, run


# ---------------------------------------------------------------- MemoryQueue


def test_memory_queue_held_head_blocks_and_positions_renumber() -> None:
    q = MemoryQueue()
    q.enqueue("a", "c", "1", created_at=1.0)
    q.enqueue("b", "c", "2", created_at=2.0)
    q.enqueue("x", "other", "9", created_at=3.0)
    assert q.hold_all("restart", conversation_id="c") == 2
    assert q.pop_next("c") is None  # 맨 앞이 멈춤 → 뒤도 막힌다
    assert q.counts(["c"])["c"].held == 2
    q.release("b")
    assert q.pop_next("c") is None
    assert q.remove("a")
    [b] = q.list("c")
    assert (b.id, b.position, b.held) == ("b", 1, False)
    popped = q.pop_next("c")
    assert popped is not None
    assert popped.id == "b"
    assert set(q.counts()) == {"other"}
    assert q.clear("other") == 1
    assert q.list() == []
    q.enqueue("x2", "c", "a", created_at=0.0)
    with pytest.raises(ValueError, match="이미"):
        q.enqueue("x2", "c", "a", created_at=0.0)


# ---------------------------------------------------------------- 재시작 뒤 처리


async def test_restart_ask_holds_items_and_release_runs_them_in_order() -> None:
    world = _world()
    conv, _ = await _before_restart(world)
    service, launcher, notified = world.boot()
    assert await service.apply_restart_policy() == {conv: "ask"}
    queue = service.queue(conv)
    assert [(q.text, q.position, q.held) for q in queue] == [("둘", 1, True), ("셋", 2, True)]
    assert all(i.held_reason == RESTART_HOLD_REASON for i in world.queue.list(conv))
    summary = service.summary(conv)
    assert (summary.queued, summary.held) == (2, 2)
    assert notified[-1].held == 2
    assert launcher.started == []  # 자동 실행하지 않는다

    # 새 메시지는 멈춘 항목 뒤에 선다(순서 보존)
    later = await _post(service, conv, "넷")
    assert isinstance(later, QueuedMessage)
    assert (later.position, later.held) == (3, False)
    assert launcher.started == []

    # 두 번째를 먼저 풀어도 맨 앞이 멈춰 있으면 기다린다
    second = await service.release_queued(conv, queue[1].id or "")
    assert second.held is False
    assert launcher.started == []
    # 맨 앞을 풀면 곧바로 실행
    await service.release_queued(conv, queue[0].id or "")
    assert [t.text for t in launcher.started] == ["둘"]
    assert [q.text for q in service.queue(conv)] == ["셋", "넷"]
    run2 = next(iter(launcher.handles))
    launcher.finish(run2)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert [t.text for t in launcher.started] == ["둘", "셋"]


async def test_restart_run_mode_starts_first_item() -> None:
    world = _world(queue_after_restart="run")
    conv, _ = await _before_restart(world)
    service, launcher, _ = world.boot()
    assert await service.apply_restart_policy() == {conv: "run"}
    assert [t.text for t in launcher.started] == ["둘"]
    assert [q.text for q in service.queue(conv)] == ["셋"]
    assert service.summary(conv).held == 0


async def test_restart_drop_mode_clears_queue() -> None:
    world = _world(queue_after_restart="drop")
    conv, _ = await _before_restart(world)
    service, launcher, _ = world.boot()
    await service.apply_restart_policy()
    assert service.queue(conv) == []
    assert launcher.started == []
    assert service.summary(conv).queued == 0


async def test_restart_mode_follows_team_layer() -> None:
    world = _world(_graph(chat=ChatSettings.model_validate({"queue_after_restart": "drop"})))
    conv, _ = await _before_restart(world)  # 공통 설정은 기본(ask)
    service, _, _ = world.boot()
    assert await service.apply_restart_policy() == {conv: "drop"}
    assert service.queue(conv) == []


async def test_restart_drops_items_of_deleted_conversation() -> None:
    world = _world()
    conv, _ = await _before_restart(world)
    world.conversations.delete(conv)
    service, _, _ = world.boot()
    assert await service.apply_restart_policy() == {}
    assert world.queue.list() == []


async def test_cancel_held_head_lets_next_released_item_flow() -> None:
    world = _world()
    conv, _ = await _before_restart(world)
    service, launcher, _ = world.boot()
    await service.apply_restart_policy()
    first, second = service.queue(conv)
    await service.release_queued(conv, second.id or "")
    cancelled = service.cancel_queued(conv, first.id or "")
    assert (cancelled.position, cancelled.held) == (1, True)
    for _ in range(5):  # 지운 뒤 맨 앞을 실행하는 작업은 백그라운드에서 돈다
        await asyncio.sleep(0)
    assert [t.text for t in launcher.started] == ["셋"]


async def test_release_unknown_or_other_conversation_item_is_not_found() -> None:
    world = _world()
    conv, _ = await _before_restart(world)
    service, _, _ = world.boot()
    other = service.create(CreateConversationRequest(graph_id="team"))
    item = service.queue(conv)[0]
    with pytest.raises(QueuedMessageNotFoundError) as caught:
        await service.release_queued(other.id, item.id or "")
    assert caught.value.code == ErrorCodes.NOT_FOUND
    with pytest.raises(QueuedMessageNotFoundError):
        await service.release_queued(conv, "nope")


async def test_reject_policy_does_not_queue_behind_held_items() -> None:
    world = _world()
    conv, _ = await _before_restart(world)
    world.common = ChatSettings(busy_policy="reject")
    service, launcher, _ = world.boot()
    await service.apply_restart_policy()
    started = await _post(service, conv, "바로")
    assert isinstance(started, Run)
    assert [t.text for t in launcher.started] == ["바로"]
    with pytest.raises(ConversationBusyError):
        await _post(service, conv, "또")


# ---------------------------------------------------------------- 이어 가기


async def test_resume_turn_starts_new_run_in_same_conversation() -> None:
    world = _world(queue_after_restart="drop")
    conv, interrupted = await _before_restart(world)
    service, launcher, _ = world.boot()
    await service.apply_restart_policy()
    graph = _graph()
    resumed = await service.resume_turn(
        interrupted.id, graph=graph, seed={"rv": {"review": "설계안"}}
    )
    [turn] = launcher.started
    assert turn.seed == {"rv": {"review": "설계안"}}
    assert turn.resumed_from == interrupted.id
    assert turn.origin == "resume"
    assert turn.input == interrupted.input
    assert turn.conversation_id == conv
    assert resumed.resumed_from == interrupted.id
    assert service.get(conv).last_run_id == resumed.id
    turns = service.turns(conv)
    assert [t.resumed_from for t in turns] == [None, interrupted.id]
    assert turns[-1].user_text == "하나"

    with pytest.raises(ConversationBusyError):  # 실행 중에는 다시 이어 가지 않는다
        await service.resume_turn(interrupted.id, graph=graph, seed={"rv": {}})
    launcher.finish(resumed.id)
    await service.wait_idle(conv)
    with pytest.raises(TurnNotResumableError) as caught:  # 마지막 턴이 아니다
        await service.resume_turn(interrupted.id, graph=graph, seed={"rv": {}})
    assert caught.value.code == ErrorCodes.RUN_NOT_RESUMABLE


async def test_resume_turn_requires_conversation_turn() -> None:
    world = _world()
    service, _, _ = world.boot()
    world.runs.save(
        Run(
            id="api-run",
            graph_id="team",
            graph_version="v",
            status="interrupted",
            input={},
            origin="api",
            created_at=1.0,
        )
    )
    with pytest.raises(TurnNotFoundError):
        await service.resume_turn("api-run", graph=_graph(), seed={"pl": {}})
    with pytest.raises(TurnNotFoundError):
        await service.resume_turn("missing", graph=_graph(), seed={"pl": {}})
