"""QA 5R.14 반례: 반복+호출 겹침, 재시작 복구된 자식, 경로 부착 모호성."""

from typing import Any

from agent_console_contracts import RunEvent
from agent_console_trace import build_trace


def _ev(seq: int, type: str, path: list[str], payload: dict[str, Any]) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}",
        run_id="r",
        seq=seq,
        ts=float(seq),
        node_path=path,
        attempt=1 if path else None,
        type=type,
        payload=payload,
    )


def _node(seq: int, path: list[str], status: str, **extra: Any) -> RunEvent:
    kind = {"running": "node.started", "succeeded": "node.completed"}.get(status, f"node.{status}")
    return _ev(seq, kind, path, {"status": status, **extra})


def test_repeat_iterations_each_call_hangs_under_its_own_iteration() -> None:
    """위임자가 회차마다 같은 대상을 부르면 호출 span은 그 회차의 위임자 span 아래다."""
    evs = [
        _node(1, ["pl"], "running", iteration=0),
        _node(2, ["pl", "be"], "running", call=0, iteration=0),
        _node(3, ["pl", "be"], "succeeded", call=0, iteration=0),
        _node(4, ["pl"], "succeeded", iteration=0),
        _node(5, ["pl"], "running", iteration=1),
        _node(6, ["pl", "be"], "running", call=1, iteration=1),
        _node(7, ["pl", "be"], "succeeded", call=1, iteration=1),
        _node(8, ["pl"], "succeeded", iteration=1),
    ]
    trace = build_trace(evs)
    by_id = {s.id: s for s in trace.spans}
    assert by_id["call:pl/be#0"].parent_id == "node:pl#1"
    assert by_id["call:pl/be#1"].parent_id == "node:pl#1@1"
    assert len(trace.spans) == 4


def test_recovered_child_without_parent_events_is_unparented_not_guessed() -> None:
    """재시작으로 부모 run.child_started가 없는 자식은 시간 이웃 노드에 붙이지 않는다."""
    child_ev = _node(1, ["a"], "running").model_copy(update={"run_id": "c1"})
    child = build_trace([child_ev])
    evs = [_node(1, ["T"], "running"), _node(2, ["T"], "succeeded")]
    trace = build_trace(evs, children={"c1": child})
    top = next(s for s in trace.spans if s.run_id == "c1")
    assert top.parent_id is None


def test_ambiguous_path_goes_up_one_level() -> None:
    """같은 경로에 열린 호출 + 위임 서브에이전트가 겹치면 위임자로 올린다."""
    evs = [
        _node(1, ["pl"], "running"),
        _node(2, ["pl", "be"], "running", call=0),
        _ev(
            3,
            "agent.subagent_started",
            ["pl", "be"],
            {"subagent_id": "sa", "name": "be", "tool_use_id": None},
        ),
        _ev(
            4,
            "interaction.requested",
            ["pl", "be"],
            {
                "interaction": {
                    "id": "q",
                    "run_id": "r",
                    "node_id": "be",
                    "node_path": ["pl", "be"],
                    "kind": "question",
                    "status": "pending",
                    "created_at": 1.0,
                }
            },
        ),
    ]
    trace = build_trace(evs)
    q = next(s for s in trace.spans if s.id == "interaction:q")
    assert q.parent_id == "node:pl#1"
