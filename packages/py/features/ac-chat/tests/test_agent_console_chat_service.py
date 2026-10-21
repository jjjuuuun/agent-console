"""ChatService 단위 테스트(가짜 실행 엔진·인메모리 저장소)."""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from agent_console_chat import (
    ChatOptions,
    ChatService,
    ConversationBusyError,
    ConversationNotFoundError,
    GraphNotFoundError,
    InvalidMessageError,
    QueuedMessageNotFoundError,
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
    GraphSettings,
    Interaction,
    NodeSpec,
    PostMessageRequest,
    QueuedMessage,
    Run,
    RunEvent,
    SessionRef,
    UpdateConversationRequest,
)


def _graph(graph_id: str, node_ids: list[str], chat: ChatSettings | None = None) -> Graph:
    return Graph(
        id=graph_id,
        name=graph_id,
        nodes=[NodeSpec(id=n, type="agent") for n in node_ids],
        settings=GraphSettings(chat=chat) if chat is not None else None,
    )


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"id-{self.n}"


@dataclass
class Env:
    service: ChatService
    launcher: FakeLauncher
    conversations: MemoryConversations
    runs: MemoryRuns
    events: MemoryEvents
    interactions: MemoryInteractions
    graphs: MemoryGraphs
    notified: list[ConversationSummary]


def _env(*graphs: Graph, common: ChatSettings | None = None, **opts: Any) -> Env:
    clock = _Clock()
    conversations, runs, events = MemoryConversations(), MemoryRuns(), MemoryEvents()
    interactions, graph_lookup = MemoryInteractions(), MemoryGraphs(graphs)
    launcher = FakeLauncher(runs, events, clock=clock)
    notified: list[ConversationSummary] = []
    service = ChatService(
        conversations,
        graph_lookup,
        launcher=launcher,
        runs=runs,
        events=events,
        interactions=interactions,
        settings=layered_chat_settings(common),
        listener=notified.append,
        clock=clock,
        ids=_Ids(),
        options=ChatOptions(**opts),
    )
    return Env(service, launcher, conversations, runs, events, interactions, graph_lookup, notified)


def _event(run_id: str, seq: int, type: str, payload: dict[str, Any], **head: Any) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=float(seq),
        node_path=head.pop("node_path", []),
        type=type,
        payload=payload,
        **head,
    )


def _interaction(iid: str, run_id: str, conv: str, status: str, created: float) -> Interaction:
    return Interaction.model_validate(
        {
            "id": iid,
            "run_id": run_id,
            "conversation_id": conv,
            "node_id": "pl",
            "kind": "question",
            "status": status,
            "created_at": created,
        }
    )


async def _post(env: Env, conv: str, text: str) -> Run | QueuedMessage:
    return await env.service.post_message(conv, PostMessageRequest(text=text))


# ---------------------------------------------------------------- CRUD


def test_create_requires_existing_graph() -> None:
    env = _env(_graph("team", ["pl"]))
    with pytest.raises(GraphNotFoundError) as info:
        env.service.create(CreateConversationRequest(graph_id="nope"))
    assert info.value.code == ErrorCodes.NOT_FOUND
    conv = env.service.create(CreateConversationRequest(graph_id="team", title="  계획  "))
    assert conv.title == "계획"
    assert env.service.get(conv.id) == conv
    assert env.notified[-1].id == conv.id


def test_get_unknown_conversation() -> None:
    env = _env(_graph("team", ["pl"]))
    with pytest.raises(ConversationNotFoundError):
        env.service.get("missing")


def test_list_sorted_by_recent_update_and_filtered() -> None:
    env = _env(_graph("a", ["pl"]), _graph("b", ["pl"]))
    first = env.service.create(CreateConversationRequest(graph_id="a"))
    second = env.service.create(CreateConversationRequest(graph_id="b"))
    env.service.update(first.id, UpdateConversationRequest(archived=True))
    assert [s.id for s in env.service.list()] == [first.id, second.id]
    assert [s.id for s in env.service.list(graph_id="b")] == [second.id]
    assert [s.id for s in env.service.list(archived=False)] == [second.id]


