"""실행 중 상호작용: 대기·재개·응답·시간 제한·취소·재시작 복구(design §R14.5, 작업 1R.28).

모든 테스트는 테스트 전용 종류(`t.ask`·`t.pick`, 또는 그 자리에서 만든 임의 이름)만 쓴다.
엔진은 종류 이름을 모른다.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from importlib.metadata import EntryPoint
from typing import Any

import pytest

from agent_console_contracts import (
    Interaction,
    InteractionGrant,
    InteractionKindDescriptor,
    InteractionSettings,
    Run,
)
from agent_console_runtime import (
    INTERACTION_KINDS_GROUP,
    REDACTED,
    RESERVED_EVENT_PREFIXES,
    EnvSecretProvider,
    GraphRuntime,
    InteractionClosedError,
    InteractionOutcome,
    InteractionRequest,
    InteractivePort,
    NodeContext,
    NodeResult,
    Registries,
    ResponseValidationError,
    SecretResolver,
    StaticInteractionKind,
    UnknownInteractionError,
    load_registries,
    recover_unfinished_runs,
)
from agent_console_runtime.testing import (
    ASK_KIND,
    BUILDERS,
    Builders,
    Harness,
    ManualClock,
    SequentialIds,
    make_harness,
)


@pytest.fixture
async def h() -> AsyncIterator[Harness]:
    """테스트 하네스. 끝나면 만든 런타임을 모두 정리한다(실패해도 Run이 남지 않게)."""
    harness = make_harness()
    made: list[GraphRuntime] = []
    make = harness.make

    def tracked(**kwargs: Any) -> GraphRuntime:
        runtime = make(**kwargs)
        made.append(runtime)
        return runtime

    harness.make = tracked
    yield harness
    for runtime in made:
        await asyncio.wait_for(runtime.shutdown(), 5)


@pytest.fixture
def b() -> Builders:
    return BUILDERS


async def until(cond: Callable[[], bool], *, limit: float = 5.0) -> None:
    """조건이 참이 될 때까지 이벤트 루프를 돌린다."""
    deadline = asyncio.get_running_loop().time() + limit
    while not cond():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("조건이 시간 안에 참이 되지 않았다")
        await asyncio.sleep(0.001)


async def pending_of(rt: GraphRuntime, run_id: str, count: int = 1) -> list[Interaction]:
    await until(lambda: len(rt.pending(run_id=run_id)) >= count)
    return rt.pending(run_id=run_id)


def ask_graph(b: Builders, **config: Any) -> Any:
    return b.graph([b.node("a", type="t.asker", **config)], [], entries=["a"])


def types_of(h: Harness, run_id: str) -> list[str]:
    return [e.type for e in h.recorder.events.list(run_id)]


def node_status(h: Harness, run_id: str) -> dict[str, str]:
    return {n.node_id: n.status for n in h.recorder.runs.list_node_runs(run_id)}


# ---------------------------------------------------------------- 기본 흐름


async def test_request_waits_and_resumes_after_response(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = ask_graph(b, asks=[{"title": "이름?", "message": "알려 주세요", "payload": {"q": 1}}])
    handle = await rt.start(g)
    [pending] = await pending_of(rt, handle.run_id)

    assert pending.status == "pending"
    assert pending.kind == "t.ask"
    assert pending.node_id == "a"
    assert pending.node_path == ["a"]
    assert pending.response_schema == ASK_KIND.response_schema  # 디스크립터 기본값
    await until(lambda: handle.run.status == "waiting")
    await until(lambda: node_status(h, handle.run_id).get("a") == "waiting")
    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert stored.status == "pending"

    answered = await rt.respond(handle.run_id, pending.id, {"answer": "철수"})
    assert answered.status == "answered"
    assert answered.answered_by == "user"
    assert answered.response == {"answer": "철수"}

    run = await handle.wait()
    assert run.status == "completed"
    [node_run] = [n for n in h.recorder.runs.list_node_runs(run.id) if n.node_id == "a"]
    [outcome] = node_run.outputs["out"]
    assert outcome == {
        "interaction_id": pending.id,
        "status": "answered",
        "response": {"answer": "철수"},
        "reason": None,
    }
    types = types_of(h, run.id)
    expected = [
        "node.started",
        "interaction.requested",
        "node.waiting",
        "run.waiting",
        "interaction.answered",
        "node.resumed",
        "run.resumed",
        "node.completed",
    ]
    picked = [t for t in types if t in expected]
    assert picked == expected
    # 저장 후 발행
    assert all(h.sink.stored_at_publish)
    events = {e.type: e for e in h.recorder.events.list(run.id)}
    wait = events["node.waiting"].payload["wait"]
    assert wait["reason"] == "t.ask"
    assert wait["data"] == {"interaction_ids": [pending.id]}
    assert events["node.resumed"].payload["status"] == "running"
    assert isinstance(events["node.resumed"].payload["waited_ms"], int)
    assert events["interaction.answered"].payload["answered_by"] == "user"
    assert rt.pending() == []


async def test_engine_does_not_know_kind_names(h: Harness, b: Builders) -> None:
    """그 자리에서 만든 임의 이름의 종류로도 같은 흐름이 돈다."""
    kind_id = f"x-{uuid.uuid4().hex}"
    descriptor = InteractionKindDescriptor(
        id=kind_id,
        title="임의 종류",
        response_schema={"type": "object", "required": ["ok"]},
        expire_response={"ok": False},
    )
    h.registries.interaction_kinds.register(kind_id, StaticInteractionKind(descriptor))
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{"kind": kind_id}]))
    [pending] = await pending_of(rt, handle.run_id)
    assert pending.kind == kind_id
    with pytest.raises(ResponseValidationError):
        await rt.respond(handle.run_id, pending.id, {"nope": 1})
    await rt.respond(handle.run_id, pending.id, {"ok": True})
    run = await handle.wait()
    assert run.status == "completed"


async def test_unregistered_kind_fails_node(h: Harness, b: Builders) -> None:
    rt = h.make()
    run = await rt.run(ask_graph(b, asks=[{"kind": "not-registered"}]))
    assert run.status == "failed"
    assert node_status(h, run.id)["a"] == "failed"


def test_context_satisfies_interactive_port() -> None:
    assert issubclass(NodeContext, InteractivePort)
    assert "interaction." in RESERVED_EVENT_PREFIXES


async def test_nodes_cannot_emit_interaction_events(h: Harness, b: Builders) -> None:
    class Emitter:
        descriptor = h.registries.node_types.get("t.step").descriptor.model_copy(
            update={"id": "t.emitter"}
        )

        def resolve_ports(self, config: Any) -> Any:
            return h.registries.node_types.get("t.step").resolve_ports(config)

        def validate(self, config: Any, ctx: Any) -> list[Any]:
            return []

        async def execute(self, ctx: NodeContext, inputs: Any) -> NodeResult:
            await ctx.emit("interaction.answered", {"interaction_id": "x", "kind": "k"})
            return NodeResult(status="succeeded")

    h.registries.node_types.register("t.emitter", Emitter())
    rt = h.make()
    run = await rt.run(b.graph([b.node("e", type="t.emitter")], [], entries=["e"]))
    assert run.status == "failed"
    [nr] = h.recorder.runs.list_node_runs(run.id)
    assert nr.error is not None
    assert "엔진 전용" in nr.error.message


async def test_request_specific_schema_and_subagent_attribution(h: Harness, b: Builders) -> None:
    rt = h.make()
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    g = ask_graph(
        b,
        actor="lead",
        asks=[{"kind": "t.pick", "response_schema": schema, "child": "be", "actor": "backend"}],
    )
    handle = await rt.start(g)
    [pending] = await pending_of(rt, handle.run_id)
    assert pending.node_path == ["a", "be"]
    assert pending.actor == "backend"
    assert pending.response_schema == schema
    with pytest.raises(ResponseValidationError) as info:
        await rt.respond(handle.run_id, pending.id, {"n": "x"})
    assert info.value.issues[0].path == "/n"
    await rt.respond(handle.run_id, pending.id, {"n": 3})
    await handle.wait()
    requested = next(
        e for e in h.recorder.events.list(handle.run_id) if e.type == "interaction.requested"
    )
    assert requested.node_path == ["a", "be"]
    assert requested.actor == "backend"


async def test_bad_child_path_is_rejected(h: Harness, b: Builders) -> None:
    class BadPath:
        descriptor = h.registries.node_types.get("t.asker").descriptor.model_copy(
            update={"id": "t.badpath"}
        )

        def resolve_ports(self, config: Any) -> Any:
            return h.registries.node_types.get("t.asker").resolve_ports(config)

        def validate(self, config: Any, ctx: Any) -> list[Any]:
            return []

        async def execute(self, ctx: NodeContext, inputs: Any) -> NodeResult:
            await ctx.request_input(InteractionRequest(kind="t.ask", node_path=["other"]))
            return NodeResult(status="succeeded")

    h.registries.node_types.register("t.badpath", BadPath())
    run = await h.make().run(b.graph([b.node("x", type="t.badpath")], [], entries=["x"]))
    assert node_status(h, run.id)["x"] == "failed"
    assert h.recorder.interaction_docs == {}


# ---------------------------------------------------------------- 여러 요청·동시 실행 한도


async def test_one_node_can_hold_several_requests(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = ask_graph(b, parallel=True, asks=[{"title": "1"}, {"title": "2"}])
    handle = await rt.start(g)
    first, second = await pending_of(rt, handle.run_id, 2)
    await rt.respond(handle.run_id, first.id, {"answer": "a"})
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    # 열린 요청이 남아 있으면 노드는 여전히 waiting
    assert node_status(h, handle.run_id)["a"] == "waiting"
    assert "node.resumed" not in types_of(h, handle.run_id)
    await rt.respond(handle.run_id, second.id, {"answer": "b"})
    run = await handle.wait()
    assert run.status == "completed"
    types = types_of(h, run.id)
    assert types.count("node.resumed") == 1
    assert types.count("node.waiting") == 2
    waits = [e for e in h.recorder.events.list(run.id) if e.type == "node.waiting"]
    assert waits[-1].payload["wait"]["data"]["interaction_ids"] == [first.id, second.id]


async def test_waiting_releases_concurrency_slot(h: Harness, b: Builders) -> None:
    """max_concurrency=1이어도 기다리는 노드가 다른 노드를 막지 않는다(데드락 없음)."""
    rt = h.make(max_concurrency=1)
    g = b.graph(
        [
            b.node("a1", type="t.asker", asks=[{"title": "1"}]),
            b.node("a2", type="t.asker", asks=[{"title": "2"}]),
            b.node("s"),
        ],
        [],
        entries=["a1", "a2", "s"],
    )
    handle = await rt.start(g)
    found = await pending_of(rt, handle.run_id, 2)  # 두 질문 노드가 동시에 대기
    await until(lambda: node_status(h, handle.run_id).get("s") == "succeeded")
    for item in found:
        await rt.respond(handle.run_id, item.id, {"answer": item.node_id})
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "completed"
    assert node_status(h, run.id) == {"a1": "succeeded", "a2": "succeeded", "s": "succeeded"}


async def test_run_waiting_only_when_nothing_runs(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = b.graph(
        [b.node("q", type="t.asker", asks=[{}]), b.node("slow", hang=True)],
        [],
        entries=["q", "slow"],
    )
    handle = await rt.start(g)
    [pending] = await pending_of(rt, handle.run_id)
    await h.probe.started_event("slow").wait()
    await asyncio.sleep(0.01)
    assert handle.run.status == "running"  # slow가 아직 running
    assert "run.waiting" not in types_of(h, handle.run_id)
    handle.cancel()
    run = await handle.wait()
    assert run.status == "cancelled"
    closed = h.recorder.interactions.get(pending.id)
    assert closed is not None
    assert closed.status == "cancelled"
    assert closed.close_reason == "cancelled"


# ---------------------------------------------------------------- 응답 경합·닫힌 요청


async def test_concurrent_responses_only_one_wins(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{}]))
    [pending] = await pending_of(rt, handle.run_id)
    results = await asyncio.gather(
        rt.respond(handle.run_id, pending.id, {"answer": "one"}),
        rt.respond(handle.run_id, pending.id, {"answer": "two"}),
        return_exceptions=True,
    )
    wins = [r for r in results if isinstance(r, Interaction)]
    losses = [r for r in results if isinstance(r, InteractionClosedError)]
    assert len(wins) == 1
    assert len(losses) == 1
    assert losses[0].interaction.status == "answered"
    assert losses[0].interaction.response == wins[0].response
    await handle.wait()
    assert types_of(h, handle.run_id).count("interaction.answered") == 1


async def test_closed_and_unknown_interactions(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{}]))
    [pending] = await pending_of(rt, handle.run_id)
    with pytest.raises(UnknownInteractionError):
        await rt.respond(handle.run_id, "nope", {"answer": "x"})
    await rt.respond(handle.run_id, pending.id, {"answer": "x"})
    with pytest.raises(InteractionClosedError):
        await rt.respond(handle.run_id, pending.id, {"answer": "y"})
    await handle.wait()
    # 실행이 끝난 뒤: 저장소 기준으로 닫힘
    with pytest.raises(InteractionClosedError) as info:
        await rt.respond(handle.run_id, pending.id, {"answer": "z"})
    assert info.value.interaction.status == "answered"
    with pytest.raises(UnknownInteractionError):
        await rt.respond("other-run", pending.id, {"answer": "z"})


async def test_store_conflict_is_reported_as_closed(h: Harness, b: Builders) -> None:
    """다른 쪽이 저장소에서 먼저 닫았으면(조건부 갱신 실패) 응답은 InteractionClosedError."""
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{}]))
    [pending] = await pending_of(rt, handle.run_id)
    await until(lambda: h.recorder.interactions.get(pending.id) is not None)
    h.recorder.interactions.close(
        pending.id, status="expired", closed_at=1.0, answered_by="system", close_reason="x"
    )
    with pytest.raises(InteractionClosedError) as info:
        await rt.respond(handle.run_id, pending.id, {"answer": "late"})
    assert info.value.interaction.status == "expired"
    run = await handle.wait()
    assert run.status == "completed"  # 요청자는 먼저 저장된 결과(만료)를 받고 이어 간다
    [node_run] = [n for n in h.recorder.runs.list_node_runs(run.id) if n.node_id == "a"]
    assert node_run.outputs["out"][0]["status"] == "expired"


# ---------------------------------------------------------------- 시간 제한


async def _started(rt: GraphRuntime, graph: Any, **opts: Any) -> tuple[Any, Interaction]:
    handle = await rt.start(graph, **opts)
    [pending] = await pending_of(rt, handle.run_id)
    return handle, pending


@pytest.mark.parametrize(
    ("request_timeout", "grant_timeout", "settings_timeout", "expected"),
    [
        (10.0, 50.0, 100.0, 10.0),
        (None, 50.0, 100.0, 50.0),
        (None, None, 100.0, 100.0),
        (None, None, None, None),
    ],
)
async def test_timeout_precedence(
    h: Harness,
    b: Builders,
    request_timeout: float | None,
    grant_timeout: float | None,
    settings_timeout: float | None,
    expected: float | None,
) -> None:
    clock = ManualClock(start=1_000.0)
    rt = h.make(
        clock=clock,
        sleep=clock.sleep,
        interaction_settings=InteractionSettings(timeout_seconds=settings_timeout),
    )
    ask: dict[str, Any] = {}
    if request_timeout is not None:
        ask["timeout_seconds"] = request_timeout
    grants = {"a": InteractionGrant(kinds=["t.ask"], timeout_seconds=grant_timeout)}
    handle, pending = await _started(rt, ask_graph(b, asks=[ask]), interaction_grants=grants)
    assert pending.expires_at == (None if expected is None else 1_000.0 + expected)
    if expected is None:
        assert clock.sleepers == 0
        handle.cancel()
        await handle.wait()
        return
    await clock.advance(expected - 1)
    assert rt.pending(run_id=handle.run_id) != []
    await clock.advance(1)
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "completed"
    closed = h.recorder.interactions.get(pending.id)
    assert closed is not None
    assert (closed.status, closed.close_reason, closed.answered_by) == (
        "expired",
        "timeout",
        "timeout",
    )
    [node_run] = [n for n in h.recorder.runs.list_node_runs(run.id) if n.node_id == "a"]
    assert node_run.outputs["out"][0] == {
        "interaction_id": pending.id,
        "status": "expired",
        "response": ASK_KIND.expire_response,
        "reason": "timeout",
    }
    closed_event = next(e for e in h.recorder.events.list(run.id) if e.type == "interaction.closed")
    assert closed_event.payload == {
        "interaction_id": pending.id,
        "kind": "t.ask",
        "status": "expired",
        "reason": "timeout",
    }


async def test_grant_is_visible_to_node(h: Harness, b: Builders) -> None:
    seen: list[InteractionGrant | None] = []

    class Peek:
        descriptor = h.registries.node_types.get("t.step").descriptor.model_copy(
            update={"id": "t.peek"}
        )

        def resolve_ports(self, config: Any) -> Any:
            return h.registries.node_types.get("t.step").resolve_ports(config)

        def validate(self, config: Any, ctx: Any) -> list[Any]:
            return []

        async def execute(self, ctx: NodeContext, inputs: Any) -> NodeResult:
            seen.append(ctx.interaction_grant)
            return NodeResult(status="succeeded")

    h.registries.node_types.register("t.peek", Peek())
    grant = InteractionGrant(kinds=["anything"])
    await h.make().run(
        b.graph([b.node("p", type="t.peek")], [], entries=["p"]),
        interaction_grants={"p": grant},
    )
    assert seen == [grant]


async def test_timeout_cancel_run(h: Harness, b: Builders) -> None:
    clock = ManualClock()
    rt = h.make(clock=clock, sleep=clock.sleep)
    g = ask_graph(b, asks=[{"timeout_seconds": 5, "on_timeout": "cancel_run"}])
    handle, pending = await _started(rt, g)
    await clock.advance(5)
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"
    assert run.error is not None
    assert run.error.message == "interaction_timeout"
    closed = h.recorder.interactions.get(pending.id)
    assert closed is not None
    assert (closed.status, closed.close_reason, closed.answered_by) == (
        "cancelled",
        "timeout",
        "timeout",
    )
    assert node_status(h, run.id)["a"] == "cancelled"


async def test_settings_on_timeout_cancel_run_is_used(h: Harness, b: Builders) -> None:
    clock = ManualClock()
    settings = InteractionSettings(timeout_seconds=3, on_timeout="cancel_run")
    rt = h.make(clock=clock, sleep=clock.sleep)
    handle, _ = await _started(rt, ask_graph(b, asks=[{}]), interaction_settings=settings)
    await clock.advance(3)
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"


# ---------------------------------------------------------------- 취소·노드 종료


async def test_cancel_closes_open_requests(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{}]))
    [pending] = await pending_of(rt, handle.run_id)
    handle.cancel("사용자 취소")
    run = await handle.wait()
    assert run.status == "cancelled"
    closed = h.recorder.interactions.get(pending.id)
    assert closed is not None
    assert (closed.status, closed.close_reason) == ("cancelled", "cancelled")
    assert node_status(h, run.id)["a"] == "cancelled"
    types = types_of(h, run.id)
    assert types.index("interaction.closed") < types.index("node.cancelled")
    assert types[-1] == "run.cancelled"


async def test_node_finishing_while_waiting_closes_requests(h: Harness, b: Builders) -> None:
    rt = h.make()
    run = await rt.run(ask_graph(b, background=True, asks=[{}]))
    assert run.status == "completed"
    assert node_status(h, run.id)["a"] == "succeeded"
    [doc] = h.recorder.interaction_docs.values()
    assert (doc.status, doc.close_reason) == ("cancelled", "node_finished")
    [task] = h.probe.background
    outcome = await task
    assert isinstance(outcome, InteractionOutcome)
    assert (outcome.status, outcome.reason) == ("cancelled", "node_finished")
    assert outcome.response == ASK_KIND.expire_response
    assert "node.resumed" not in types_of(h, run.id)


# ---------------------------------------------------------------- 비밀 가림


async def test_payload_and_response_secrets_are_redacted(h: Harness, b: Builders) -> None:
    secret = "s3cr3t-value"
    resolver = SecretResolver([EnvSecretProvider({"TOKEN": secret})])
    rt = h.make(secrets=resolver)
    g = ask_graph(b, secret="secret://TOKEN", asks=[{"title": f"키 {secret}?"}])
    handle = await rt.start(g)
    [pending] = await pending_of(rt, handle.run_id)
    assert pending.payload == {"secret": REDACTED}
    assert pending.title == f"키 {REDACTED}?"
    answered = await rt.respond(handle.run_id, pending.id, {"answer": f"use {secret}"})
    assert answered.response == {"answer": f"use {REDACTED}"}
    run = await handle.wait()

    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert secret not in stored.model_dump_json()
    for event in h.recorder.events.list(run.id):
        assert secret not in event.model_dump_json()
    # 요청자(메모리)는 원문을 받는다(하류로 넘어가는 값은 가리지 않음, §4.8). 저장본은 가려진다.
    [node_run] = [n for n in h.recorder.runs.list_node_runs(run.id) if n.node_id == "a"]
    assert node_run.outputs["out"][0]["response"] == {"answer": f"use {REDACTED}"}


async def test_outcome_keeps_original_response(h: Harness, b: Builders) -> None:
    secret = "another-secret"
    resolver = SecretResolver([EnvSecretProvider({"K": secret})])
    got: list[InteractionOutcome] = []

    class Keep:
        descriptor = h.registries.node_types.get("t.step").descriptor.model_copy(
            update={"id": "t.keep"}
        )

        def resolve_ports(self, config: Any) -> Any:
            return h.registries.node_types.get("t.step").resolve_ports(config)

        def validate(self, config: Any, ctx: Any) -> list[Any]:
            return []

        async def execute(self, ctx: NodeContext, inputs: Any) -> NodeResult:
            ctx.secrets.resolve("secret://K")
            got.append(await ctx.request_input(InteractionRequest(kind="t.ask")))
            return NodeResult(status="succeeded")

    h.registries.node_types.register("t.keep", Keep())
    rt = h.make(secrets=resolver)
    handle = await rt.start(b.graph([b.node("k", type="t.keep")], [], entries=["k"]))
    [pending] = await pending_of(rt, handle.run_id)
    await rt.respond(handle.run_id, pending.id, {"answer": secret})
    await handle.wait()
    assert got[0].response == {"answer": secret}


# ---------------------------------------------------------------- 재시작 복구


async def test_recover_expires_pending_interactions(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{}]))
    [pending] = await pending_of(rt, handle.run_id)
    await until(lambda: node_status(h, handle.run_id).get("a") == "waiting")
    # 서버 프로세스가 사라진 것처럼: 저장소 상태만 남기고 새로 복구한다.
    recorder = h.recorder
    published: list[Any] = []

    class Sink:
        def publish(self, event: Any) -> None:
            published.append(event)

    ids = recover_unfinished_runs(
        recorder, clock=lambda: 9_999.0, ids=SequentialIds("r"), sink=Sink()
    )
    assert ids == [handle.run_id]
    closed = recorder.interactions.get(pending.id)
    assert closed is not None
    assert (closed.status, closed.close_reason, closed.answered_by) == (
        "expired",
        "interrupted",
        "system",
    )
    node_runs = {n.node_id: n for n in recorder.runs.list_node_runs(handle.run_id)}
    assert node_runs["a"].status == "cancelled"
    assert node_runs["a"].error is not None
    assert node_runs["a"].error.code == "interrupted"
    tail = [e.type for e in published]
    assert tail == ["interaction.closed", "node.cancelled", "run.interrupted"]
    seqs = [e.seq for e in recorder.events.list(handle.run_id)]
    assert seqs == sorted(set(seqs))
    # 이 프로세스의 엔진 정리: 저장소에서 이미 닫힌 요청은 충돌로 보고 조용히 넘어간다.
    handle.cancel()
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"


def test_recover_closes_orphan_pending_of_finished_run() -> None:
    from agent_console_runtime.testing import InMemoryRecorder

    rec = InMemoryRecorder()
    rec.runs.save(
        Run(
            id="done",
            graph_id="g",
            graph_version="v",
            status="completed",
            input={},
            origin="api",
            created_at=1.0,
        )
    )
    rec.interactions.save(
        Interaction(id="i1", run_id="done", node_id="a", kind="k", status="pending", created_at=1.0)
    )
    assert recover_unfinished_runs(rec, clock=lambda: 5.0, ids=SequentialIds("x")) == []
    doc = rec.interactions.get("i1")
    assert doc is not None
    assert doc.status == "expired"
    assert [e.type for e in rec.events.list("done")] == ["interaction.closed"]
    run = rec.runs.get("done")
    assert run is not None
    assert run.status == "completed"


# ---------------------------------------------------------------- X15 등록


def test_interaction_kinds_load_from_entry_points() -> None:
    regs = Registries()
    eps = [
        EntryPoint(
            name="t.ask",
            value="agent_console_runtime.testing:ASK_KIND",
            group=INTERACTION_KINDS_GROUP,
        ),
        EntryPoint(
            name="t.broken",
            value="agent_console_runtime.testing:PROBE",
            group=INTERACTION_KINDS_GROUP,
        ),
    ]
    reports = load_registries(regs, entry_points=eps)
    status = {r.key: r.ok for r in reports}
    assert status == {"t.ask": True, "t.broken": False}
    assert regs.interaction_kinds.get("t.ask").descriptor == ASK_KIND
    assert regs.extension("interaction_kinds") is regs.interaction_kinds


# ---------------------------------------------------------------- Run 메타(conversation_id)


async def test_conversation_id_is_recorded_on_run_and_interactions(h: Harness, b: Builders) -> None:
    """`start(conversation_id=)`는 Run 메타로 기록되고 그 Run의 상호작용에 그대로
    복사된다(1R.14).
    """
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{"title": "?"}]), conversation_id="conv-1")
    assert handle.run.conversation_id == "conv-1"
    [pending] = await pending_of(rt, handle.run_id)
    assert pending.conversation_id == "conv-1"
    stored_run = h.recorder.runs.get(handle.run_id)
    assert stored_run is not None
    assert stored_run.conversation_id == "conv-1"
    await rt.respond(handle.run_id, pending.id, {"answer": "네"})
    run = await handle.wait()
    assert run.conversation_id == "conv-1"
    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert stored.conversation_id == run.conversation_id

    plain = await rt.start(ask_graph(b, asks=[]))
    assert plain.run.conversation_id is None
    await plain.wait()


async def test_shutdown_with_timeout_forces_waiting_runs(h: Harness, b: Builders) -> None:
    """`shutdown(timeout=0)`: 협조적 취소를 기다리지 않고 태스크를 취소하되, 정리 기록은 끝낸다."""
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{"title": "?"}]))
    [pending] = await pending_of(rt, handle.run_id)
    finished = await rt.shutdown(timeout=0)
    assert finished is False
    assert handle.done()
    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert stored.status == "cancelled"
    run = h.recorder.runs.get(handle.run_id)
    assert run is not None
    assert run.status == "cancelled"
    assert await rt.shutdown(timeout=0) is True  # 실행 중인 Run이 없으면 바로 참


@pytest.mark.parametrize("timeout", [None, 0])
async def test_shutdown_interrupt_matches_restart_recovery(
    h: Harness, b: Builders, timeout: float | None
) -> None:
    """`shutdown(interrupt=True)`(서버 정상 종료): 취소가 아니라 재시작 복구와 같은 "끊김"(1R.26).

    Run `interrupted`(error.code `interrupted`), 대기 노드 `cancelled`(interrupted), 요청
    `expired`(close_reason `interrupted`). 강제 취소(timeout=0) 경로도 같다.
    """
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{"title": "?"}]))
    [pending] = await pending_of(rt, handle.run_id)
    await rt.shutdown("서버 종료", timeout=timeout, interrupt=True)
    assert handle.done()
    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert (stored.status, stored.close_reason) == ("expired", "interrupted")
    run = h.recorder.runs.get(handle.run_id)
    assert run is not None
    assert run.status == "interrupted"
    assert run.error is not None
    assert (run.error.code, run.error.message) == ("interrupted", "서버 종료")
    nodes = h.recorder.runs.list_node_runs(handle.run_id)
    assert {n.status for n in nodes} <= {"cancelled", "skipped", "succeeded"}
    cancelled = [n for n in nodes if n.status == "cancelled"]
    assert cancelled
    assert all(n.error is not None and n.error.code == "interrupted" for n in cancelled)
    types = [e.type for e in h.recorder.events.list(handle.run_id)]
    assert types[-1] == "run.interrupted"
    assert "interaction.closed" in types


async def test_interrupt_after_cancel_keeps_cancelled(h: Harness, b: Builders) -> None:
    """이미 취소 요청된 Run은 끊김으로 바꾸지 않는다(사용자 취소가 우선)."""
    rt = h.make()
    handle = await rt.start(ask_graph(b, asks=[{"title": "?"}]))
    await pending_of(rt, handle.run_id)
    assert handle.cancel("user") is True
    assert handle.interrupt() is False
    run = await handle.wait()
    assert run.status == "cancelled"


async def test_extra_redact_hides_unresolved_plain_tokens(h: Harness, b: Builders) -> None:
    """2R.4: 해석하지 않은 평문(예: 프롬프트에 붙인 토큰)은 앱이 넣은 `extra_redact`로 가린다.

    엔진은 의심 규칙을 모른다 — 문자열 함수만 받는다(서버는 `ac-secret-rules`를 넣는다)."""
    plain = "PLAIN-TOKEN-123"
    resolver = SecretResolver(extra_redact=lambda text: text.replace(plain, "[SUSPECTED]"))
    rt = h.make(secrets=resolver)
    handle = await rt.start(ask_graph(b, asks=[{"title": f"키 {plain}?"}]))
    [pending] = await pending_of(rt, handle.run_id)
    assert pending.title == "키 [SUSPECTED]?"
    await rt.respond(handle.run_id, pending.id, {"answer": f"use {plain}"})
    run = await handle.wait()
    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert plain not in stored.model_dump_json()
    events = h.recorder.events.list(run.id)
    assert events
    assert all(plain not in e.model_dump_json() for e in events)
    # 함수가 없으면(가림 끔) 원문 그대로 남는다
    assert SecretResolver().redact({"t": plain}) == {"t": plain}


async def test_request_copies_node_label_for_display(h: Harness, b: Builders) -> None:
    """엔진이 상호작용을 열 때 노드 label(없으면 id)을 `node_label`에 복사한다(2R.7, D6b)."""
    rt = h.make()
    labeled = b.node("a", type="t.asker", asks=[{"title": "?"}]).model_copy(
        update={"label": "검토 지점"}
    )
    plain = b.node("c", type="t.asker", asks=[{"title": "?"}])
    g = b.graph([labeled, plain], [], entries=["a", "c"])
    handle = await rt.start(g)
    pending = await pending_of(rt, handle.run_id, 2)
    labels = {p.node_id: p.node_label for p in pending}
    assert labels == {"a": "검토 지점", "c": "c"}  # label이 없으면 id
    for p in pending:
        pid = p.id
        await until(lambda pid=pid: h.recorder.interactions.get(pid) is not None)  # type: ignore[misc]
        stored = h.recorder.interactions.get(pid)
        assert stored is not None
        assert stored.node_label == labels[p.node_id]

    def requested_labels() -> list[Any]:
        return [
            e.payload["interaction"]["node_label"]
            for e in h.recorder.events.list(handle.run_id)
            if e.type == "interaction.requested"
        ]

    # 이벤트 기록은 비동기라 두 요청 이벤트가 모두 저장될 때까지 기다린다
    await until(lambda: len(requested_labels()) == 2)
    requested = requested_labels()
    assert sorted(str(x) for x in requested) == sorted(str(x) for x in labels.values())
    for p in pending:
        await rt.respond(handle.run_id, p.id, {"answer": "ok"})
    await handle.wait()
