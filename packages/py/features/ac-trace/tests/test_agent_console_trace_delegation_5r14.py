"""5R.14 위임 흐름: 호출 NodeRun span(별도 세션), 반복 회차 span, 사이클 연결 링크, 자식 Run 묶음.

모두 명시 id(`node_path`·payload `call`·`iteration`·`edge.traversed`·`run.child_started`)로만
잇는다.
"""

from typing import Any

from agent_console_contracts import NodeRun, RunEvent, Trace, TraceSpan
from agent_console_trace import (
    SPAN_KIND_NODE,
    build_trace,
    call_span_id,
    child_span_id,
    handoff_matrix,
    node_span_id,
)


class _Events:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.items: list[RunEvent] = []

    def add(
        self,
        type: str,
        payload: dict[str, Any] | None = None,
        *,
        path: list[str] | None = None,
        actor: str | None = None,
    ) -> "_Events":
        seq = len(self.items) + 1
        self.items.append(
            RunEvent(
                event_id=f"{self.run_id}-{seq}",
                run_id=self.run_id,
                seq=seq,
                ts=float(seq),
                node_path=path or [],
                attempt=1 if path else None,
                actor=actor,
                type=type,
                payload=payload or {},
            )
        )
        return self

    def node(self, path: list[str], status: str, **extra: Any) -> "_Events":
        type = {"running": "node.started", "succeeded": "node.completed"}.get(
            status, f"node.{status}"
        )
        return self.add(type, {"status": status, **extra}, path=path, actor=path[-1])

    def call(self, path: list[str], call: int, *, iteration: int = 0) -> "_Events":
        """호출 NodeRun 하나(queued → started → 세션 → completed)."""
        tag = "/".join(path)
        return (
            self.node(path, "queued", call=call, iteration=iteration)
            .node(path, "running", call=call, iteration=iteration)
            .add(
                "agent.session_started",
                {"session_id": f"s-{tag}-{call}", "backend": "fake"},
                path=path,
            )
            .node(path, "succeeded", call=call, iteration=iteration, outputs_preview=f"{tag}끝")
        )

    def edge(self, eid: str, src: str, dst: str, kind: str | None = None) -> "_Events":
        payload: dict[str, Any] = {
            "edge_id": eid,
            "source": {"node": src, "port": "out"},
            "target": {"node": dst, "port": "in"},
        }
        if kind is not None:
            payload["kind"] = kind
        return self.add("edge.traversed", payload)


def _span(trace: Trace, span_id: str) -> TraceSpan:
    return next(s for s in trace.spans if s.id == span_id)


def _node_run(path: list[str], call: int, inputs: dict[str, Any]) -> NodeRun:
    return NodeRun(
        run_id="r",
        node_id=path[-1],
        status="succeeded",
        call=call,
        invoked_by=path[:-1],
        inputs=inputs,
    )


# ---------------------------------------------------------------- 호출 NodeRun


def test_call_node_runs_are_separate_session_children_per_call() -> None:
    ev = (
        _Events("r")
        .node(["pl"], "running", iteration=0)
        .add("agent.session_started", {"session_id": "s-pl", "backend": "fake"}, path=["pl"])
        .add(
            "agent.tool_call",
            {"tool_use_id": "t1", "name": "delegate", "input": {"target": "be"}},
            path=["pl"],
        )
        .call(["pl", "be"], 0)
        .call(["pl", "be"], 1)
        .node(["pl"], "succeeded", iteration=0)
    )
    node_runs = [
        _node_run(["pl", "be"], 0, {"delegated": "API 만들기"}),
        _node_run(["pl", "be"], 1, {"a": 1, "b": "둘"}),
    ]
    trace = build_trace(
        ev.items,
        edge_kinds={"pl->be": "delegate"},
        call_edges={("pl", "be"): "pl->be"},
        node_runs=node_runs,
    )
    first = _span(trace, call_span_id(["pl", "be"], 0))
    second = _span(trace, "call:pl/be#1")
    for i, span in enumerate((first, second)):
        assert span.kind == SPAN_KIND_NODE
        assert span.parent_id == node_span_id("pl", 1) == "node:pl#1"
        assert (span.call, span.iteration, span.node_path) == (i, 0, ["pl", "be"])
        assert span.session_id == f"s-pl/be-{i}"  # 위임자(s-pl)와 다른 별도 세션
        assert span.status == "succeeded"
        assert span.result_preview == "pl/be끝"
    assert first.task_preview == "API 만들기"  # NodeRun 입력(위임 과제)
    assert second.task_preview == '{"a": 1, "b": "둘"}'
    calls = [link for link in trace.links if link.target.startswith("call:")]
    assert [(link.source, link.edge_id, link.kind) for link in calls] == [
        ("node:pl#1", "pl->be", "delegate"),
        ("node:pl#1", "pl->be", "delegate"),
    ]
    assert all(s.order is None for s in trace.spans)  # 호출은 넘김 순번이 아니다
    matrix = handoff_matrix([trace])
    assert [(c.source, c.target, c.kind, c.count) for c in matrix.cells] == [
        ("pl", "be", "delegate", 2)
    ]