async def test_project_id_is_stored_listed_and_passed_to_turns() -> None:
    """5.2R.32: 대화의 project_id는 요약·목록 거르기·턴 Run으로 이어진다(불투명 문자열)."""
    env = _env(_graph("a", ["pl"]))
    inside = env.service.create(CreateConversationRequest(graph_id="a", project_id="p1"))
    outside = env.service.create(CreateConversationRequest(graph_id="a"))
    assert (inside.project_id, outside.project_id) == ("p1", None)
    assert [s.id for s in env.service.list(project_id="p1")] == [inside.id]
    assert env.service.list(project_id="p1")[0].project_id == "p1"
    assert env.service.list(project_id="none") == []
    assert {s.id for s in env.service.list()} == {inside.id, outside.id}
    run = await _post(env, inside.id, "안녕")
    assert isinstance(run, Run)
    assert env.launcher.started[0].project_id == "p1"
    assert run.project_id == "p1"


# ---------------------------------------------------------------- 메시지 → 턴


async def test_post_message_starts_turn_with_message_input() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(env, conv.id, "안녕하세요")
    assert isinstance(run, Run)
    start = env.launcher.started[0]
    assert start.input == {"text": "안녕하세요"}
    assert start.origin == "chat"
    assert start.conversation_id == conv.id
    assert run.conversation_id == conv.id
    assert env.service.get(conv.id).last_run_id == run.id
    assert env.service.is_busy(conv.id)
    env.launcher.finish(run.id)
    await env.service.wait_idle()
    assert not env.service.is_busy(conv.id)
    assert env.service.summary(conv.id).last_status == "completed"


async def test_message_input_key_is_option() -> None:
    env = _env(_graph("team", ["pl"]), message_input_key="prompt", origin="chat-cli")
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    await _post(env, conv.id, "hi")
    assert env.launcher.started[0].input == {"prompt": "hi"}
    assert env.launcher.started[0].origin == "chat-cli"


async def test_empty_message_rejected() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    with pytest.raises(InvalidMessageError):
        await _post(env, conv.id, "  \n ")


async def test_title_from_first_message_default() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    text = "로그인   화면을\n만들어 주세요 " + "가" * 60
    run = await _post(env, conv.id, text)
    title = env.service.get(conv.id).title
    assert title.startswith("로그인 화면을 만들어 주세요")
    assert len(title) <= 40
    assert isinstance(run, Run)
    env.launcher.finish(run.id)
    await env.service.wait_idle()
    run2 = await _post(env, conv.id, "두 번째")
    assert env.service.get(conv.id).title == title  # 이미 있으면 바꾸지 않음
    assert isinstance(run2, Run)
    env.launcher.finish(run2.id)
    await env.service.wait_idle()


async def test_title_manual_policy_from_team_layer() -> None:
    env = _env(_graph("team", ["pl"], chat=ChatSettings(title="manual")))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    await _post(env, conv.id, "제목이 되면 안 됨")
    assert env.service.get(conv.id).title == ""


async def test_title_chars_option() -> None:
    env = _env(_graph("team", ["pl"]), title_chars=5)
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    await _post(env, conv.id, "abcdefghij")
    assert env.service.get(conv.id).title == "abcde"


async def test_start_failure_propagates_and_conversation_stays_idle() -> None:
    env = _env(_graph("team", ["pl"]))
    env.launcher.fail_with = ValueError("검증 실패")
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    with pytest.raises(ValueError, match="검증 실패"):
        await _post(env, conv.id, "hi")
    assert not env.service.is_busy(conv.id)


async def test_deleted_graph_on_post() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    del env.graphs.items["team"]
    with pytest.raises(GraphNotFoundError):
        await _post(env, conv.id, "hi")


# ---------------------------------------------------------------- 실행 중 메시지 정책


async def test_queue_policy_runs_messages_in_order() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    first = await _post(env, conv.id, "하나")
    second = await _post(env, conv.id, "둘")
    third = await _post(env, conv.id, "셋")
    assert isinstance(first, Run)
    assert isinstance(second, QueuedMessage)
    assert isinstance(third, QueuedMessage)
    assert (second.position, second.text) == (1, "둘")
    assert third.position == 2
    assert [q.text for q in env.service.queue(conv.id)] == ["둘", "셋"]
    assert env.service.summary(conv.id).queued == 2

    env.launcher.finish(first.id)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert [s.text for s in env.launcher.started] == ["하나", "둘"]
    assert [q.position for q in env.service.queue(conv.id)] == [1]
    run2 = env.service.active_run_id(conv.id)
    assert run2 is not None
    env.launcher.finish(run2)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    run3 = env.service.active_run_id(conv.id)
    assert run3 is not None
    env.launcher.finish(run3)
    await env.service.wait_idle()
    assert [s.text for s in env.launcher.started] == ["하나", "둘", "셋"]
    assert env.service.queue(conv.id) == []
    assert env.service.get(conv.id).last_run_id == run3


