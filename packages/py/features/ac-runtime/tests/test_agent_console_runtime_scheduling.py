"""엣지 디스크립터 `scheduling`(entry·flow·exit·none)과 노드 `executable`로만 스케줄한다.

design §R3.1.

모든 노드·엣지 타입은 테스트 전용(`t.*`)이다. 엔진은 연결 종류·노드 타입 이름을 모른다.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import EntryPoint
from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    Issue,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    RunEvent,
    parse_run_event,
)
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    AgentRequest,
    DelegationPlan,
    NodeContext,
    NodeResult,
    NoEntryError,
    Registries,
    RuntimeIssueCodes,
    SubagentSpec,
    ValidationContext,
    as_delegation_strategy,
    load_registries,
)
from agent_console_runtime.testing import (
    BUILDERS,
    USER_NODE,
    Builders,
    Harness,
    InlineStrategy,
    make_harness,
)


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def statuses(h: Harness, run_id: str) -> dict[str, str]:
    return {nr.node_id: nr.status for nr in h.recorder.runs.list_node_runs(run_id)}


def events(h: Harness, run_id: str, type: str | None = None) -> list[RunEvent]:
    found = h.recorder.events.list(run_id)
    return [e for e in found if type is None or e.type == type]


# ---------------------------------------------------------------- 입구


@pytest.mark.parametrize("validate", [True, False])
async def test_no_entry_edge_creates_no_run(h: Harness, b: Builders, validate: bool) -> None:
    # a는 들어오는 엣지가 없지만 입구로 추론하지 않는다.
    g = b.graph([b.node("a"), b.node("b")], [b.edge("a", "b")])
    with pytest.raises(NoEntryError) as info:
        await h.make().start(g, validate=validate)
    assert [i.code for i in info.value.issues] == [RuntimeIssueCodes.NO_ENTRY]
    assert h.recorder.run_docs == {}
    assert h.probe.calls == []


async def test_entry_into_non_executable_node_is_not_an_entry(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("r", type="t.res")], [], entries=["r"])
    with pytest.raises(NoEntryError):
        await h.make().start(g)


async def test_only_explicit_entries_run(h: Harness, b: Builders) -> None:
    # a(들어오는 엣지 없음)·사용자 자리 you는 스케줄되지 않는다. 입구는 팀원 자리 b여도 된다.
    g = b.graph(
        [b.node("a"), b.node("b"), b.node("c")],
        [b.edge("a", "c"), b.edge("b", "c")],
        entries=["b"],
    )
    run = await h.make().run(g, {"msg": "hi"})
    assert run.status == "completed"
    assert statuses(h, run.id) == {"b": "succeeded", "c": "succeeded"}
    assert [c[0] for c in h.probe.calls] == ["b", "c"]
    assert h.probe.calls[0] == ("b", {"in": {"msg": "hi"}})
    # 입구·사용자 자리에는 NodeRun도 이벤트도 없다.
    assert not any(e.node_path[:1] in (["a"], [USER_NODE]) for e in events(h, run.id))


async def test_entry_into_middle_node_with_join_all(h: Harness, b: Builders) -> None:
    # a는 스케줄되지 않으므로 a → m 엣지는 처음부터 죽고, join all인 m은 입구 값만으로 실행된다.
    g = b.graph(
        [b.node("a"), b.node("m", join="all")],
        [b.edge("a", "m", tp="in2")],
        entries=["m"],
    )
    run = await h.make().run(g, {"x": 1})
    assert statuses(h, run.id) == {"m": "succeeded"}
    assert h.probe.calls == [("m", {"in": {"x": 1}})]


async def test_several_entries_and_entry_config(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("p"), b.node("q"), b.node("gone")],
        [
            b.entry("p", key="msg"),
            b.entry("q"),
            b.entry("gone", key="missing"),  # 입구 엣지가 통과하지 않으면 그 노드는 skipped
        ],
        entries=[],
    )
    g = g.model_copy(update={"nodes": [b.node(USER_NODE, type="t.user"), *g.nodes]})
    run = await h.make().run(g, {"msg": "hello", "extra": 2})
    assert run.status == "completed"
    assert statuses(h, run.id) == {"p": "succeeded", "q": "succeeded", "gone": "skipped"}
    assert dict(h.probe.calls) == {"p": {"in": "hello"}, "q": {"in": {"msg": "hello", "extra": 2}}}


async def test_entry_and_flow_join_all_waits_for_both(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "A"}, sleep=0.02), b.node("j", join="all")],
        [b.edge("a", "j", tp="in2"), b.entry("j", key="msg")],
        entries=["a"],
    )
    run = await h.make().run(g, {"msg": "M"})
    assert run.status == "completed"
    assert [c for c in h.probe.calls if c[0] == "j"] == [("j", {"in": "M", "in2": "A"})]


# ---------------------------------------------------------------- 실행하지 않는 노드·none 엣지


async def test_non_executable_and_none_edges_are_ignored(h: Harness, b: Builders) -> None:
    # t.res는 실행되면 실패하고, t.tie는 평가되면 예외 → 경고가 남는다. 둘 다 없어야 한다.
    g = b.graph(
        [b.node("res", type="t.res"), b.node("a"), b.node("b")],
        [
            b.edge("res", "a", kind="t.tie"),
            b.edge("a", "b", kind="t.tie"),
            b.edge("res", "b"),  # 실행하지 않는 노드에서 오는 흐름 → 처음부터 죽음
        ],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    # b는 흐름 입력(res → b)이 있어 스케줄 대상이지만 그 엣지가 죽어 skipped.
    assert statuses(h, run.id) == {"a": "succeeded", "b": "skipped"}
    assert events(h, run.id, "log.warning") == []


async def test_none_and_exit_edges_do_not_make_cycles(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a"), b.node("b")],
        [
            b.edge("a", "b", kind="t.tie"),
            b.edge("b", "a", kind="t.tie", sp="alt", tp="in2"),
            b.reply("a"),
        ],
        entries=["a"],
    )
    assert h.make().validate(g) == []
    run = await h.make().run(g, {"m": 1})
    assert statuses(h, run.id) == {"a": "succeeded"}


async def test_executable_user_slot_runs_only_with_flow_input(h: Harness, b: Builders) -> None:
    # 사용자 자리는 실행 가능하다. 입구·답변만 있으면 실행되지 않고, 흐름으로 들어오면 실행된다.
    g = b.graph(
        [b.node("a", outputs={"out": "draft"}), b.node("after")],
        [
            b.edge("a", "review", tp="hears"),
            b.edge("review", "after", sp="says"),
            b.reply("a"),
        ],
        entries=["a"],
    )
    g = g.model_copy(update={"nodes": [*g.nodes, b.node("review", type="t.user")]})
    run = await h.make().run(g)
    assert statuses(h, run.id) == {
        "a": "succeeded",
        "review": "succeeded",
        "after": "succeeded",
    }
    assert ("review", {"hears": "draft"}) in h.probe.calls
    assert USER_NODE not in statuses(h, run.id)


# ---------------------------------------------------------------- 답변


async def test_exit_edges_publish_replies_as_nodes_finish(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "중간 결과"}), b.node("b", outputs={"out": "최종"})],
        [
            b.edge("a", "b"),
            b.reply("a", label="중간", final=False, order=1),
            b.reply("b"),
        ],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    assert USER_NODE not in statuses(h, run.id)  # 답변 대상은 스케줄되지 않는다

    replies = events(h, run.id, "run.reply")
    assert [(e.payload["node_id"], e.payload["text"]) for e in replies] == [
        ("a", "중간 결과"),
        ("b", "최종"),
    ]
    first = replies[0]
    assert first.payload["label"] == "중간"
    assert first.payload["final"] is False
    assert first.payload["order"] == 1
    assert first.payload["edge_id"] == f"a.out->{USER_NODE}.hears"
    assert first.node_path == ["a"]
    assert replies[1].payload["final"] is True
    for e in replies:
        parse_run_event(e)  # 계약 payload 형식

    # a의 답변은 a가 끝나는 즉시(b 시작 전에) 나간다.
    order = [(e.type, e.node_path) for e in events(h, run.id)]
    assert order.index(("run.reply", ["a"])) < order.index(("node.started", ["b"]))
    assert order.index(("node.completed", ["a"])) < order.index(("run.reply", ["a"]))


async def test_reply_value_conversion_and_failed_source(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": {"k": "값"}}), b.node("f", fail=True)],
        [b.reply("a", raw=True), b.reply("f")],
        entries=["a", "f"],
    )
    run = await h.make().run(g)
    replies = events(h, run.id, "run.reply")
    assert [e.payload["text"] for e in replies] == ['{"k": "값"}']  # 실패한 f는 답변 없음
    assert replies[0].payload["label"] is None
    assert run.status == "failed"  # 답변 엣지는 실패를 "처리"하지 않는다


async def test_graph_without_exit_still_completes(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a")], [], entries=["a"])
    run = await h.make().run(g)
    assert run.status == "completed"
    assert events(h, run.id, "run.reply") == []


# ---------------------------------------------------------------- actor·하위 node_path·X12


async def test_actor_is_taken_from_node_type_hook(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", actor="writer", events=2), b.node("b")],
        [b.edge("a", "b"), b.reply("a")],
        entries=["a"],
    )
    run = await h.make().run(g)
    by_node: dict[str, set[str | None]] = {}
    for e in events(h, run.id):
        if e.node_path:
            by_node.setdefault(e.node_path[0], set()).add(e.actor)
    assert by_node["a"] == {"writer"}  # node.*·agent.text_delta·run.reply 모두
    assert by_node["b"] == {None}  # 훅이 None이면 actor 없음
    assert {e.actor for e in events(h, run.id) if not e.node_path} == {None}


async def test_delegation_strategy_runs_callees_inside_delegator(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("lead", type="t.lead", actor="pl"),
            b.node("be", actor="backend"),
            b.node("qa", actor="qa"),
        ],
        [
            b.edge("lead", "be", kind="t.call", sp="alt", tp="in2"),
            b.edge("lead", "qa", kind="t.call", sp="alt", tp="in2"),
            b.reply("be"),  # 호출 대상의 답변: 위임 결과마다 발행
            b.reply("lead"),
        ],
        entries=[],
    )
    g = g.model_copy(
        update={
            "nodes": [b.node(USER_NODE, type="t.user"), *g.nodes],
            "edges": [b.entry("lead", key="msg"), *g.edges],
        }
    )
    run = await h.make().run(g, {"msg": "작업"})
    assert run.status == "completed"
    # 호출 대상은 스케줄되지 않는다(NodeRun 없음). t.step 구현도 불리지 않는다.
    assert statuses(h, run.id) == {"lead": "succeeded"}
    assert h.probe.calls == []

    messages = events(h, run.id, "agent.message")
    assert [(e.node_path, e.actor) for e in messages] == [
        (["lead", "be"], "backend"),
        (["lead", "qa"], "qa"),
    ]
    started = events(h, run.id, "agent.subagent_started")
    assert [(e.node_path, e.actor) for e in started] == [(["lead"], "pl"), (["lead"], "pl")]

    replies = events(h, run.id, "run.reply")
    assert [(e.payload["node_id"], e.node_path, e.actor, e.payload["text"]) for e in replies] == [
        ("be", ["lead", "be"], "backend", "be:작업"),
        ("lead", ["lead"], "pl", "be:작업 | qa:작업"),
    ]


class _ContextProbeNode:
    """NodeContext 경계 검사 노드 `t.ctxprobe`(이 테스트 파일 전용)."""

    descriptor = NodeTypeDescriptor(
        id="t.ctxprobe",
        title="ctx",
        static_ports=PortSpec(inputs=[PortDef(name="in")], outputs=[PortDef(name="out")]),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return self.descriptor.static_ports or PortSpec()

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        errors: list[str] = []
        for attempt in (
            lambda: ctx.emit("x.note", {}, node_path=["elsewhere"]),
            lambda: ctx.emit("x.note", {}, node_path=[]),
            lambda: ctx.emit_replies("other", {"out": 1}),
            lambda: ctx.emit("run.reply", {}),
        ):
            try:
                await attempt()
            except ValueError as exc:
                errors.append(type(exc).__name__)
        event = await ctx.emit("x.note", {"n": 1}, node_path=ctx.child_path("sub"), actor="s")
        return NodeResult(
            status="succeeded", outputs={"out": {"errors": errors, "path": event.node_path}}
        )


async def test_context_rejects_foreign_paths_and_non_callees(h: Harness, b: Builders) -> None:
    h.registries.node_types.register("t.ctxprobe", _ContextProbeNode())
    g = b.graph(
        [b.node("c", type="t.ctxprobe"), b.node("other")],
        [b.reply("other")],
        entries=["c"],
    )
    run = await h.make().run(g)
    nr = h.recorder.runs.list_node_runs(run.id)
    out = next(n for n in nr if n.node_id == "c").outputs["out"]
    assert out == {"errors": ["ValueError"] * 4, "path": ["c", "sub"]}
    note = events(h, run.id, "x.note")
    assert [(e.node_path, e.actor) for e in note] == [(["c", "sub"], "s")]
    assert events(h, run.id, "run.reply") == []


class _StrictStrategy(InlineStrategy):
    """검사에서 늘 오류를 내는 위임 방식(엣지 config `strategy`로 고른다)."""

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        return [Issue(severity="error", code="t.strict", message="거부")]


async def test_strategy_from_edge_config_and_validation_issue(h: Harness, b: Builders) -> None:
    h.registries.delegation_strategies.register("t.strict", _StrictStrategy())
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("be")],
        [b.edge("lead", "be", kind="t.call", sp="alt", tp="in2", strategy="t.strict")],
        entries=["lead"],
    )
    run = await h.make().run(g)
    assert run.status == "failed"
    nr = h.recorder.runs.list_node_runs(run.id)
    assert [(n.node_id, n.error.code if n.error else None) for n in nr] == [("lead", "t.strict")]
    assert (
        InlineStrategy()
        .validate(
            DelegationPlan(
                strategy="t.inline",
                delegator_node_id="lead",
                request=AgentRequest(agent=Agent(id="a", name="a"), prompt="p"),
            )
        )[0]
        .code
        == "t.no_members"
    )


def test_delegation_strategies_load_from_entry_points() -> None:
    regs = Registries()
    eps = [
        EntryPoint(
            name="t.inline",
            value="agent_console_runtime.testing:InlineStrategy",
            group=DELEGATION_STRATEGIES_GROUP,
        ),
        EntryPoint(
            name="t.bad",
            value="agent_console_runtime.testing:FlowEdge",
            group=DELEGATION_STRATEGIES_GROUP,
        ),
    ]
    reports = load_registries(regs, entry_points=eps)
    assert {r.key: r.status for r in reports} == {"t.bad": "failed", "t.inline": "loaded"}
    strategy = regs.delegation_strategies.get("t.inline")
    assert strategy.descriptor.max_depth == 1
    assert regs.extension("delegation_strategies") is regs.delegation_strategies
    with pytest.raises(TypeError):
        as_delegation_strategy(object())


def test_agent_request_carries_subagents_bundle_and_interactions() -> None:
    from agent_console_contracts import InteractionGrant, ResourceBundle

    req = AgentRequest(agent=Agent(id="a", name="a"), prompt="p")
    assert req.subagents == []
    assert req.bundle is None
    assert req.interactions is None
    full = req.model_copy(
        update={
            "subagents": [SubagentSpec(name="be", description="백엔드", actor="backend-lead")],
            "bundle": ResourceBundle(slots={"instructions": ["x"]}),
            "interactions": InteractionGrant(kinds=["t.ask"]),
        }
    )
    again = AgentRequest.model_validate(full.model_dump(mode="json"))
    assert again.subagents[0].actor == "backend-lead"
    assert again.bundle is not None
    assert again.bundle.slots == {"instructions": ["x"]}
    assert again.interactions is not None
    assert again.interactions.kinds == ["t.ask"]
