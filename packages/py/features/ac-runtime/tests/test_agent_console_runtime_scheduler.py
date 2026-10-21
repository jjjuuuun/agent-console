"""토큰 스케줄러: 순차·분기·dead-path·join·실패·동시성·저장 후 발행·버전 고정."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_console_contracts import parse_run_event
from agent_console_graph import graph_hash
from agent_console_registry import UnknownExtensionError
from agent_console_runtime import GraphValidationError, RuntimeErrorCodes
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def statuses(h: Harness, run_id: str) -> dict[str, str]:
    return {nr.node_id: nr.status for nr in h.recorder.runs.list_node_runs(run_id)}


def types(h: Harness, run_id: str) -> list[str]:
    return [e.type for e in h.recorder.events.list(run_id)]


async def test_linear_run_stores_events_before_publish(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "hello"}), b.node("b"), b.node("c")],
        [b.edge("a", "b"), b.edge("b", "c")],
        entries=["a"],
    )
    run = await h.make().run(g, {"text": "hi"}, origin="api")

    assert run.status == "completed"
    assert run.origin == "api"
    assert run.graph_version == graph_hash(g)
    assert statuses(h, run.id) == {"a": "succeeded", "b": "succeeded", "c": "succeeded"}
    # 입구 노드는 입구 엣지가 넘긴 Run 입력을 받고, 다음 노드는 엣지가 전달한 값을 받는다.
    assert h.probe.calls[0] == ("a", {"in": {"text": "hi"}})
    assert h.probe.calls[1] == ("b", {"in": "hello"})
    assert h.probe.calls[2] == ("c", {"in": {"in": "hello"}})

    events = h.recorder.events.list(run.id)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert events[0].type == "run.created"
    assert events[-1].type == "run.completed"
    assert "edge.traversed" in types(h, run.id)
    # 4R.18: edge.traversed payload에 연결 종류(엣지 kind)를 싣는다.
    traversed = [e.payload for e in events if e.type == "edge.traversed"]
    kinds = {edge.id: edge.kind for edge in g.edges}
    assert len(traversed) == 2  # a→b, b→c(입구 엣지는 지나간 기록이 없다)
    assert all(p["kind"] == kinds[p["edge_id"]] == "t.flow" for p in traversed)
    for e in events:
        parse_run_event(e)  # 알려진 type은 계약 형식을 지킨다
    # 저장 후 발행: 발행 순간 이미 저장돼 있었다.
    assert [e.event_id for e in h.sink.events] == [e.event_id for e in events]
    assert all(h.sink.stored_at_publish)
    saved = h.recorder.runs.get(run.id)
    assert saved is not None
    assert saved.status == "completed"
    assert saved.ended_at is not None


async def test_unemitted_port_kills_path_and_downstream_is_skipped(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("r", outputs={"out": 1}),
            b.node("yes"),
            b.node("no"),
            b.node("after_no"),
        ],
        [b.edge("r", "yes"), b.edge("r", "no", sp="alt"), b.edge("no", "after_no")],
        entries=["r"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    assert statuses(h, run.id) == {
        "r": "succeeded",
        "yes": "succeeded",
        "no": "skipped",
        "after_no": "skipped",
    }
    assert types(h, run.id).count("node.skipped") == 2


async def test_dynamic_ports_route(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("d", type="t.dyn", ports=["x", "y"], choose="y"), b.node("nx"), b.node("ny")],
        [b.edge("a0", "d", tp="in"), b.edge("d", "nx", sp="x"), b.edge("d", "ny", sp="y")],
        entries=["a0"],
    )
    g = g.model_copy(update={"nodes": [b.node("a0", outputs={"out": 5}), *g.nodes]})
    run = await h.make().run(g)
    assert statuses(h, run.id) == {
        "a0": "succeeded",
        "d": "succeeded",
        "nx": "skipped",
        "ny": "succeeded",
    }


async def test_any_join_runs_once_with_first_arrival(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("x", outputs={"out": "X"}),
            b.node("y", outputs={"out": "Y"}, sleep=0.05),
            b.node("z"),
        ],
        [b.edge("x", "z"), b.edge("y", "z", tp="in2")],
        entries=["x", "y"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    z_calls = [c for c in h.probe.calls if c[0] == "z"]
    assert z_calls == [("z", {"in": "X"})]


async def test_all_join_waits_for_every_reachable_edge(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("x", outputs={"out": "X"}),
            b.node("y", outputs={"out": "Y"}, sleep=0.05),
            b.node("dead", outputs={}),  # 아무 포트도 방출하지 않음 → 그 엣지는 죽는다
            b.node("z", join="all"),
        ],
        [b.edge("x", "z"), b.edge("y", "z", tp="in2"), b.edge("dead", "z", tp="in2")],
        entries=["x", "y", "dead"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    assert [c for c in h.probe.calls if c[0] == "z"] == [("z", {"in": "X", "in2": "Y"})]


async def test_unhandled_failure_fails_run_and_skips_downstream(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a", fail=True), b.node("b")], [b.edge("a", "b")], entries=["a"])
    run = await h.make().run(g)
    assert run.status == "failed"
    assert run.error is not None
    assert run.error.code == RuntimeErrorCodes.NODE_FAILED
    assert run.error.details["node_id"] == "a"
    assert statuses(h, run.id) == {"a": "failed", "b": "skipped"}
    assert types(h, run.id)[-1] == "run.failed"


async def test_failure_with_activated_edge_is_handled(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", fail=True), b.node("ok"), b.node("handler")],
        [b.edge("a", "ok"), b.edge("a", "handler", kind="t.err")],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    assert statuses(h, run.id) == {"a": "failed", "ok": "skipped", "handler": "succeeded"}
    assert h.probe.calls[-1][1]["in"]["code"] == "t.fail"


async def test_exception_becomes_failed_node(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a", **{"raise": "kaboom"})], [], entries=["a"])
    run = await h.make().run(g)
    assert run.status == "failed"
    nr = h.recorder.runs.list_node_runs(run.id)[0]
    assert nr.error is not None
    assert nr.error.code == RuntimeErrorCodes.NODE_EXCEPTION
    assert "kaboom" in nr.error.message


async def test_node_may_skip_itself(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a", skip=True), b.node("b")], [b.edge("a", "b")], entries=["a"])
    run = await h.make().run(g)
    assert run.status == "completed"
    assert statuses(h, run.id) == {"a": "skipped", "b": "skipped"}


async def test_broken_edge_is_dead_and_warned(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a"), b.node("b")], [b.edge("a", "b", kind="t.broken")], entries=["a"])
    run = await h.make().run(g)
    assert run.status == "completed"
    assert statuses(h, run.id)["b"] == "skipped"
    assert "log.warning" in types(h, run.id)


async def test_max_concurrency_limits_parallel_nodes(h: Harness, b: Builders) -> None:
    fan = [b.node(f"p{i}", sleep=0.03) for i in range(5)]
    g = b.graph([b.node("s"), *fan], [b.edge("s", f"p{i}") for i in range(5)], entries=["s"])
    run = await h.make(max_concurrency=2).run(g)
    assert run.status == "completed"
    assert h.probe.max_running == 2


async def test_unlimited_concurrency_runs_fan_out_in_parallel(h: Harness, b: Builders) -> None:
    fan = [b.node(f"p{i}", sleep=0.03) for i in range(4)]
    g = b.graph([b.node("s"), *fan], [b.edge("s", f"p{i}") for i in range(4)], entries=["s"])
    await h.make().run(g)
    assert h.probe.max_running == 4


async def test_usage_totals_are_summed(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("a", usage={"input_tokens": 3, "cost_usd": 0.5, "extra_metric": 2}),
            b.node("b", usage={"input_tokens": 4, "output_tokens": 1}),
        ],
        [b.edge("a", "b")],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.totals is not None
    assert run.totals.input_tokens == 7
    assert run.totals.output_tokens == 1
    assert run.totals.cost_usd == 0.5
    assert run.totals.model_dump()["extra_metric"] == 2


async def test_graph_version_is_frozen_at_start(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a", sleep=0.05)], [], entries=["a"])
    expected = graph_hash(g)
    handle = await h.make().start(g)
    g.nodes.append(b.node("late"))  # 실행 중 정의 변경은 영향이 없다
    run = await handle.wait()
    assert run.graph_version == expected
    assert set(statuses(h, run.id)) == {"a"}


async def test_validation_errors_prevent_run(h: Harness, b: Builders) -> None:
    rt = h.make()
    bad = b.graph([b.node("a", invalid=True), b.node("b", sleep=-1)], [b.edge("a", "zz")])
    with pytest.raises(GraphValidationError) as info:
        await rt.start(bad)
    codes = {i.code for i in info.value.issues}
    assert {"t.invalid", "invalid_config", "unknown_node"} <= codes
    assert h.recorder.run_docs == {}

    cyclic = b.graph([b.node("a"), b.node("b")], [b.edge("a", "b"), b.edge("b", "a")])
    with pytest.raises(GraphValidationError):
        await rt.start(cyclic)

    unknown = b.graph([b.node("a", type="nope")], [], entries=["a"])
    with pytest.raises(GraphValidationError):
        await rt.start(unknown)
    with pytest.raises(UnknownExtensionError):
        await rt.start(unknown, validate=False)


async def test_deterministic_ids_and_clock(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a")], [], entries=["a"])
    run = await h.make().run(g, run_id="run-1")
    events = h.recorder.events.list("run-1")
    assert run.id == "run-1"
    assert [e.event_id for e in events] == [f"e-{i}" for i in range(1, len(events) + 1)]
    assert [e.ts for e in events] == sorted(e.ts for e in events)


async def test_events_are_batched(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a", events=50)], [], entries=["a"])
    run = await h.make().run(g)
    deltas = [e for e in h.recorder.events.list(run.id) if e.type == "agent.text_delta"]
    assert len(deltas) == 50
    assert all(e.node_path == ["a"] and e.attempt == 1 for e in deltas)
    assert h.recorder.append_calls < 20


async def test_duplicate_active_run_id_rejected(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(b.graph([b.node("a", sleep=0.05)], [], entries=["a"]), run_id="dup")
    with pytest.raises(ValueError, match="dup"):
        await rt.start(b.graph([b.node("a")], [], entries=["a"]), run_id="dup")
    await handle.wait()
    assert rt.get("dup") is None


async def test_concurrent_runs_are_isolated(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = b.graph([b.node("a", sleep=0.01), b.node("b")], [b.edge("a", "b")], entries=["a"])
    runs = await asyncio.gather(*(rt.run(g) for _ in range(3)))
    assert len({r.id for r in runs}) == 3
    for r in runs:
        seqs = [e.seq for e in h.recorder.events.list(r.id)]
        assert seqs == list(range(1, len(seqs) + 1))


async def test_recorder_failure_surfaces_as_recorder_error(h: Harness, b: Builders) -> None:
    from agent_console_runtime import RecorderError

    def broken(_events: Any) -> int:
        raise OSError("disk full")

    h.recorder.events.append_many = broken  # type: ignore[method-assign,assignment]
    with pytest.raises(RecorderError) as info:
        await h.make().start(b.graph([b.node("a")], [], entries=["a"]))
    assert isinstance(info.value.__cause__, OSError)
    assert h.sink.events == []  # 저장 실패한 이벤트는 발행하지 않는다


# ---------------------------------------------------------------- 실패 요약 3단 규칙(5.2R.5)


async def test_failure_summary_names_node_by_label_and_keeps_id_in_details(
    h: Harness, b: Builders
) -> None:
    node = b.node("n1", fail=True).model_copy(update={"label": "안내원"})
    run = await h.make().run(b.graph([node], [], entries=["n1"]))
    assert run.error is not None
    assert run.error.message == "'안내원' 실패: boom"
    assert "n1" not in run.error.message
    assert run.error.details["node_id"] == "n1"
    assert run.error.details["node_name"] == "안내원"
    assert run.error.fix is None


async def test_failure_summary_uses_name_hook_then_type_title(h: Harness, b: Builders) -> None:
    run = await h.make().run(b.graph([b.node("n1", fail=True, name="검토자")], [], entries=["n1"]))
    assert run.error is not None
    assert run.error.message == "'검토자' 실패: boom"
    h2 = make_harness()
    run2 = await h2.make().run(b.graph([b.node("n2", fail=True)], [], entries=["n2"]))
    assert run2.error is not None
    assert run2.error.message == "'테스트 단계' 실패: boom"


async def test_failure_summary_carries_cause_fix(h: Harness, b: Builders) -> None:
    fix = {"actions": [{"label": "고치기", "target": {"role": "settings", "section": "common"}}]}
    run = await h.make().run(b.graph([b.node("n1", fail=True, fix=fix)], [], entries=["n1"]))
    assert run.error is not None
    assert run.error.fix is not None
    assert run.error.fix.actions[0].label == "고치기"
    assert run.error.model_dump(mode="json")["fix"]["actions"][0]["target"]["role"] == "settings"
