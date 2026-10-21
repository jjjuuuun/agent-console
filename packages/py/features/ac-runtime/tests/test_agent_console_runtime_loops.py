"""반복 — 사이클 연결 실행(design §5R.4, 5R.5).

엔진은 연결 종류 이름을 모른다: 테스트 연결 `t.loop`(디스크립터 `cycle`)과 그 이름을 바꾼 사본으로
같은 동작을 확인한다. 노드는 테스트 전용 `t.step`(config `per_iteration`으로 회차마다 다른
결과)이다.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_console_contracts import (
    EdgeSpec,
    EdgeTypeDescriptor,
    FlowSettings,
    KnownIssueCodes,
    NodeRun,
    Run,
    RunEvent,
    parse_run_event,
)
from agent_console_graph import GraphIssueCodes
from agent_console_runtime import (
    Activation,
    GraphValidationError,
    NodeRunView,
    RuntimeErrorCodes,
    recover_unfinished_runs,
    resume_options,
    resume_seed,
)
from agent_console_runtime.testing import (
    BUILDERS,
    Builders,
    Harness,
    LoopEdge,
    SequentialIds,
    make_harness,
)

LOOP = "t.loop"


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def runs_of(h: Harness, run_id: str) -> dict[tuple[str, int], str]:
    """(노드, 회차) → 상태."""
    return {(nr.node_id, nr.iteration): nr.status for nr in h.recorder.runs.list_node_runs(run_id)}


def events(h: Harness, run_id: str, type: str | None = None) -> list[RunEvent]:
    return [e for e in h.recorder.events.list(run_id) if type is None or e.type == type]


def loop_payloads(h: Harness, run_id: str, type: str) -> list[dict[str, Any]]:
    found = events(h, run_id, type)
    for event in found:
        parse_run_event(event.model_dump(mode="json"))  # 알려진 형식으로 검증된다
    return [e.payload for e in found]


def seen(h: Harness, node_id: str) -> list[tuple[int, tuple[tuple[str, Any, bool], ...]]]:
    return [(s.iteration, s.incoming) for s in h.probe.seen if s.node_id == node_id]


class IterationGate:
    """출발 노드 회차가 config `min` 이상일 때만 지나가는 테스트 연결(`NodeRunView.iteration`)."""

    descriptor = EdgeTypeDescriptor(id="t.from-iteration", title="회차 조건")

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None
        if source.iteration < int(edge.config.get("min", 0)):
            return None
        return Activation(source.outputs[edge.source.port])


# ---------------------------------------------------------------- 기본 반복


async def test_two_node_cycle_runs_until_limit(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "draft"}), b.node("b", outputs={"out": "again"})],
        [b.edge("a", "b"), b.edge("b", "a", kind=LOOP, max_iterations=2), b.reply("b")],
        entries=["a"],
    )
    run = await h.make().run(g, {"text": "hi"})

    assert run.status == "completed"
    assert runs_of(h, run.id) == {
        ("a", 0): "succeeded",
        ("a", 1): "succeeded",
        ("a", 2): "succeeded",
        ("b", 0): "succeeded",
        ("b", 1): "succeeded",
        ("b", 2): "succeeded",
    }
    loop_id = "b.out->a.in"
    assert loop_payloads(h, run.id, "loop.iteration") == [
        {"edge_id": loop_id, "iteration": 1, "nodes": ["a", "b"]},
        {"edge_id": loop_id, "iteration": 2, "nodes": ["a", "b"]},
    ]
    assert loop_payloads(h, run.id, "loop.exhausted") == [
        {"edge_id": loop_id, "iteration": 2, "max_iterations": 2}
    ]
    # node.* payload에 회차가 있다
    started = [(e.node_path, e.payload["iteration"]) for e in events(h, run.id, "node.started")]
    assert started == [(["a"], 0), (["b"], 0), (["a"], 1), (["b"], 1), (["a"], 2), (["b"], 2)]
    # 답변은 회차마다 나간다(b가 답변 연결을 가진다)
    assert len(events(h, run.id, "run.reply")) == 3


async def test_next_iteration_receives_cycle_edge_value_first(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "draft"}), b.node("b", outputs={"out": "fix it"})],
        [b.edge("a", "b"), b.edge("b", "a", kind=LOOP, max_iterations=1)],
        entries=["a"],
    )
    run = await h.make().run(g, {"text": "hi"})
    assert run.status == "completed"

    entry_id = "you.says->a.in"
    loop_id = "b.out->a.in"
    assert seen(h, "a") == [
        (0, ((entry_id, {"text": "hi"}, False),)),
        # 입구 값은 남아 있지만(carried) 사이클 연결 값이 이번 회차 값이다
        (1, ((entry_id, {"text": "hi"}, True), (loop_id, "fix it", False))),
    ]
    inputs = {
        (nr.node_id, nr.iteration): nr.inputs for nr in h.recorder.runs.list_node_runs(run.id)
    }
    assert inputs[("a", 0)] == {"in": {"text": "hi"}}
    assert inputs[("a", 1)] == {"in": "fix it"}

    # 사이클 연결 통과 → 회차 열기 → 도착 노드 대기열 순서
    types = [
        (e.type, e.payload.get("edge_id"), e.payload.get("iteration"))
        for e in events(h, run.id)
        if e.type in ("edge.traversed", "loop.iteration")
        or (e.type == "node.queued" and e.node_path == ["a"])
    ]
    at = types.index(("loop.iteration", loop_id, 1))
    assert types[at - 1 : at + 2] == [
        ("edge.traversed", loop_id, None),
        ("loop.iteration", loop_id, 1),
        ("node.queued", None, 1),
    ]


async def test_three_node_cycle_uses_descriptor_default(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a"), b.node("b"), b.node("c", outputs={"out": "x"})],
        [b.edge("a", "b"), b.edge("b", "c"), b.edge("c", "a", kind=LOOP)],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    # 디스크립터 cycle.max_iterations = 3 → 회차 0~3
    assert sorted(runs_of(h, run.id)) == [(n, i) for n in "abc" for i in range(4)]
    assert loop_payloads(h, run.id, "loop.exhausted")[0]["max_iterations"] == 3


@pytest.mark.parametrize(
    ("edge_config", "settings", "expected_runs"),
    [
        ({}, FlowSettings(max_iterations=1), 2),  # 설정 → 디스크립터 기본값을 덮는다
        ({"max_iterations": 2}, FlowSettings(max_iterations=1), 3),  # 엣지 config가 먼저
        ({}, None, 4),  # 디스크립터 기본값
    ],
)
async def test_limit_inheritance_order(
    h: Harness,
    b: Builders,
    edge_config: dict[str, Any],
    settings: FlowSettings | None,
    expected_runs: int,
) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": 1})],
        [b.edge("a", "a", kind=LOOP, **edge_config)],
        entries=["a"],
    )
    run = await h.make().run(g, flow_settings=settings)
    assert run.status == "completed"
    assert len(h.recorder.runs.list_node_runs(run.id)) == expected_runs


async def test_runtime_default_flow_settings(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a", outputs={"out": 1})], [b.edge("a", "a", kind=LOOP)], entries=["a"])
    run = await h.make(flow_settings=FlowSettings(max_iterations=2)).run(g)
    assert len(h.recorder.runs.list_node_runs(run.id)) == 3


# ---------------------------------------------------------------- 검토 반려 되돌리기


def review_graph(b: Builders, *, max_iterations: int | None = None) -> Any:
    """작성자 w → 검토 r. r.out(승인) → 다음 n, r.alt(반려) ⇢ w(사이클)."""
    loop_config = {} if max_iterations is None else {"max_iterations": max_iterations}
    return b.graph(
        [
            b.node("w", outputs={"out": "draft"}),
            b.node(
                "r",
                per_iteration=[
                    {"outputs": {"alt": "reason 1"}},
                    {"outputs": {"alt": "reason 2"}},
                    {"outputs": {"out": "approved"}},
                ],
            ),
            b.node("n"),
        ],
        [
            b.edge("w", "r"),
            b.edge("r", "n"),
            b.edge("r", "w", kind=LOOP, sp="alt", **loop_config),
            b.reply("n"),
        ],
        entries=["w"],
    )


async def test_review_rejections_loop_back_then_continue(h: Harness, b: Builders) -> None:
    run = await h.make().run(review_graph(b), {"text": "write"})

    assert run.status == "completed"
    # 반려 두 번 동안 승인 쪽 하류(n)는 skipped가 되지 않고 기다렸다가 승인 뒤 한 번만 실행된다
    assert runs_of(h, run.id) == {
        ("w", 0): "succeeded",
        ("w", 1): "succeeded",
        ("w", 2): "succeeded",
        ("r", 0): "succeeded",
        ("r", 1): "succeeded",
        ("r", 2): "succeeded",
        ("n", 0): "succeeded",
    }
    assert [s[1][-1][1] for s in seen(h, "w")] == [{"text": "write"}, "reason 1", "reason 2"]
    assert [e.payload["text"] for e in events(h, run.id, "run.reply")] == ["{'in': 'approved'}"]
    assert loop_payloads(h, run.id, "loop.exhausted") == []


async def test_exhausted_then_other_edge_continues(h: Harness, b: Builders) -> None:
    h.registries.edge_types.register("t.from-iteration", IterationGate())
    g = b.graph(
        [
            b.node("w", outputs={"out": "draft"}),
            b.node("r", outputs={"alt": "no"}),  # 늘 반려
            b.node("n"),
            b.node("giveup"),
        ],
        [
            b.edge("w", "r"),
            b.edge("r", "n"),
            b.edge("r", "w", kind=LOOP, sp="alt", max_iterations=2),
            # 한도에 닿은 회차(2)에서만 지나가는 다른 연결
            b.edge("r", "giveup", kind="t.from-iteration", sp="alt", min=2),
        ],
        entries=["w"],
    )
    run = await h.make().run(g)

    assert run.status == "completed"
    assert loop_payloads(h, run.id, "loop.exhausted") == [
        {"edge_id": "r.alt->w.in", "iteration": 2, "max_iterations": 2}
    ]
    result = runs_of(h, run.id)
    assert result[("giveup", 0)] == "succeeded"
    assert result[("n", 0)] == "skipped"  # 승인 쪽은 반복이 끝난 뒤에야 막힌다
    assert [k for k in result if k[0] == "w"] == [("w", 0), ("w", 1), ("w", 2)]


async def test_edge_leaving_region_runs_downstream_once(h: Harness, b: Builders) -> None:
    # 영역 밖으로 나가는 연결이 회차마다 지나가도 밖 노드는 한 번만 실행된다
    g = b.graph(
        [b.node("a", outputs={"out": "v"}), b.node("side")],
        [b.edge("a", "side"), b.edge("a", "a", kind=LOOP, max_iterations=2)],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    assert runs_of(h, run.id) == {
        ("a", 0): "succeeded",
        ("a", 1): "succeeded",
        ("a", 2): "succeeded",
        ("side", 0): "succeeded",
    }


# ---------------------------------------------------------------- 중첩 반복


async def test_nested_cycles_reset_inner_count(h: Harness, b: Builders) -> None:
    # 바깥 a → b → c → d ⇢ a, 안쪽 c ⇢ b. c는 회차마다 반려(alt)·통과(out)를 번갈아 낸다.
    g = b.graph(
        [
            b.node("a"),
            b.node("b"),
            b.node(
                "c",
                per_iteration=[
                    {"outputs": {"alt": "inner"}},
                    {"outputs": {"out": "done"}},
                    {"outputs": {"alt": "inner"}},
                    {"outputs": {"out": "done"}},
                ],
            ),
            b.node("d", outputs={"out": "outer"}),
        ],
        [
            b.edge("a", "b"),
            b.edge("b", "c"),
            b.edge("c", "d"),
            b.edge("c", "b", kind=LOOP, sp="alt", max_iterations=1),
            b.edge("d", "a", kind=LOOP, max_iterations=1),
            b.reply("d"),
        ],
        entries=["a"],
    )
    run = await h.make().run(g)

    assert run.status == "completed"
    iterations: dict[str, list[int]] = {}
    for node_id, i in sorted(runs_of(h, run.id)):
        iterations.setdefault(node_id, []).append(i)
    # 안쪽 반복 한도는 1이지만 바깥 회차가 열릴 때 횟수가 0으로 돌아가 두 번 돈다
    assert iterations == {"a": [0, 1], "b": [0, 1, 2, 3], "c": [0, 1, 2, 3], "d": [0, 1]}
    opened = [(p["edge_id"], p["iteration"]) for p in loop_payloads(h, run.id, "loop.iteration")]
    # loop.iteration.iteration = 도착 노드의 새 NodeRun 회차(b는 바깥 회차 안에서 3회차)
    assert opened == [("c.alt->b.in", 1), ("d.out->a.in", 1), ("c.alt->b.in", 3)]
    assert loop_payloads(h, run.id, "loop.exhausted") == [
        {"edge_id": "d.out->a.in", "iteration": 1, "max_iterations": 1}
    ]


# ---------------------------------------------------------------- 검증·이름 무관


async def test_cycle_without_cycle_edge_is_rejected(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a"), b.node("b")], [b.edge("a", "b"), b.edge("b", "a")], entries=["a"])
    with pytest.raises(GraphValidationError) as info:
        await h.make().start(g)
    assert [i.code for i in info.value.issues] == [GraphIssueCodes.CYCLE]


async def test_renamed_cycle_edge_kind_works(h: Harness, b: Builders) -> None:
    renamed = LoopEdge()
    renamed.descriptor = LoopEdge.descriptor.model_copy(update={"id": "t.zz-again"})
    h.registries.edge_types.register("t.zz-again", renamed)
    g = b.graph(
        [b.node("a"), b.node("b", outputs={"out": 1})],
        [b.edge("a", "b"), b.edge("b", "a", kind="t.zz-again", max_iterations=1)],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    assert sorted(runs_of(h, run.id)) == [("a", 0), ("a", 1), ("b", 0), ("b", 1)]


# ---------------------------------------------------------------- 안전 한도·사용량·세션


async def test_max_node_runs_fails_run(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a"), b.node("b", outputs={"out": 1})],
        [b.edge("a", "b"), b.edge("b", "a", kind=LOOP, max_iterations=50)],
        entries=["a"],
    )
    run = await h.make().run(g, flow_settings=FlowSettings(max_node_runs=5))

    assert run.status == "failed"
    assert run.error is not None
    assert run.error.code == KnownIssueCodes.FLOW_MAX_NODE_RUNS_EXCEEDED
    assert run.error.code == RuntimeErrorCodes.MAX_NODE_RUNS_EXCEEDED
    assert run.error.details == {"limit": 5}
    executed = [k for k, v in runs_of(h, run.id).items() if v != "skipped"]
    assert len(executed) == 5
    assert all(v in ("succeeded", "skipped") for v in runs_of(h, run.id).values())
    assert events(h, run.id)[-1].type == "run.failed"


async def test_max_node_runs_none_is_unlimited(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": 1})],
        [b.edge("a", "a", kind=LOOP, max_iterations=4)],
        entries=["a"],
    )
    run = await h.make().run(g, flow_settings=FlowSettings(max_node_runs=None))
    assert run.status == "completed"
    assert len(h.recorder.runs.list_node_runs(run.id)) == 5


async def test_usage_totals_and_previous_session(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": 1}, session="s", usage={"input_tokens": 10})],
        [b.edge("a", "a", kind=LOOP, max_iterations=2)],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.totals is not None
    assert run.totals.input_tokens == 30
    assert [s.previous_session_id for s in h.probe.seen] == [None, "s-0", "s-1"]
    sessions = {
        nr.iteration: nr.backend_session_id for nr in h.recorder.runs.list_node_runs(run.id)
    }
    assert sessions == {0: "s-0", 1: "s-1", 2: "s-2"}


async def test_failure_in_earlier_iteration_still_fails_run(h: Harness, b: Builders) -> None:
    # 영역 a → x → c, a → c(join any), c ⇢ a. x는 첫 회차에서 실패(처리 안 됨), 다음 회차는 성공.
    g = b.graph(
        [
            b.node("a", outputs={"out": 1}),
            b.node("x", per_iteration=[{"fail": True}, {}]),
            b.node("c", outputs={"out": 1}),
        ],
        [
            b.edge("a", "x"),
            b.edge("x", "c"),
            b.edge("a", "c", tp="in2"),
            b.edge("c", "a", kind=LOOP, max_iterations=1),
        ],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert runs_of(h, run.id)[("x", 0)] == "failed"
    assert runs_of(h, run.id)[("x", 1)] == "succeeded"
    assert run.status == "failed"
    assert run.error is not None
    assert run.error.details["node_id"] == "x"


# ---------------------------------------------------------------- 취소·재시작 복구


async def wait_seen(h: Harness, node_id: str, iteration: int) -> None:
    for _ in range(2000):
        if any(s.node_id == node_id and s.iteration == iteration for s in h.probe.seen):
            return
        await asyncio.sleep(0.001)
    raise AssertionError(f"{node_id} 회차 {iteration}이 시작되지 않았다")


async def test_cancel_during_second_iteration(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a"), b.node("b", outputs={"out": 1}, per_iteration=[{}, {"hang": True}])],
        [b.edge("a", "b"), b.edge("b", "a", kind=LOOP)],
        entries=["a"],
    )
    rt = h.make()
    handle = await rt.start(g)
    await wait_seen(h, "b", 1)
    rt.cancel(handle.run_id)
    run = await handle.wait()

    assert run.status == "cancelled"
    assert runs_of(h, run.id) == {
        ("a", 0): "succeeded",
        ("b", 0): "succeeded",
        ("a", 1): "succeeded",
        ("b", 1): "cancelled",
    }
    cancelled = events(h, run.id, "node.cancelled")
    assert [(e.node_path, e.payload["iteration"]) for e in cancelled] == [(["b"], 1)]


async def test_interrupt_during_iteration_then_resume_options(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a"), b.node("b", outputs={"out": 1}, per_iteration=[{}, {"hang": True}])],
        [b.edge("a", "b"), b.edge("b", "a", kind=LOOP)],
        entries=["a"],
    )
    rt = h.make()
    handle = await rt.start(g)
    await wait_seen(h, "b", 1)
    handle.interrupt()
    run = await handle.wait()
    assert run.status == "interrupted"

    node_runs = h.recorder.runs.list_node_runs(run.id)
    options = resume_options(
        run,
        node_runs,
        h.recorder.events.list(run.id),
        graph=g,
        node_types=[e.item.descriptor for e in h.registries.node_types.list()],
    )
    assert [(o.node_id, o.status) for o in options.nodes] == [("b", "running")]
    assert resume_seed(node_runs, ["b"]) == {"b": {"in": {"in": 1}}}


def test_recovery_cancels_only_unfinished_iteration() -> None:
    from agent_console_runtime.testing import InMemoryRecorder

    recorder = InMemoryRecorder()
    recorder.runs.save(
        Run(
            id="r1",
            graph_id="g",
            graph_version="v",
            status="running",
            input={},
            origin="api",
            created_at=1.0,
        )
    )
    for iteration, status in ((0, "succeeded"), (1, "running")):
        recorder.runs.save_node_run(
            NodeRun(
                run_id="r1",
                node_id="a",
                status=status,  # type: ignore[arg-type]
                iteration=iteration,
                started_at=2.0,
            )
        )
    assert recover_unfinished_runs(recorder, clock=lambda: 9.0, ids=SequentialIds("x")) == ["r1"]

    by_iteration = {nr.iteration: nr for nr in recorder.runs.list_node_runs("r1")}
    assert by_iteration[0].status == "succeeded"
    assert by_iteration[1].status == "cancelled"
    assert by_iteration[1].error is not None
    assert by_iteration[1].error.code == RuntimeErrorCodes.INTERRUPTED
    cancelled = [e for e in recorder.events.list("r1") if e.type == "node.cancelled"]
    assert [e.payload["iteration"] for e in cancelled] == [1]


# ---------------------------------------------------------------- 흔들림 없음


async def test_loop_run_is_deterministic(b: Builders) -> None:
    shapes = set()
    for _ in range(5):
        h = make_harness()
        run = await h.make().run(review_graph(b))
        shapes.add(tuple(e.type for e in h.recorder.events.list(run.id)))
    assert len(shapes) == 1
