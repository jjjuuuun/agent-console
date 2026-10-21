"""handoff_matrix 테스트(여러 실행의 "누가 누구에게 몇 번")."""

from agent_console_contracts import Trace, TraceLink, TraceSpan
from agent_console_trace import SPAN_KIND_INTERACTION, handoff_matrix


def _trace(run_id: str, spans: list[TraceSpan], links: list[TraceLink] | None = None) -> Trace:
    return Trace(run_id=run_id, spans=spans, links=links or [])


def _node(sid: str, actor: str | None, node: str | None = None) -> TraceSpan:
    return TraceSpan(id=sid, kind="node", actor=actor, node_id=node or sid)


def _child(sid: str, parent: str, actor: str | None, kind: str = "delegated") -> TraceSpan:
    return TraceSpan(id=sid, kind=kind, parent_id=parent, actor=actor, node_id=sid)


def _runs() -> list[Trace]:
    first = _trace(
        "r1",
        [
            _node("pl", "pl-agent"),
            _child("be", "pl", "backend"),
            _child("fe", "pl", "frontend"),
            _child("ask", "pl", "pl-agent", kind=SPAN_KIND_INTERACTION),
            _node("qa", "qa-agent"),
        ],
        [TraceLink(source="pl", target="qa", edge_id="h1", kind="handoff")],
    )
    second = _trace(
        "r2",
        [_node("pl", "pl-agent"), _child("be", "pl", "backend"), _node("qa", "qa-agent")],
        [
            TraceLink(source="pl", target="qa", edge_id="h1", kind="handoff"),
            TraceLink(source="pl", target="missing", edge_id="x"),
        ],
    )
    return [first, second]


def test_counts_links_and_delegations_across_runs() -> None:
    matrix = handoff_matrix(_runs())
    assert matrix.runs == 2
    assert [(c.source, c.target, c.kind, c.count) for c in matrix.cells] == [
        ("pl-agent", "backend", "delegated", 2),
        ("pl-agent", "qa-agent", "handoff", 2),
        ("pl-agent", "frontend", "delegated", 1),
    ]


def test_options_child_kinds_links_limit() -> None:
    only_links = handoff_matrix(_runs(), child_kinds=())
    assert [(c.target, c.count) for c in only_links.cells] == [("qa-agent", 2)]
    no_links = handoff_matrix(
        _runs(), include_links=False, child_kinds=("delegated", SPAN_KIND_INTERACTION)
    )
    assert ("pl-agent", "pl-agent", SPAN_KIND_INTERACTION, 1) in [
        (c.source, c.target, c.kind, c.count) for c in no_links.cells
    ]
    assert len(handoff_matrix(_runs(), limit=1).cells) == 1


def test_falls_back_to_node_id_and_skips_unnamed() -> None:
    trace = _trace(
        "r",
        [_node("a", None, node="node-a"), TraceSpan(id="b", kind="delegated", parent_id="a")],
    )
    matrix = handoff_matrix([trace])
    assert matrix.cells == []  # 받은 쪽 이름(actor·node_id)이 없으면 세지 않는다
    trace2 = _trace("r", [_node("a", None, node="node-a"), _child("c", "a", None)])
    assert [(c.source, c.target) for c in handoff_matrix([trace2]).cells] == [("node-a", "c")]


def test_empty() -> None:
    assert handoff_matrix([]).model_dump() == {"cells": [], "runs": 0}
