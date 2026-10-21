"""QA 반례: 재시도·반복에서 링크가 엉뚱한 시도에 붙지 않는가."""

from typing import Any

from agent_console_contracts import RunEvent
from agent_console_trace import build_trace


def _ev(
    seq: int, type: str, path: list[str], payload: dict[str, Any], attempt: int = 1
) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}",
        run_id="r",
        seq=seq,
        ts=float(seq),
        node_path=path,
        attempt=attempt,
        type=type,
        payload=payload,
    )


def _edge(seq: int, a: str, b: str, eid: str) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}",
        run_id="r",
        seq=seq,
        ts=float(seq),
        node_path=[],
        type="edge.traversed",
        payload={
            "edge_id": eid,
            "source": {"node": a, "port": "o"},
            "target": {"node": b, "port": "i"},
        },
    )


def test_link_targets_attempt_that_actually_ran_after_traversal() -> None:
    evs = [
        _ev(1, "node.started", ["a"], {"status": "running"}),
        _ev(2, "node.completed", ["a"], {"status": "succeeded"}),
        _edge(3, "a", "b", "e1"),
        _ev(4, "node.started", ["b"], {"status": "running"}),
        _ev(5, "node.completed", ["b"], {"status": "succeeded"}),
        _edge(6, "b", "a", "e2"),
        _ev(7, "node.started", ["a"], {"status": "running"}, attempt=2),
        _ev(8, "node.completed", ["a"], {"status": "succeeded"}, attempt=2),
    ]
    trace = build_trace(evs)
    back = next(link for link in trace.links if link.edge_id == "e2")
    assert back.target == "node:a#2"
