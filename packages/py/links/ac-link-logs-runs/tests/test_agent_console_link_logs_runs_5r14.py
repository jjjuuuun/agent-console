"""5R.14: 위임 고도화 이벤트 대응(데이터)·자식 Run 수집·호출 NodeRun 넘김."""

from __future__ import annotations

from agent_console_contracts import Run
from agent_console_contracts.logs import LogEvent
from agent_console_link_logs_runs import load_default_event_map
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogFilter, query_context

NEW_TYPES = ("edge.skipped", "loop.iteration", "loop.exhausted", "run.child_started")


def _events(rig: PlatformRunsRig, **flt: object) -> list[LogEvent]:
    return rig.index.query_events(LogFilter(limit=200).with_(**flt), query_context(None)).items


def test_new_event_types_have_own_rules_in_data() -> None:
    table = load_default_event_map()
    fallback = table.rule_for("brand.unknown")
    for type in (*NEW_TYPES, "run.child_finished"):
        assert table.rule_for(type) is not fallback, type
        assert table.rule_for(type) is not table.rule_for("run.*"), type


def _child(run_id: str, parent: str, created_at: float) -> Run:
    return run_record(run_id, created_at=created_at).model_copy(
        update={"parent_run_id": parent, "root_run_id": parent, "parent_node_id": "T"}
    )


def test_child_run_is_its_own_unit_and_parent_event_points_to_it() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record("r1", created_at=1.0))
    rig.records.runs.save(_child("c1", "r1", 2.0))
    rig.records.events.append(
        run_event(1, "node.started", {"status": "running"}, ("T",)),
        run_event(
            2, "run.child_started", {"child_run_id": "c1", "node_id": "T", "graph_id": "g2"}, ("T",)
        ),
        run_event(
            3,
            "run.child_finished",
            {"child_run_id": "c1", "node_id": "T", "status": "failed"},
            ("T",),
        ),
        run_event(1, "node.started", {"status": "running"}, ("ca",), run_id="c1"),
        run_event(2, "run.interrupted", {"status": "interrupted"}, (), run_id="c1"),
    )
    rig.scan()
    parent = {e.seq: e for e in _events(rig) if e.run_id == "r1"}
    started, finished = parent[2], parent[3]
    assert (started.category, started.stage, started.title) == (
        "agent",
        "start",
        "자식 실행 시작 T → g2",
    )
    assert started.correlation["child_run"] == "c1"
    assert (finished.stage, finished.status, finished.call_id) == ("complete", "error", "c1")
    child = [e for e in _events(rig) if e.run_id == "c1"]
    assert [e.title for e in child] == ["ca running", "실행 interrupted"]
    assert child[0].thread == "ca"  # 자식 Run 안 상대 경로


def test_loop_and_skipped_edge_events() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    hop = {"source": {"node": "rv", "port": "o"}, "target": {"node": "w", "port": "i"}}
    rig.records.events.append(
        run_event(1, "loop.iteration", {"edge_id": "back", "iteration": 1, "nodes": ["w"]}, ()),
        run_event(
            2, "loop.exhausted", {"edge_id": "back", "iteration": 2, "max_iterations": 2}, ()
        ),
        run_event(3, "edge.skipped", {"edge_id": "back", **hop, "reason": "condition_false"}, ()),
    )
    rig.scan()
    it, ex, sk = _events(rig)
    assert (it.category, it.title) == ("control", "반복 1회차 (back)")
    assert (ex.status, ex.title) == ("warning", "반복 한도 2/2 (back)")
    assert (sk.category, sk.title) == ("control", "rv ↛ w condition_false")
    assert not sk.from_  # 지나가지 않은 연결은 넘김이 아니다
    assert not sk.to


def test_call_node_run_start_is_a_handoff_scheduled_is_not() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "node.started", {"status": "running"}, ("lead",)),
        run_event(2, "node.started", {"status": "running", "call": 0}, ("lead", "m1")),
        run_event(3, "node.started", {"status": "running", "call": None}, ("old",)),
    )
    rig.scan()
    lead, m1, old = _events(rig)
    # 5.5R.7(C7): 받는 쪽도 호출 NodeRun일 때만 채운다(대응표 조건부 값).
    assert (lead.from_, lead.to, lead.via) == ([], [], "")
    assert (m1.from_, m1.to, m1.via, m1.title) == (["lead"], ["m1"], "delegate", "m1 running")
    assert old.via == ""
    matrix = rig.index.handoffs(LogFilter(), query_context(None))
    assert [(c.source, c.target, c.kind, c.count) for c in matrix.cells] == [
        ("lead", "m1", "delegate", 1)
    ]
