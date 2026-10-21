"""build_trace 테스트: 자식 span(서브에이전트), 형제 span + 화살표(넘기기), 사용자 대기 span,
그리고 시간상 이웃을 잇지 않는다는 원칙."""

from typing import Any

import pytest

from agent_console_contracts import RunEvent, Trace, TraceSpan
from agent_console_trace import (
    SPAN_KIND_DELEGATED,
    SPAN_KIND_INTERACTION,
    SPAN_KIND_NODE,
    build_trace,
)

RUN = "run-1"


class _Events:
    """seq·ts를 차례로 붙이는 이벤트 작성 도우미."""

    def __init__(self, run_id: str = RUN) -> None:
        self.run_id = run_id
        self.items: list[RunEvent] = []

    def add(
        self,
        type: str,
        payload: dict[str, Any] | None = None,
        *,
        path: list[str] | None = None,
        actor: str | None = None,
        attempt: int | None = None,
        ts: float | None = None,
    ) -> "_Events":
        seq = len(self.items) + 1
        self.items.append(
            RunEvent(
                event_id=f"{self.run_id}-{seq}",
                run_id=self.run_id,
                seq=seq,
                ts=ts if ts is not None else float(seq),
                node_path=path or [],
                attempt=attempt if attempt is not None else (1 if path else None),
                actor=actor,
                type=type,
                payload=payload or {},
            )
        )
        return self

    def node(self, node: str, status: str, actor: str | None = None, **extra: Any) -> "_Events":
        type = {"running": "node.started", "succeeded": "node.completed"}.get(
            status, f"node.{status}"
        )
        return self.add(type, {"status": status, **extra}, path=[node], actor=actor)


def _span(trace: Trace, span_id: str) -> TraceSpan:
    return next(s for s in trace.spans if s.id == span_id)


def _interaction(iid: str, node_path: list[str], actor: str, created: float) -> dict[str, Any]:
    return {
        "interaction": {
            "id": iid,
            "run_id": RUN,
            "node_id": node_path[-1],
            "node_path": node_path,
            "actor": actor,
            "kind": "question",
            "status": "pending",
            "title": "어느 DB를 쓸까요?",
            "created_at": created,
        }
    }


def test_subagent_is_child_span_in_same_session() -> None:
    ev = (
        _Events()
        .node("pl", "running", actor="pl-agent")
        .add("agent.session_started", {"session_id": "S1", "backend": "claude"}, path=["pl"])
        .add(
            "agent.tool_call",
            {"tool_use_id": "tu-1", "name": "Agent"},
            path=["pl"],
            actor="pl-agent",
        )
        .add(
            "agent.subagent_started",
            {
                "subagent_id": "sa-1",
                "name": "be",
                "tool_use_id": "tu-1",
                "task_preview": "API 구현",
            },
            path=["pl", "be"],
            actor="backend-lead",
        )
        .add("agent.text_delta", {"text": "..."}, path=["pl", "be"], actor="backend-lead")
        .add(
            "agent.subagent_stopped",
            {
                "subagent_id": "sa-1",
                "name": "be",
                "tool_use_id": "tu-1",
                "status": "completed",
                "usage": {"total_tokens": 1234},
                "result_preview": "완료",
            },
            path=["pl", "be"],
            actor="backend-lead",
        )
        .add("agent.usage", {"usage": {"input_tokens": 10, "output_tokens": 5}}, path=["pl"])
        .node("pl", "succeeded", actor="pl-agent", outputs_preview="끝")
    )
    trace = build_trace(ev.items)
    assert trace.run_id == RUN
    pl = _span(trace, "node:pl#1")
    assert (pl.kind, pl.actor, pl.status, pl.session_id) == (
        SPAN_KIND_NODE,
        "pl-agent",
        "succeeded",
        "S1",
    )
    assert pl.usage is not None
    assert pl.usage.input_tokens == 10
    assert pl.result_preview == "끝"
    assert (pl.started_at, pl.ended_at) == (1.0, 8.0)
    sub = _span(trace, "delegated:sa-1")
    assert sub.kind == SPAN_KIND_DELEGATED
    assert sub.parent_id == pl.id
    assert sub.node_path == ["pl", "be"]
    assert (sub.node_id, sub.actor, sub.status) == ("be", "backend-lead", "completed")
    assert sub.session_id == "S1"  # 같은 세션
    assert sub.usage is not None
    assert sub.usage.total_tokens == 1234
    assert (sub.task_preview, sub.result_preview, sub.tool_use_id) == ("API 구현", "완료", "tu-1")
    assert trace.links == []