async def test_waiting_turn_counts_as_busy() -> None:
    env = _env(_graph("team", ["pl"], chat=ChatSettings(busy_policy="reject")))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(env, conv.id, "질문해 줘")
    assert isinstance(run, Run)
    env.launcher.set_status(run.id, "waiting")
    assert env.service.summary(conv.id).last_status == "waiting"
    with pytest.raises(ConversationBusyError) as info:
        await _post(env, conv.id, "새 메시지")
    assert info.value.code == ErrorCodes.CONVERSATION_BUSY
    assert info.value.details["run_id"] == run.id


async def test_reject_policy_from_common_layer_and_team_override() -> None:
    env = _env(
        _graph("strict", ["pl"]),
        _graph("lenient", ["pl"], chat=ChatSettings(busy_policy="queue")),
        common=ChatSettings(busy_policy="reject"),
    )
    strict = env.service.create(CreateConversationRequest(graph_id="strict"))
    lenient = env.service.create(CreateConversationRequest(graph_id="lenient"))
    await _post(env, strict.id, "a")
    await _post(env, lenient.id, "a")
    with pytest.raises(ConversationBusyError):
        await _post(env, strict.id, "b")
    assert isinstance(await _post(env, lenient.id, "b"), QueuedMessage)


async def test_cancel_queued() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    first = await _post(env, conv.id, "하나")
    q1 = await _post(env, conv.id, "둘")
    q2 = await _post(env, conv.id, "셋")
    assert isinstance(first, Run)
    assert isinstance(q1, QueuedMessage)
    assert isinstance(q2, QueuedMessage)
    assert q1.id is not None
    assert q2.id is not None
    removed = env.service.cancel_queued(conv.id, q1.id)
    assert (removed.id, removed.position, removed.text) == (q1.id, 1, "둘")
    assert [(q.id, q.position) for q in env.service.queue(conv.id)] == [(q2.id, 1)]
    with pytest.raises(QueuedMessageNotFoundError) as info:
        env.service.cancel_queued(conv.id, q1.id)
    assert info.value.code == ErrorCodes.NOT_FOUND
    env.launcher.finish(first.id)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert [s.text for s in env.launcher.started] == ["하나", "셋"]


async def test_queued_message_failing_to_start_is_dropped() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    first = await _post(env, conv.id, "하나")
    await _post(env, conv.id, "둘")
    assert isinstance(first, Run)
    env.launcher.fail_with = RuntimeError("검증 실패")
    env.launcher.finish(first.id)
    await env.service.wait_idle()
    assert env.service.queue(conv.id) == []
    assert not env.service.is_busy(conv.id)


# ---------------------------------------------------------------- 세션 이어 쓰기