def test_nested_call_parent_is_open_outer_call() -> None:
    ev = (
        _Events("r")
        .node(["pl"], "running")
        .node(["pl", "mid"], "queued", call=0)
        .node(["pl", "mid"], "running", call=0)
        .add("agent.tool_call", {"tool_use_id": "t", "name": "delegate"}, path=["pl", "mid"])
        .call(["pl", "mid", "leaf"], 0)
        .node(["pl", "mid"], "succeeded", call=0)
        .node(["pl"], "succeeded")
    )
    trace = build_trace(ev.items)
    leaf = _span(trace, "call:pl/mid/leaf#0")
    assert leaf.parent_id == "call:pl/mid#0"
    assert _span(trace, "call:pl/mid#0").parent_id == "node:pl#1"
    # 쌍의 연결을 모르면 링크는 남기되 연결 id·종류는 비운다
    assert {(link.source, link.target, link.kind) for link in trace.links} == {
        ("node:pl#1", "call:pl/mid#0", None),
        ("call:pl/mid#0", "call:pl/mid/leaf#0", None),
    }


def test_call_counterexamples_use_explicit_ids_only() -> None:
    """R8.6 반례: 끝난 호출에 뒤늦은 이벤트를 붙이지 않고, 거부된 호출은 span이 없다."""
    ev = (
        _Events("r")
        .node(["pl"], "running")
        .call(["pl", "be"], 0)
        # 호출이 끝난 뒤 같은 경로의 이벤트: 열린 호출이 없으니 위임자로(가장 최근 호출로 추정 금지)
        .add(
            "interaction.requested",
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
            path=["pl", "be"],
        )
        .add("agent.session_started", {"session_id": "late", "backend": "fake"}, path=["pl", "be"])
        # 깊이 초과·순환 거부는 NodeRun 없이 경고만
        .add(
            "log.warning",
            {"message": "깊이 초과", "details": {"code": "delegation.depth_exceeded"}},
            path=["pl"],
        )
        # 호출 회차(call)가 없는 긴 경로의 노드 이벤트는 호출로 보지 않는다
        .node(["pl", "ghost"], "running")
        # 부른 쪽을 못 본 호출은 부모 없이
        .call(["nobody", "x"], 0)
        .node(["pl"], "succeeded")
    )
    trace = build_trace(ev.items)
    assert _span(trace, "interaction:q").parent_id == "node:pl#1"
    assert _span(trace, "call:pl/be#0").session_id == "s-pl/be-0"
    assert not any("ghost" in s.id for s in trace.spans)
    assert _span(trace, "call:nobody/x#0").parent_id is None
    assert {s.id for s in trace.spans} == {
        "node:pl#1",
        "call:pl/be#0",
        "interaction:q",
        "call:nobody/x#0",
    }
    assert not any(link.target == "call:nobody/x#0" for link in trace.links)


def test_subagent_inside_call_shares_the_call_session() -> None:
    ev = (
        _Events("r")
        .node(["pl"], "running")
        .add("agent.session_started", {"session_id": "s-pl", "backend": "fake"}, path=["pl"])
        .node(["pl", "be"], "running", call=0)
        .add("agent.session_started", {"session_id": "s-be", "backend": "fake"}, path=["pl", "be"])
        .add("agent.tool_call", {"tool_use_id": "tu", "name": "Agent"}, path=["pl", "be"])
        .add(
            "agent.subagent_started",
            {"subagent_id": "sa", "name": "db", "tool_use_id": "tu"},
            path=["pl", "be", "db"],
        )
    )
    trace = build_trace(ev.items)
    sub = _span(trace, "delegated:sa")
    assert sub.parent_id == "call:pl/be#0"
    assert sub.session_id == "s-be"


# ---------------------------------------------------------------- 반복 회차