def test_subagent_started_on_delegator_path_gets_target_name() -> None:
    ev = (
        _Events()
        .node("pl", "running")
        .add("agent.subagent_started", {"subagent_id": "x", "name": "qa"}, path=["pl"])
    )
    sub = _span(build_trace(ev.items), "delegated:x")
    assert sub.node_path == ["pl", "qa"]
    assert sub.parent_id == "node:pl#1"  # 위임자 경로(명시)


def test_handoff_is_sibling_span_with_arrow_and_order() -> None:
    ev = (
        _Events()
        .node("pl", "running", actor="pl")
        .node("pl", "succeeded", actor="pl")
        .add(
            "edge.traversed",
            {
                "edge_id": "h1",
                "source": {"node": "pl", "port": "out"},
                "target": {"node": "qa", "port": "in"},
            },
        )
        .add(
            "edge.traversed",
            {
                "edge_id": "h2",
                "source": {"node": "pl", "port": "out"},
                "target": {"node": "doc", "port": "in"},
            },
        )
        .node("doc", "running", actor="writer")
        .node("qa", "running", actor="qa")
        .node("qa", "succeeded", actor="qa")
        .node("doc", "succeeded", actor="writer")
        .add(  # 실행되지 않은 도착 노드(답변 연결 등)로의 화살표는 만들지 않는다
            "edge.traversed",
            {
                "edge_id": "r1",
                "source": {"node": "qa", "port": "out"},
                "target": {"node": "you", "port": "hears"},
            },
        )
    )
    trace = build_trace(ev.items, edge_kinds={"h1": "handoff", "h2": "handoff"})
    assert [(link.source, link.target, link.edge_id, link.kind) for link in trace.links] == [
        ("node:pl#1", "node:qa#1", "h1", "handoff"),
        ("node:pl#1", "node:doc#1", "h2", "handoff"),
    ]
    qa, doc = _span(trace, "node:qa#1"), _span(trace, "node:doc#1")
    assert qa.parent_id is None
    assert doc.parent_id is None
    assert (qa.order, doc.order) == (1, 2)  # 넘김 순번 = edge.traversed 순서
    assert _span(trace, "node:pl#1").order is None


def test_link_kind_prefers_event_payload_and_falls_back_to_graph() -> None:
    """4R.18: `edge.traversed` payload의 `kind`가 있으면 그것, 없는 옛 이벤트는 `edge_kinds`."""

    def edge(edge_id: str, target: str, **extra: str) -> dict[str, object]:
        return {
            "edge_id": edge_id,
            "source": {"node": "pl", "port": "out"},
            "target": {"node": target, "port": "in"},
            **extra,
        }

    ev = (
        _Events()
        .node("pl", "running", actor="pl")
        .node("pl", "succeeded", actor="pl")
        .add("edge.traversed", edge("h1", "qa", kind="delegate"))  # 새 이벤트(종류 실림)
        .add("edge.traversed", edge("h2", "doc"))  # 옛 이벤트(종류 없음)
        .node("qa", "running", actor="qa")
        .node("doc", "running", actor="writer")
    )
    graph = {"h1": "handoff", "h2": "handoff"}
    trace = build_trace(ev.items, edge_kinds=graph)
    assert [(link.edge_id, link.kind) for link in trace.links] == [
        ("h1", "delegate"),  # 이벤트 값이 그래프 표보다 먼저
        ("h2", "handoff"),
    ]
    bare = build_trace(ev.items)
    assert [(link.edge_id, link.kind) for link in bare.links] == [("h1", "delegate"), ("h2", None)]