async def test_sessions_saved_and_passed_to_next_turn() -> None:
    env = _env(_graph("team", ["pl", "qa"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(env, conv.id, "하나")
    assert isinstance(run, Run)
    assert env.launcher.started[0].sessions == {}
    env.launcher.finish(
        run.id,
        events=[
            _event(
                run.id,
                1,
                "agent.session_started",
                {"session_id": "s-old", "backend": "fake"},
                node_path=["pl"],
            ),
            _event(
                run.id,
                2,
                "agent.session_started",
                {"session_id": "s-pl", "backend": "fake"},
                node_path=["pl"],
            ),
            # 서브에이전트(위임자 세션 안)는 따로 저장하지 않는다
            _event(
                run.id,
                3,
                "agent.session_started",
                {"session_id": "s-sub", "backend": "fake"},
                node_path=["pl", "be"],
            ),
            _event(run.id, 4, "agent.session_started", {"bad": True}, node_path=["qa"]),
        ],
    )
    await env.service.wait_idle()
    assert env.service.get(conv.id).sessions == {
        "pl": SessionRef(backend="fake", session_id="s-pl")
    }
    run2 = await _post(env, conv.id, "둘")
    assert isinstance(run2, Run)
    assert env.launcher.started[1].sessions == {"pl": SessionRef(backend="fake", session_id="s-pl")}
    # 이번 턴에 돌지 않은 노드의 세션은 유지하고 돈 노드는 갱신
    env.launcher.finish(
        run2.id,
        events=[
            _event(
                run2.id,
                1,
                "agent.session_started",
                {"session_id": "s-qa", "backend": "fake"},
                node_path=["qa"],
            ),
        ],
    )
    await env.service.wait_idle()
    assert env.service.get(conv.id).sessions == {
        "pl": SessionRef(backend="fake", session_id="s-pl"),
        "qa": SessionRef(backend="fake", session_id="s-qa"),
    }


async def test_switch_graph_drops_sessions_of_missing_nodes() -> None:
    env = _env(_graph("a", ["pl", "qa"]), _graph("b", ["pl", "be"]))
    conv = env.service.create(CreateConversationRequest(graph_id="a"))
    env.conversations.save(
        conv.model_copy(
            update={
                "sessions": {
                    "pl": SessionRef(backend="fake", session_id="1"),
                    "qa": SessionRef(backend="fake", session_id="2"),
                }
            }
        )
    )
    with pytest.raises(GraphNotFoundError):
        env.service.update(conv.id, UpdateConversationRequest(graph_id="nope"))
    updated = env.service.update(conv.id, UpdateConversationRequest(graph_id="b"))
    assert updated.graph_id == "b"
    assert set(updated.sessions) == {"pl"}
    run = await _post(env, conv.id, "다음 턴")
    assert isinstance(run, Run)
    assert env.launcher.started[0].graph.id == "b"


async def test_switch_graph_during_turn_filters_sessions_by_new_graph() -> None:
    env = _env(_graph("a", ["pl", "qa"]), _graph("b", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="a"))
    run = await _post(env, conv.id, "하나")
    assert isinstance(run, Run)
    env.service.update(conv.id, UpdateConversationRequest(graph_id="b"))
    env.launcher.finish(
        run.id,
        events=[
            _event(
                run.id,
                1,
                "agent.session_started",
                {"session_id": "p", "backend": "x"},
                node_path=["pl"],
            ),
            _event(
                run.id,
                2,
                "agent.session_started",
                {"session_id": "q", "backend": "x"},
                node_path=["qa"],
            ),
        ],
    )
    await env.service.wait_idle()
    assert set(env.service.get(conv.id).sessions) == {"pl"}


async def test_update_title_and_archive() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    same = env.service.update(conv.id, UpdateConversationRequest())
    assert same == conv
    updated = env.service.update(
        conv.id, UpdateConversationRequest(title=" 새 제목 ", archived=True)
    )
    assert (updated.title, updated.archived) == ("새 제목", True)
    assert updated.updated_at > conv.updated_at


# ---------------------------------------------------------------- 턴 조립·요약


async def _three_turns(env: Env) -> tuple[str, list[str]]:
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    ids: list[str] = []
    for text in ("하나", "둘", "셋"):
        run = await _post(env, conv.id, text)
        assert isinstance(run, Run)
        ids.append(run.id)
        env.launcher.finish(
            run.id,
            events=[
                _event(run.id, 1, "agent.text_delta", {"text": "..."}, node_path=["pl"]),
                _event(
                    run.id,
                    3,
                    "run.reply",
                    {
                        "edge_id": "r2",
                        "node_id": "qa",
                        "label": "QA",
                        "order": 2,
                        "text": f"{text}-qa",
                    },
                    actor="qa-agent",
                ),
                _event(
                    run.id,
                    2,
                    "run.reply",
                    {"edge_id": "r1", "node_id": "pl", "final": False, "text": f"{text}-pl"},
                    actor="pl-agent",
                ),
                _event(run.id, 4, "run.reply", {"broken": True}),
            ],
        )
        await env.service.wait_idle()
    return conv.id, ids


async def test_turns_assemble_input_replies_interactions() -> None:
    env = _env(_graph("team", ["pl", "qa"]))
    conv, ids = await _three_turns(env)
    env.interactions.save(_interaction("i2", ids[0], conv, "answered", 20.0))
    env.interactions.save(_interaction("i1", ids[0], conv, "expired", 10.0))
    env.interactions.save(_interaction("other", ids[1], conv, "answered", 5.0))
    turns = env.service.turns(conv)
    assert [t.run_id for t in turns] == ids  # 오래된 순
    first = turns[0]
    assert first.user_text == "하나"
    assert [(r.node_id, r.agent_id, r.final, r.text) for r in first.replies] == [
        ("pl", "pl-agent", False, "하나-pl"),
        ("qa", "qa-agent", True, "하나-qa"),
    ]
    assert [i.id for i in first.interactions] == ["i1", "i2"]
    assert first.status == "completed"
    assert first.started_at is not None
    assert first.ended_at is not None
    assert env.service.turn(ids[1]).interactions[0].id == "other"


async def test_turns_paging_with_before_and_limit() -> None:
    env = _env(_graph("team", ["pl"]))
    conv, ids = await _three_turns(env)
    assert [t.run_id for t in env.service.turns(conv, limit=2)] == ids[1:]
    assert [t.run_id for t in env.service.turns(conv, before=ids[1], limit=5)] == ids[:1]
    assert env.service.turns(conv, before=ids[0]) == []
    with pytest.raises(TurnNotFoundError):
        env.service.turns(conv, before="not-a-run")
    with pytest.raises(TurnNotFoundError):
        env.service.turn("not-a-run")


async def test_active_turn_uses_live_status_and_lists_pending_interaction() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(env, conv.id, "물어봐")
    assert isinstance(run, Run)
    env.launcher.set_status(run.id, "waiting")
    env.interactions.save(_interaction("q1", run.id, conv.id, "pending", 1.0))
    env.interactions.save(_interaction("old", "elsewhere", conv.id, "answered", 0.5))
    turn = env.service.turns(conv.id)[-1]
    assert turn.status == "waiting"
    assert [(i.id, i.status) for i in turn.interactions] == [("q1", "pending")]
    summary = env.service.summary(conv.id)
    assert summary.pending_interactions == 1
    assert summary.last_status == "waiting"
    env.notified.clear()
    env.service.notify(conv.id)
    assert env.notified[-1].pending_interactions == 1
    env.service.notify("missing")  # 없는 대화는 조용히 무시


async def test_delete_cancels_active_turn_and_clears_queue() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(env, conv.id, "하나")
    await _post(env, conv.id, "둘")
    assert isinstance(run, Run)
    env.service.delete(conv.id)
    assert env.launcher.cancelled == [(run.id, "conversation_deleted")]
    await env.service.wait_idle()
    assert len(env.launcher.started) == 1  # 대기열 메시지는 실행되지 않음
    with pytest.raises(ConversationNotFoundError):
        env.service.get(conv.id)


async def test_listener_errors_are_swallowed() -> None:
    def boom(_: ConversationSummary) -> None:
        raise RuntimeError("listener")

    env = _env(_graph("team", ["pl"]))
    env.service._listener = boom
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    assert env.service.get(conv.id).id == conv.id


async def test_aclose_cancels_watchers_and_keeps_queue() -> None:
    """종료는 감시만 정리한다. 대기열은 저장소에 남아 다음 시작 때 처리된다(2R.14)."""
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(env, conv.id, "하나")
    await _post(env, conv.id, "둘")
    await env.service.aclose()
    assert [q.text for q in env.service.queue(conv.id)] == ["둘"]
    assert isinstance(run, Run)
    env.launcher.finish(run.id)  # 종료 뒤 끝난 턴은 대기열을 꺼내지 않는다
    await asyncio.sleep(0)
    assert len(env.launcher.started) == 1


async def test_run_task_cancelled_still_releases_conversation() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    run = await _post(env, conv.id, "하나")
    await _post(env, conv.id, "둘")
    assert isinstance(run, Run)
    env.launcher.handles[run.id].done.cancel()  # 엔진 종료 등으로 Run 태스크가 취소됨
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert [s.text for s in env.launcher.started] == ["하나", "둘"]


async def test_conversation_deleted_while_turn_starting_cancels_turn() -> None:
    env = _env(_graph("team", ["pl"]))
    conv = env.service.create(CreateConversationRequest(graph_id="team"))
    gate, entered = asyncio.Event(), asyncio.Event()
    original = env.launcher.start_turn

    async def slow(turn: Any) -> Any:
        entered.set()
        await gate.wait()
        return await original(turn)

    env.launcher.start_turn = slow  # type: ignore[method-assign]
    post = asyncio.create_task(_post(env, conv.id, "hi"))
    await entered.wait()
    env.service.delete(conv.id)
    gate.set()
    run = await post
    assert isinstance(run, Run)
    assert env.launcher.cancelled == [(run.id, "conversation_deleted")]
    assert not env.service.is_busy(conv.id)
    assert env.conversations.get(conv.id) is None  # 지워진 대화를 되살리지 않음
