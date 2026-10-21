"""끊긴 실행 이어 가기(2R.14, design §2R.10): `start(seed=)`, 선택지·검사, `ResumeService`.

엔진이 노드 이름을 모른다는 것을 테스트 전용 타입(`t.step`, 이 파일의 `t.redo`)으로 보인다.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_console_contracts import (
    ErrorCodes,
    ErrorInfo,
    Graph,
    NodeRun,
    NodeTypeDescriptor,
    Run,
    RunEvent,
)
from agent_console_runtime import (
    GraphRuntime,
    GraphValidationError,
    ResumeIssueCodes,
    ResumeRunNotFoundError,
    ResumeService,
    ResumeStart,
    RunNotResumableError,
    RuntimeIssueCodes,
    SkipReasons,
    interrupted_status,
    resume_issues,
    resume_options,
    resume_seed,
)
from agent_console_runtime.testing import (
    BUILDERS,
    AskerNode,
    Builders,
    Harness,
    SequentialIds,
    make_harness,
)


class RedoAsker(AskerNode):
    """다시 실행할 수 있다고 선언한 질문 노드(이름은 아무것이나 — 엔진은 모른다)."""

    descriptor = AskerNode.descriptor.model_copy(update={"id": "t.redo", "rerunnable": True})


@pytest.fixture
def h() -> Harness:
    harness = make_harness()
    harness.registries.node_types.register("t.redo", RedoAsker())
    return harness


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def _statuses(h: Harness, run_id: str) -> dict[str, str]:
    return {nr.node_id: nr.status for nr in h.recorder.runs.list_node_runs(run_id)}


def _skips(h: Harness, run_id: str) -> dict[str, Any]:
    return {
        e.node_path[0]: e.payload.get("reason")
        for e in h.recorder.events.list(run_id)
        if e.type == "node.skipped"
    }


def _descriptors(h: Harness) -> list[NodeTypeDescriptor]:
    return [e.item.descriptor for e in h.registries.node_types.list()]


async def _pending(rt: GraphRuntime, run_id: str) -> list[Any]:
    for _ in range(500):
        found = rt.pending(run_id=run_id)
        if found:
            return found
        await asyncio.sleep(0)
    raise AssertionError("대기 요청이 열리지 않았다")


# ---------------------------------------------------------------- 엔진 start(seed=)


async def test_seed_skips_upstream_and_runs_downstream(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "A"}), b.node("b"), b.node("c")],
        [b.edge("a", "b"), b.edge("b", "c")],
        entries=["a"],
    )
    rt = h.make()
    handle = await rt.start(
        g, {"text": "원래"}, origin="resume", seed={"b": {"in": "저장"}}, resumed_from="old"
    )
    run = await handle.wait()
    assert run.status == "completed"
    assert run.resumed_from == "old"
    assert run.origin == "resume"
    assert _statuses(h, run.id) == {"a": "skipped", "b": "succeeded", "c": "succeeded"}
    assert _skips(h, run.id) == {"a": SkipReasons.RESUMED}
    # a는 실행하지 않았고 b는 저장된 입력으로 시작했다
    assert [c[0] for c in h.probe.calls] == ["b", "c"]
    assert h.probe.calls[0] == ("b", {"in": "저장"})


async def test_seed_parallel_branch_is_dead_path_not_resumed(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "A"}), b.node("b"), b.node("c")],
        [b.edge("a", "b"), b.edge("a", "c")],
        entries=["a"],
    )
    run = await h.make().run(g, {}, seed={"b": {"in": 1}})
    assert _statuses(h, run.id) == {"a": "skipped", "b": "succeeded", "c": "skipped"}
    assert _skips(h, run.id) == {"a": "resumed", "c": None}


async def test_seed_must_name_scheduled_nodes(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a")], [], entries=["a"])
    rt = h.make()
    with pytest.raises(GraphValidationError) as caught:
        await rt.start(g, {}, seed={"you": {}, "ghost": {}})
    assert {(i.code, i.node_id) for i in caught.value.issues} == {
        (RuntimeIssueCodes.SEED_NOT_SCHEDULED, "you"),
        (RuntimeIssueCodes.SEED_NOT_SCHEDULED, "ghost"),
    }
    with pytest.raises(GraphValidationError):
        await rt.start(g, {}, seed={})
    assert h.recorder.runs.list() == []  # Run을 만들지 않았다


# ---------------------------------------------------------------- 순수 함수


def _node_run(node_id: str, status: str, **extra: Any) -> NodeRun:
    return NodeRun.model_validate({"run_id": "r", "node_id": node_id, "status": status, **extra})


def _event(seq: int, node_id: str, status: str) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}",
        run_id="r",
        seq=seq,
        ts=float(seq),
        type=f"node.{status}",
        node_path=[node_id],
        payload={"status": status},
    )


INTERRUPTED = ErrorInfo(code="interrupted", message="끊김")


def test_interrupted_status_reads_last_status_before_cancel() -> None:
    nr = _node_run("q", "cancelled", error=INTERRUPTED.model_dump())
    events = [_event(1, "q", "queued"), _event(2, "q", "running"), _event(3, "q", "waiting")]
    assert interrupted_status(nr, [*events, _event(4, "q", "cancelled")]) == "waiting"
    assert interrupted_status(nr, []) == "running"
    assert interrupted_status(_node_run("q", "waiting"), []) == "waiting"
    user_cancel = _node_run("q", "cancelled", error={"code": "cancelled", "message": "x"})
    assert interrupted_status(user_cancel, events) is None
    assert interrupted_status(_node_run("q", "succeeded"), events) is None


def test_resume_options_issues_and_seed(b: Builders) -> None:
    g = Graph(
        id="g",
        name="g",
        nodes=[
            b.node("a").model_copy(update={"label": "A"}),
            b.node("q", type="t.redo").model_copy(update={"label": "검토"}),
            b.node("s", type="t.other"),
        ],
    )
    run = Run(
        id="r",
        graph_id="g",
        graph_version="v",
        status="interrupted",
        input={},
        origin="api",
        created_at=1.0,
    )
    node_runs = [
        _node_run("a", "succeeded"),
        _node_run("s", "cancelled", error=INTERRUPTED.model_dump(), node_type="t.other"),
        _node_run(
            "q", "cancelled", error=INTERRUPTED.model_dump(), node_type="t.redo", inputs={"in": 7}
        ),
    ]
    descriptors = [
        NodeTypeDescriptor(id="t.redo", title="x", rerunnable=True),
        NodeTypeDescriptor(id="t.other", title="y"),
    ]
    options = resume_options(
        run, node_runs, [_event(1, "q", "waiting")], graph=g, node_types=descriptors
    )
    assert [(n.node_id, n.label, n.rerunnable, n.status) for n in options.nodes] == [
        ("q", "검토", True, "waiting"),
        ("s", None, False, "running"),
    ]
    issues = resume_issues(options, ["q", "s", "a"])
    assert [(i.node_id, i.code) for i in issues] == [
        ("s", ResumeIssueCodes.NOT_RERUNNABLE),
        ("a", ResumeIssueCodes.UNKNOWN_NODE),
    ]
    assert resume_issues(options, ["q"]) == []
    assert resume_seed(node_runs, ["q"]) == {"q": {"in": 7}}
    finished = run.model_copy(update={"status": "completed"})
    assert resume_options(finished, node_runs, [], graph=g, node_types=descriptors).nodes == []


# ---------------------------------------------------------------- 끊김 → 이어 가기(엔진 + 서비스)


async def test_interrupt_then_resume_reopens_same_request(h: Harness, b: Builders) -> None:
    ask = {"title": "검토해 주세요", "payload": {"q": 1}}
    g = b.graph(
        [b.node("a", outputs={"out": "A"}), b.node("q", type="t.redo", asks=[ask]), b.node("c")],
        [b.edge("a", "q"), b.edge("q", "c")],
        entries=["a"],
    )
    rt = h.make()
    first = await rt.start(g, {"text": "원래"})
    [opened] = await _pending(rt, first.run_id)
    assert await rt.shutdown("끊김", interrupt=True)
    interrupted = h.recorder.runs.get(first.run_id)
    assert interrupted is not None
    assert interrupted.status == "interrupted"

    rt2 = h.make(ids=SequentialIds("second-"))  # 재시작한 프로세스(이벤트 id가 겹치지 않게)
    started: list[ResumeStart] = []

    async def starter(req: ResumeStart) -> Run:
        started.append(req)
        handle = await rt2.start(
            req.graph, req.run.input, origin="resume", seed=req.seed, resumed_from=req.run.id
        )
        return handle.run

    service = ResumeService(
        h.recorder.runs,
        h.recorder.events,
        graph_of=lambda run: g if run.graph_id == g.id else None,
        node_types=lambda: _descriptors(h),
        starter=starter,
    )
    options = service.options(first.run_id)
    assert [(n.node_id, n.rerunnable, n.status) for n in options.nodes] == [("q", True, "waiting")]

    with pytest.raises(GraphValidationError) as caught:
        await service.resume(first.run_id, ["a"])
    assert caught.value.issues[0].code == ResumeIssueCodes.UNKNOWN_NODE

    new = await service.resume(first.run_id, ["q"])
    assert started[0].seed == {"q": {"in": "A"}}
    assert new.resumed_from == first.run_id
    assert new.input == {"text": "원래"}
    [reopened] = await _pending(rt2, new.id)
    assert (reopened.title, reopened.payload, reopened.kind) == (
        opened.title,
        opened.payload,
        opened.kind,
    )
    await rt2.respond(new.id, reopened.id, {"answer": "좋아요"})
    handle = rt2.get(new.id)
    assert handle is not None
    done = await handle.wait()
    assert done.status == "completed"
    assert _statuses(h, new.id) == {"a": "skipped", "q": "succeeded", "c": "succeeded"}
    assert _skips(h, new.id) == {"a": "resumed"}

    # 이미 이어 간 Run은 다시 이어 가지 않는다(선택지도 비어 있다)
    assert service.options(first.run_id).nodes == []
    with pytest.raises(RunNotResumableError) as again:
        await service.resume(first.run_id, ["q"])
    assert again.value.code == ErrorCodes.RUN_NOT_RESUMABLE
    assert again.value.details["resumed_by"] == new.id
    # 끊긴 Run이 아니면 거부
    with pytest.raises(RunNotResumableError):
        await service.resume(new.id, ["q"])
    with pytest.raises(ResumeRunNotFoundError):
        service.options("missing")


async def test_resume_needs_graph_of_that_run(h: Harness) -> None:
    h.recorder.runs.save(
        Run(
            id="r",
            graph_id="gone",
            graph_version="v",
            status="interrupted",
            input={},
            origin="api",
            created_at=1.0,
        )
    )

    async def never(req: ResumeStart) -> Run:
        raise AssertionError("시작하면 안 된다")

    service = ResumeService(
        h.recorder.runs,
        h.recorder.events,
        graph_of=lambda run: None,
        node_types=lambda: _descriptors(h),
        starter=never,
    )
    with pytest.raises(RunNotResumableError) as caught:
        await service.resume("r", ["q"])
    assert caught.value.details["graph_id"] == "gone"


async def test_child_run_is_not_resumed_on_its_own(h: Harness, b: Builders) -> None:
    """자식 Run(`root_run_id`)은 따로 이어 가지 않는다(5R.13 결정: 루트 Run을 이어 간다)."""
    g = b.graph([b.node("q", type="t.redo")], [], "child", entries=["q"])
    child = Run(
        id="child",
        graph_id="child",
        graph_version="v",
        status="interrupted",
        input={},
        origin="api",
        parent_run_id="root",
        parent_node_id="team",
        root_run_id="root",
        created_at=1.0,
    )
    h.recorder.runs.save(child)
    h.recorder.runs.save_node_run(
        _node_run("q", "cancelled", error=INTERRUPTED.model_dump(), node_type="t.redo").model_copy(
            update={"run_id": "child"}
        )
    )

    async def never(req: ResumeStart) -> Run:
        raise AssertionError("시작하면 안 된다")

    service = ResumeService(
        h.recorder.runs,
        h.recorder.events,
        graph_of=lambda run: g,
        node_types=lambda: _descriptors(h),
        starter=never,
    )
    assert service.options("child").nodes == []
    with pytest.raises(RunNotResumableError) as caught:
        await service.resume("child", ["q"])
    assert caught.value.details == {
        "run_id": "child",
        "status": "interrupted",
        "root_run_id": "root",
        "parent_run_id": "root",
    }
    # 끊기지 않은 자식 Run도 같은 거절(상태 거절보다 먼저, 이어 갈 곳이 상세에 있다 — D12)
    h.recorder.runs.save(child.model_copy(update={"status": "failed"}))
    with pytest.raises(RunNotResumableError) as again:
        await service.resume("child", ["q"])
    assert again.value.details["root_run_id"] == "root"
    assert again.value.details["parent_run_id"] == "root"
    assert again.value.details["status"] == "failed"
    # 같은 기록이 루트 Run이면 선택지가 있다
    root_like = child.model_copy(update={"root_run_id": None, "parent_run_id": None})
    options = resume_options(
        root_like,
        h.recorder.runs.list_node_runs("child"),
        [],
        graph=g,
        node_types=_descriptors(h),
    )
    assert [n.node_id for n in options.nodes] == ["q"]