def test_interaction_spans_link_by_interaction_id() -> None:
    ev = (
        _Events()
        .node("pl", "running", actor="pl")
        .add("interaction.requested", _interaction("q1", ["pl"], "pl", 2.5), path=["pl"])
        .node("pl", "waiting", actor="pl")
        .add(
            "agent.subagent_started",
            {"subagent_id": "sa", "name": "be", "tool_use_id": "tu"},
            path=["pl", "be"],
            actor="be",
        )
        .add(
            "interaction.requested", _interaction("q2", ["pl", "be"], "be", 5.0), path=["pl", "be"]
        )
        .add(
            "interaction.answered",
            {
                "interaction_id": "q1",
                "kind": "question",
                "answered_by": "user",
                "response_preview": "Postgres",
            },
            path=["pl"],
        )
        .add(
            "interaction.closed",
            {
                "interaction_id": "q2",
                "kind": "tool_permission",
                "status": "expired",
                "reason": "timeout",
            },
            path=["pl", "be"],
        )
        .add("node.resumed", {"status": "running", "waited_ms": 3500}, path=["pl"], actor="pl")
    )
    trace = build_trace(ev.items)
    q1 = _span(trace, "interaction:q1")
    assert (q1.kind, q1.parent_id, q1.interaction_id) == (SPAN_KIND_INTERACTION, "node:pl#1", "q1")
    assert (q1.status, q1.started_at, q1.ended_at) == ("answered", 2.5, 6.0)
    assert (q1.task_preview, q1.result_preview) == ("어느 DB를 쓸까요?", "Postgres")
    q2 = _span(trace, "interaction:q2")
    assert q2.parent_id == "delegated:sa"  # 서브에이전트가 연 요청은 위임 span의 자식
    assert (q2.status, q2.result_preview, q2.actor) == ("expired", "timeout", "be")
    assert _span(trace, "node:pl#1").status == "running"  # resumed


# ---------------------------------------------------------------- 시간상 이웃을 잇지 않는다


def test_adjacent_nodes_without_explicit_edge_are_not_linked() -> None:
    ev = (
        _Events()
        .node("a", "running", ts=1.0)
        .node("a", "succeeded", ts=2.0)
        .node(
            "b", "running", ts=2.0001
        )  # 바로 다음에 시작했어도 edge.traversed가 없으면 잇지 않는다
        .node("b", "succeeded", ts=3.0)
    )
    trace = build_trace(ev.items)
    assert trace.links == []
    assert all(s.parent_id is None for s in trace.spans)
    assert all(s.order is None for s in trace.spans)


def test_subagent_without_ids_is_not_attached_to_running_node() -> None:
    ev = (
        _Events()
        .node("pl", "running")  # 이 시점에 실행 중인 노드는 pl 하나뿐이지만
        .add("agent.subagent_started", {"subagent_id": "orphan"})  # node_path·tool_use_id·name 없음
        .add("agent.tool_call", {"tool_use_id": "tu-x", "name": "Agent"})  # 소속 경로 없는 호출
        .add("agent.subagent_started", {"subagent_id": "orphan2", "tool_use_id": "tu-x"})
    )
    trace = build_trace(ev.items)
    assert _span(trace, "delegated:orphan").parent_id is None
    assert _span(trace, "delegated:orphan2").parent_id is None


def test_interleaved_subagents_close_by_id_not_by_order() -> None:
    ev = (
        _Events()
        .node("pl", "running")
        .add(
            "agent.subagent_started",
            {"subagent_id": "A", "name": "be", "tool_use_id": "t1"},
            path=["pl", "be"],
        )
        .add(
            "agent.subagent_started",
            {"subagent_id": "B", "name": "fe", "tool_use_id": "t2"},
            path=["pl", "fe"],
        )
        .add("agent.subagent_stopped", {"subagent_id": "A", "status": "failed"}, path=["pl", "be"])
        .add(
            "agent.subagent_stopped",
            {"subagent_id": "ghost", "status": "completed"},
            path=["pl", "x"],
        )
        .add(
            "agent.subagent_stopped",
            {"subagent_id": "nomatch", "tool_use_id": "t2", "status": "completed"},
            path=["pl", "fe"],
        )
    )
    trace = build_trace(ev.items)
    assert (_span(trace, "delegated:A").status, _span(trace, "delegated:A").ended_at) == (
        "failed",
        4.0,
    )
    assert (_span(trace, "delegated:B").status, _span(trace, "delegated:B").ended_at) == (
        "completed",
        6.0,
    )
    assert not any(s.id == "delegated:ghost" for s in trace.spans)  # 시작을 못 본 종료는 버림


