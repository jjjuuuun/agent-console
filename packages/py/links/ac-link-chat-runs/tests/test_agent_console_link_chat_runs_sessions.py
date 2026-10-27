"""link-chat-runs: 중첩 실행(자식 Run) 노드 세션을 경로 키로 대화에 기록하고 다음 턴에 넘긴다
(5R.11 QA FAIL 1회차 수정, design §5R.7).

노드 종류 이름은 쓰지 않는다 — Run 계보(``root_run_id``·``parent_run_id``·``parent_node_id``)만
본다.
"""

from __future__ import annotations

from typing import Any, cast

from agent_console_chat import ChatService
from agent_console_chat.testing import MemoryEvents, MemoryRuns
from agent_console_contracts import (
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    Run,
    RunEvent,
    SessionRef,
    UpdateConversationRequest,
)
from agent_console_link_chat_runs import (
    CHAT_CONVERSATIONS,
    CHAT_TURN_SESSIONS,
    LineageSessions,
    module,
)
from agent_console_link_chat_runs.testing import (
    LocalRunStarter,
    local_chat_module,
    local_runs_module,
)
from agent_console_modkit import assemble
from agent_console_nodes_core import SESSIONS, child_sessions
from agent_console_runtime import session_refs

OUTER = Graph(
    id="outer",
    name="바깥",
    nodes=[NodeSpec(id="T", type="nest"), NodeSpec(id="pl", type="agent")],
)
OTHER = Graph(id="other", name="다른", nodes=[NodeSpec(id="T", type="nest")])


def _ref(sid: str) -> SessionRef:
    return SessionRef(backend="fake-agent", session_id=sid)


def _run(rid: str, created: float, **lineage: Any) -> Run:
    return Run(
        id=rid,
        graph_id="g",
        graph_version="v",
        status="completed",
        input={},
        origin="chat" if not lineage else "child",
        created_at=created,
        **lineage,
    )


def _session(run_id: str, seq: int, node_path: list[str], sid: str) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=float(seq),
        node_path=node_path,
        type="agent.session_started",
        payload={"session_id": sid, "backend": "fake-agent"},
    )


def _tree(runs: MemoryRuns, events: MemoryEvents, root: str = "root") -> None:
    """root(pl) → kid(T 안의 a, 위임 a/sub) → grand(kid의 U 안의 b), orphan(계보 끊김)."""
    runs.save(_run(root, 1.0))
    runs.save(_run("kid", 2.0, parent_run_id=root, parent_node_id="T", root_run_id=root))
    runs.save(_run("grand", 3.0, parent_run_id="kid", parent_node_id="U", root_run_id=root))
    runs.save(_run("orphan", 4.0, parent_run_id="lost", parent_node_id="X", root_run_id=root))
    events.add(
        [
            _session(root, 1, ["pl"], "s-pl"),
            _session("kid", 1, ["a"], "s-a"),
            _session("kid", 2, ["a", "sub"], "s-sub"),  # 위임(세션 안) — 따로 저장하지 않음
            _session("grand", 1, ["b"], "s-b"),
            _session("orphan", 1, ["c"], "s-c"),
        ]
    )


def test_collect_uses_path_keys_for_descendants() -> None:
    runs, events = MemoryRuns(), MemoryEvents()
    _tree(runs, events)
    rules = LineageSessions(runs, events)
    root = runs.get("root")
    assert root is not None
    found = rules.collect(root)
    assert found == {"pl": _ref("s-pl"), "T/a": _ref("s-a"), "T/U/b": _ref("s-b")}
    # 노드가 자식 Run에 넘기는 규칙(child_sessions)과 짝이다
    inner = child_sessions(session_refs(found), "T")
    assert {k: v.session_id for k, v in inner.items()} == {"a": "s-a", "U/b": "s-b"}
    assert {k: v.session_id for k, v in child_sessions(inner, "U").items()} == {"b": "s-b"}


def test_later_child_run_wins_same_key() -> None:
    runs, events = MemoryRuns(), MemoryEvents()
    runs.save(_run("root", 1.0))
    runs.save(_run("k1", 2.0, parent_run_id="root", parent_node_id="T", root_run_id="root"))
    runs.save(_run("k2", 3.0, parent_run_id="root", parent_node_id="T", root_run_id="root"))
    events.add([_session("k2", 1, ["a"], "new"), _session("k1", 1, ["a"], "old")])
    root = runs.get("root")
    assert root is not None
    assert LineageSessions(runs, events).collect(root) == {"T/a": _ref("new")}


def test_prune_keeps_keys_under_current_nodes() -> None:
    rules = LineageSessions(MemoryRuns(), MemoryEvents())
    sessions = {
        "pl": _ref("1"),
        "T/a": _ref("2"),
        "T/U/b": _ref("3"),
        "Tx/a": _ref("4"),  # 접두만 같은 다른 노드
        "gone/a": _ref("5"),
    }
    assert rules.prune(sessions, ["T", "pl"]) == {
        "pl": _ref("1"),
        "T/a": _ref("2"),
        "T/U/b": _ref("3"),
    }
    assert rules.prune(sessions, []) == {}


async def test_module_records_nested_sessions_and_passes_them_next_turn() -> None:
    starter = LocalRunStarter()
    assembly = assemble(
        [
            module,
            local_chat_module(graphs=[OUTER, OTHER]),
            local_runs_module(starter=starter),
        ]
    )
    assert assembly.port(CHAT_TURN_SESSIONS) is not None
    chat = cast(ChatService, assembly.port(CHAT_CONVERSATIONS))
    await assembly.start()
    try:
        conv = chat.create(CreateConversationRequest(graph_id="outer"))
        first = await chat.post_message(conv.id, PostMessageRequest(text="하나"))
        assert isinstance(first, Run)
        _tree(starter.runs, starter.events, root=first.id)
        starter.finish(first.id)
        await chat.wait_idle()
        assert chat.get(conv.id).sessions == {
            "pl": _ref("s-pl"),
            "T/a": _ref("s-a"),
            "T/U/b": _ref("s-b"),
        }
        second = await chat.post_message(conv.id, PostMessageRequest(text="둘"))
        assert isinstance(second, Run)
        passed = {k: v.session_id for k, v in starter.calls[1]["extra_services"][SESSIONS].items()}
        assert passed == {"pl": "s-pl", "T/a": "s-a", "T/U/b": "s-b"}
        starter.finish(second.id)
        await chat.wait_idle()
        switched = chat.update(conv.id, UpdateConversationRequest(graph_id="other"))
        assert set(switched.sessions) == {"T/a", "T/U/b"}
    finally:
        await assembly.stop()