def test_iterations_are_separate_spans_and_cycle_edge_is_a_link() -> None:
    ev = (
        _Events("r")
        .node(["w"], "running", iteration=0)
        .add("agent.session_started", {"session_id": "s0", "backend": "fake"}, path=["w"])
        .node(["w"], "succeeded", iteration=0)
        .edge("h1", "w", "rv", "handoff")
        .node(["rv"], "running", iteration=0)
        .node(["rv"], "succeeded", iteration=0)
        .edge("back", "rv", "w", "loop")
        .add("loop.iteration", {"edge_id": "back", "iteration": 1, "nodes": ["w", "rv"]})
        .node(["w"], "running", iteration=1)
        .add("agent.session_started", {"session_id": "s1", "backend": "fake"}, path=["w"])
        .add("agent.usage", {"usage": {"input_tokens": 5}}, path=["w"])
        .node(["w"], "succeeded", iteration=1)
        .edge("h1", "w", "rv", "handoff")
        .node(["rv"], "running", iteration=1)
        .node(["rv"], "succeeded", iteration=1)
        .add("loop.exhausted", {"edge_id": "back", "iteration": 1, "max_iterations": 1})
        .add(
            "edge.skipped",
            {
                "edge_id": "back",
                "source": {"node": "rv", "port": "out"},
                "target": {"node": "w", "port": "in"},
                "reason": "max_iterations",
            },
        )
    )
    trace = build_trace(ev.items)
    assert [(s.id, s.iteration) for s in trace.spans] == [
        ("node:w#1", 0),
        ("node:rv#1", 0),
        ("node:w#1@1", 1),
        ("node:rv#1@1", 1),
    ]
    assert _span(trace, "node:w#1").session_id == "s0"
    assert _span(trace, "node:w#1@1").session_id == "s1"
    assert _span(trace, "node:w#1").usage is None
    assert _span(trace, "node:w#1@1").usage is not None
    assert [(link.source, link.target, link.edge_id, link.kind) for link in trace.links] == [
        ("node:w#1", "node:rv#1", "h1", "handoff"),
        ("node:rv#1", "node:w#1@1", "back", "loop"),  # 사이클 연결 = 다음 회차로 가는 링크
        ("node:w#1@1", "node:rv#1@1", "h1", "handoff"),
    ]  # 건너뛴 연결(edge.skipped)은 링크가 아니다
    assert [s.order for s in trace.spans] == [None, 1, 2, 3]


def test_iteration_zero_keeps_old_span_ids() -> None:
    assert node_span_id("a", 1) == node_span_id("a", 1, 0) == "node:a#1"
    assert node_span_id("a", 2, 3) == "node:a#2@3"


# ---------------------------------------------------------------- 자식 Run


def _child_trace(run_id: str, grand: Trace | None = None) -> Trace:
    ev = _Events(run_id).node(["ca"], "running").node(["ca"], "succeeded")
    children: dict[str, Trace] = {}
    if grand is not None:
        ev.edge("h", "ca", "T2", "handoff").node(["T2"], "running")
        ev.add("run.child_started", {"child_run_id": grand.run_id, "node_id": "T2"}, path=["T2"])
        children[grand.run_id] = grand
    return build_trace(ev.items, children=children)


def test_child_run_trace_hangs_under_team_node_with_run_id() -> None:
    grand = _child_trace("gc")
    child = _child_trace("c1", grand)
    ev = (
        _Events("root")
        .node(["T"], "running")
        .add("run.child_started", {"child_run_id": "c1", "node_id": "T"}, path=["T"])
        .add(
            "run.child_finished",
            {"child_run_id": "c1", "node_id": "T", "status": "completed"},
            path=["T"],
        )
        .node(["T"], "succeeded")
    )
    trace = build_trace(ev.items, children={"c1": child, "orphan": _child_trace("orphan")})
    by_id = {s.id: s for s in trace.spans}
    ca = by_id[child_span_id("c1", "node:ca#1")]
    assert ca.id == "run:c1/node:ca#1"
    assert (ca.run_id, ca.parent_id) == ("c1", "node:T#1")
    t2 = by_id["run:c1/node:T2#1"]
    assert (t2.run_id, t2.parent_id) == ("c1", "node:T#1")  # 자식 Run의 맨 위 span
    gca = by_id["run:gc/node:ca#1"]
    assert (gca.run_id, gca.parent_id) == ("gc", "run:c1/node:T2#1")  # 손자는 자식 안 팀 노드 아래
    # 부른 노드를 못 본 자식은 부모 없이 붙는다(명시 키 없음)
    assert by_id["run:orphan/node:ca#1"].parent_id is None
    assert by_id["node:T#1"].run_id is None  # 이 Run 자신의 span은 run_id가 비어 있다
    child_links = [link for link in trace.links if link.run_id == "c1"]
    assert [(link.source, link.target) for link in child_links] == [
        ("run:c1/node:ca#1", "run:c1/node:T2#1")
    ]


def test_child_run_top_spans_attach_to_team_node() -> None:
    child = build_trace(
        _Events("c1").node(["a"], "running").node(["b"], "running").items,
    )
    ev = (
        _Events("root")
        .node(["T"], "running")
        .add("run.child_started", {"child_run_id": "c1", "node_id": "T"}, path=["T"])
    )
    trace = build_trace(ev.items, children={"c1": child})
    tops = [s for s in trace.spans if s.run_id == "c1"]
    assert [(s.id, s.parent_id) for s in tops] == [
        ("run:c1/node:a#1", "node:T#1"),
        ("run:c1/node:b#1", "node:T#1"),
    ]


def test_child_run_called_by_delegator_hangs_under_call_span() -> None:
    child = build_trace(_Events("c1").node(["a"], "running").items)
    ev = (
        _Events("root")
        .node(["pl"], "running")
        .node(["pl", "T"], "running", call=0)
        .add("run.child_started", {"child_run_id": "c1", "node_id": "T"}, path=["pl", "T"])
    )
    trace = build_trace(ev.items, children={"c1": child})
    assert _span(trace, "run:c1/node:a#1").parent_id == "call:pl/T#0"