def test_ambiguous_delegation_path_falls_back_to_explicit_ancestor() -> None:
    ev = (
        _Events()
        .node("pl", "running")
        .add("agent.subagent_started", {"subagent_id": "A", "name": "be"}, path=["pl", "be"])
        .add("agent.subagent_started", {"subagent_id": "B", "name": "be"}, path=["pl", "be"])
        # 같은 대상이 두 번 위임돼 경로만으로는 어느 쪽인지 모른다 → 가장 최근 것에 붙이지 않는다
        .add("interaction.requested", _interaction("q", ["pl", "be"], "be", 4.0), path=["pl", "be"])
    )
    assert _span(build_trace(ev.items), "interaction:q").parent_id == "node:pl#1"


def test_interaction_of_unknown_node_has_no_parent() -> None:
    ev = (
        _Events()
        .node("pl", "running")
        .add("interaction.requested", _interaction("q", ["review"], "x", 2.0), path=["review"])
    )
    assert _span(build_trace(ev.items), "interaction:q").parent_id is None


def test_edge_from_unseen_source_is_ignored() -> None:
    ev = (
        _Events()
        .add(
            "edge.traversed",
            {
                "edge_id": "e",
                "source": {"node": "ghost", "port": "out"},
                "target": {"node": "b", "port": "in"},
            },
        )
        .node("b", "running")
    )
    assert build_trace(ev.items).links == []


# ---------------------------------------------------------------- 견고성


def test_retry_attempts_are_separate_spans_and_link_uses_latest_source() -> None:
    ev = _Events()
    ev.add("node.started", {"status": "running"}, path=["a"], attempt=1)
    ev.add("node.failed", {"status": "failed"}, path=["a"], attempt=1)
    ev.add("node.started", {"status": "running"}, path=["a"], attempt=2)
    ev.add("node.completed", {"status": "succeeded"}, path=["a"], attempt=2)
    ev.add(
        "edge.traversed",
        {
            "edge_id": "e",
            "source": {"node": "a", "port": "o"},
            "target": {"node": "b", "port": "i"},
        },
    )
    ev.node("b", "running")
    trace = build_trace(ev.items)
    assert [s.id for s in trace.spans] == ["node:a#1", "node:a#2", "node:b#1"]
    assert trace.links[0].source == "node:a#2"


def test_skipped_and_queued_nodes_do_not_make_spans() -> None:
    ev = _Events().add("node.queued", {"status": "queued"}, path=["a"]).node("b", "skipped")
    assert build_trace(ev.items).spans == []


def test_malformed_and_unknown_events_are_skipped() -> None:
    ev = (
        _Events()
        .node("a", "running")
        .add("node.completed", {"status": "not-a-status"}, path=["a"])
        .add("agent.subagent_started", {"name": "x"}, path=["a", "x"])  # subagent_id 없음
        .add("interaction.requested", {"interaction": {"id": "q"}})
        .add("custom.plugin_event", {"anything": 1}, path=["a"])
    )
    trace = build_trace(ev.items)
    assert [s.id for s in trace.spans] == ["node:a#1"]
    assert trace.spans[0].status == "running"


def test_events_are_sorted_by_seq() -> None:
    ev = _Events().node("a", "running").node("a", "succeeded")
    trace = build_trace(list(reversed(ev.items)))
    assert _span(trace, "node:a#1").status == "succeeded"


def test_run_id_rules() -> None:
    assert build_trace([], run_id="r").spans == []
    with pytest.raises(ValueError, match="run_id"):
        build_trace([])
    mixed = _Events("r1").node("a", "running").items + _Events("r2").node("b", "running").items
    with pytest.raises(ValueError, match="섞여"):
        build_trace(mixed)


def test_preview_is_clipped() -> None:
    ev = _Events().node("a", "running").node("a", "succeeded", outputs_preview="x" * 50)
    assert (
        _span(build_trace(ev.items, preview_chars=10), "node:a#1").result_preview == "x" * 9 + "…"
    )
