"""ac-nodes-core: 조건 연결 `when`·실패 처리 연결 `on_error`(design §5R.5, 5R.8).

단위(`activates`·`validate_edge`)와 fake 백엔드로 끝까지 실행(이벤트 `edge.traversed`/`edge.skipped`
payload `condition`, 경고 이벤트, 실패 처리 뒤 Run `completed`)을 본다. 테스트 연산자는
entry point로 주입하고, 이름을 바꾼 테스트 연결 종류로도 같은 동작을 확인한다(엔진은 id를 모른다).
"""

from __future__ import annotations

import importlib.metadata
import sys
import types
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import pytest

from agent_console_backend_fake import FakeBackend
from agent_console_conditions import (
    CONDITION_OPERATORS_GROUP,
    ConditionIssueCodes,
    OperatorConsumer,
    RedactorConsumer,
    builtin_operators,
    load_condition_operators,
    new_operator_registry,
    operator_map,
)
from agent_console_contracts import (
    Agent,
    ConditionOperatorDescriptor,
    EdgeSpec,
    ErrorInfo,
    Graph,
    NodeRun,
    NodeSpec,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_nodes_core import AGENT_LOOKUP, WORKSPACE_SETTINGS
from agent_console_nodes_core.conditional import (
    CONDITION_FALSE,
    CONDITION_WIDGET,
    OnErrorEdge,
    WhenEdge,
    condition_subject,
)
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    NODE_TYPES_GROUP,
    Activation,
    Blocked,
    EdgeValidator,
    EnvSecretProvider,
    GraphRuntime,
    NodeRunView,
    Registries,
    SecretResolver,
    Services,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock

DIST = "agent-console-nodes-core"
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP)
OPS = {op.descriptor.id: op for op in builtin_operators()}


def edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str, **config: Any) -> EdgeSpec:
    return EdgeSpec.model_validate(
        {
            "id": eid,
            "source": {"node": src, "port": sp},
            "target": {"node": dst, "port": tp},
            "kind": kind,
            "config": config,
        }
    )


def contains_pass(**extra: Any) -> dict[str, Any]:
    return {"all": [{"path": "/output", "op": "contains", "value": "PASS"}], **extra}


def view(
    status: Any = "succeeded",
    outputs: Mapping[str, Any] | None = None,
    *,
    error: ErrorInfo | None = None,
    iteration: int = 0,
    structured: Any = None,
) -> NodeRunView:
    return NodeRunView(
        node_id="check",
        node_type="agent",
        status=status,
        outputs=MappingProxyType(dict(outputs or {})),
        error=error,
        iteration=iteration,
        structured=structured,
    )


# ---------------------------------------------------------------- 단위: when


def test_when_descriptor_is_data_for_the_editor() -> None:
    d = WhenEdge.descriptor
    assert d.scheduling == "flow"
    assert d.handles_failure is False
    assert d.ui_schema["conditions"]["ui:widget"] == CONDITION_WIDGET
    item = d.config_schema["$defs"]["ConditionItem"]["properties"]["path"]
    assert "/output" in item["examples"]
    titles = d.ui_schema["conditions"]["ui:options"]["path_titles"]
    assert set(titles) == set(item["examples"])


def test_when_true_passes_value_with_evidence() -> None:
    e = edge("w", "check", "out", "ok", "in", "when", conditions=contains_pass())
    got = WhenEdge(OPS).activates(view(outputs={"out": "all tests PASS (12)"}), e)
    assert isinstance(got, Activation)
    assert got.value == "all tests PASS (12)"
    assert got.condition is not None
    assert got.condition.result is True
    assert got.condition.combinator == "all"
    assert got.warnings == ()


def test_when_false_is_blocked_with_reason_and_evidence() -> None:
    e = edge("w", "check", "out", "ok", "in", "when", conditions=contains_pass())
    got = WhenEdge(OPS).activates(view(outputs={"out": "2 failed"}), e)
    assert isinstance(got, Blocked)
    assert got.reason == CONDITION_FALSE
    assert got.condition is not None
    assert [(i.result, i.actual) for i in got.condition.items or []] == [(False, "2 failed")]


def test_when_negate_any_and_subject_fields() -> None:
    cond = {
        "any": [
            {"path": "/structured/verdict", "op": "eq", "value": "ok"},
            {"path": "/iteration", "op": "gte", "value": 2},
        ],
        "negate": True,
    }
    e = edge("w", "check", "out", "fix", "in", "when", conditions=cond)
    fresh = view(outputs={"out": "x"}, structured={"verdict": "bad"}, iteration=0)
    assert isinstance(WhenEdge(OPS).activates(fresh, e), Activation)  # 둘 다 거짓 → 뒤집어 참
    later = view(outputs={"out": "x"}, structured={"verdict": "bad"}, iteration=2)
    assert isinstance(WhenEdge(OPS).activates(later, e), Blocked)
    assert condition_subject(later, e) == {
        "status": "succeeded",
        "iteration": 2,
        "output": "x",
        "structured": {"verdict": "bad"},
    }


def test_when_needs_success_and_port_value_and_empty_means_always() -> None:
    e = edge("w", "check", "out", "ok", "in", "when")
    when = WhenEdge(OPS)
    assert isinstance(when.activates(view(outputs={"out": "x"}), e), Activation)
    assert when.activates(view(outputs={}), e) is None
    failed = view("failed", error=ErrorInfo(code="x", message="y"))
    assert when.activates(failed, e) is None


def test_when_unknown_operator_is_false_with_warning() -> None:
    cond = {"all": [{"path": "/output", "op": "removed_plugin", "value": 1}]}
    e = edge("w", "check", "out", "ok", "in", "when", conditions=cond)
    got = WhenEdge(OPS).activates(view(outputs={"out": "x"}), e)
    assert isinstance(got, Blocked)
    assert [w.details for w in got.warnings] == [
        {"code": ConditionIssueCodes.UNKNOWN_OPERATOR, "op": "removed_plugin", "path": "/output"}
    ]


def test_when_operator_source_can_be_live() -> None:
    current: dict[str, Any] = {}
    when = WhenEdge(lambda: current)
    e = edge("w", "check", "out", "ok", "in", "when", conditions=contains_pass())
    assert isinstance(when.activates(view(outputs={"out": "PASS"}), e), Blocked)
    current.update(OPS)
    assert isinstance(when.activates(view(outputs={"out": "PASS"}), e), Activation)


def test_when_default_operators_come_from_entry_points() -> None:
    assert {"contains", "matches", "lte"} <= set(WhenEdge().operators())


def test_when_takes_app_operator_registry() -> None:
    """앱이 `use_operators`로 자기 연산자 레지스트리를 준다(`OperatorConsumer`, 5R.13)."""
    when = WhenEdge()
    assert isinstance(when, OperatorConsumer)
    assert "contains" in when.operators()  # 기본값(설치된 entry point)을 읽은 뒤에도
    registry = new_operator_registry()
    when.use_operators(lambda: operator_map(registry))
    e = edge("w", "check", "out", "ok", "in", "when", conditions=contains_pass())
    assert isinstance(when.activates(view(outputs={"out": "PASS"}), e), Blocked)  # 아직 없음
    registry.register("contains", OPS["contains"])
    assert isinstance(when.activates(view(outputs={"out": "PASS"}), e), Activation)


def test_when_redacts_evidence_before_cutting_at_boundary() -> None:
    """5.2R.43: 비밀이 자르기 경계(200자)에 걸쳐도 근거에 조각이 남지 않는다(자르기 전에 가림)."""
    secret = "sk-very-secret-value-0123456789"
    secrets = SecretResolver([EnvSecretProvider({"API_KEY": secret})])
    secrets.resolve("secret://API_KEY")
    text = "x" * 190 + secret + " tail"  # 190~220자에 걸친 비밀 — 200자에서 잘린다
    cond = {"all": [{"path": "/output", "op": "contains", "value": "NOPE"}]}
    e = edge("w", "check", "out", "ok", "in", "when", conditions=cond)

    plain = WhenEdge(OPS).activates(view(outputs={"out": text}), e)
    assert isinstance(plain, Blocked)
    assert plain.condition is not None
    (raw,) = plain.condition.items or []
    cut = str(raw.actual)
    # 가림 없이 자르면 비밀 앞 조각이 남고, 잘린 뒤의 기록 단계 가림은 조각을 알아보지 못한다
    assert secret[:10] in cut
    assert secrets.redact(cut) == cut

    when = WhenEdge(OPS, redact=secrets.redact)
    got = when.activates(view(outputs={"out": text}), e)
    assert isinstance(got, Blocked)
    assert got.condition is not None
    (item,) = got.condition.items or []
    assert secret[:6] not in str(item.actual)
    assert "[REDACTED]" in str(item.actual)
    assert item.result is False  # 판정은 원래 값으로 한다

    # 앱이 나중에 주는 길(`RedactorConsumer.use_redactor`, 실행 모듈이 부른다)
    late = WhenEdge(OPS)
    assert isinstance(late, RedactorConsumer)
    late.use_redactor(secrets.redact)
    passed = late.activates(
        view(outputs={"out": text}),
        edge("w", "check", "out", "ok", "in", "when", conditions=contains_pass()),
    )
    assert isinstance(passed, Blocked)
    assert passed.condition is not None
    assert secret[:6] not in str((passed.condition.items or [])[0].actual)
    late.use_redactor(None)
    again = late.activates(view(outputs={"out": text}), e)
    assert isinstance(again, Blocked)
    assert again.condition is not None
    assert secret[:10] in str((again.condition.items or [])[0].actual)


# ---------------------------------------------------------------- 단위: on_error


def test_on_error_only_on_failure() -> None:
    e = edge("x", "check", "out", "fix", "in", "on_error")
    assert OnErrorEdge.descriptor.handles_failure is True
    assert OnErrorEdge().activates(view(outputs={"out": "ok"}), e) is None
    got = OnErrorEdge().activates(view("failed", error=ErrorInfo(code="c", message="m")), e)
    assert isinstance(got, Activation)
    assert got.value == {"error": {"code": "c", "message": "m"}, "node_id": "check"}


# ---------------------------------------------------------------- 실행(fake 백엔드)


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder
    services: dict[Any, Any]

    def runtime(self) -> GraphRuntime:
        return GraphRuntime(
            self.registries,
            self.recorder,
            clock=StepClock(),
            ids=SequentialIds("e"),
            services=Services(self.services),
        )

    async def run(self, graph: Graph, text: str) -> Run:
        return await self.runtime().run(graph, {"text": text})

    def node_runs(self, run: Run) -> dict[str, NodeRun]:
        return {nr.node_id: nr for nr in self.recorder.runs.list_node_runs(run.id)}

    def events(self, run: Run, type: str) -> list[RunEvent]:
        return [ev for ev in self.recorder.events.list(run.id) if ev.type == type]


def agent(agent_id: str, **options: Any) -> Agent:
    opts = {"default": {"response": f"{agent_id}:$prompt"}, **options}
    return Agent.model_validate({"id": agent_id, "name": agent_id, "backend_options": opts})


def make_stack(*agents: Agent) -> Stack:
    regs = Registries()
    eps = [ep for ep in importlib.metadata.distribution(DIST).entry_points if ep.group in GROUPS]
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    regs.backends.register("fake", FakeBackend(ids=SequentialIds("s"), clock=StepClock()))
    found = {a.id: a for a in agents}
    services: dict[Any, Any] = {
        AGENT_LOOKUP: found.get,
        WORKSPACE_SETTINGS: WorkspaceSettings.model_validate(
            {"agent_defaults": {"backend": "fake"}}
        ),
    }
    return Stack(regs, InMemoryRecorder(), services)


def node(node_id: str) -> NodeSpec:
    return NodeSpec.model_validate(
        {"id": node_id, "type": "agent", "label": node_id, "config": {"agent_ref": node_id}}
    )


def graph(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> Graph:
    return Graph.model_validate(
        {
            "id": "team",
            "name": "팀",
            "nodes": [NodeSpec(id="you", type="user", label="나").model_dump()]
            + [x.model_dump() for x in nodes],
            "edges": [x.model_dump() for x in edges],
        }
    )


def checker_graph(kind: str = "when") -> Graph:
    return graph(
        [node("check"), node("ok"), node("fix")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("pass", "check", "out", "ok", "in", kind, conditions=contains_pass()),
            edge("fail", "check", "out", "fix", "in", kind, conditions=contains_pass(negate=True)),
            edge("a1", "ok", "out", "you", "hears", "reply"),
            edge("a2", "fix", "out", "you", "hears", "reply"),
        ],
    )


CHECK_RULES = {"rules": [{"contains": "good", "response": "all tests PASS (12)"}]}


@pytest.mark.parametrize(
    ("text", "passed", "skipped"), [("good", "ok", "fix"), ("bad", "fix", "ok")]
)
async def test_only_one_when_edge_passes(text: str, passed: str, skipped: str) -> None:
    stack = make_stack(agent("check", **CHECK_RULES), agent("ok"), agent("fix"))
    run = await stack.run(checker_graph(), text)
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert runs[passed].status == "succeeded"
    assert runs[skipped].status == "skipped"

    traversed = [
        ev.payload for ev in stack.events(run, "edge.traversed") if ev.payload["kind"] == "when"
    ]
    skipped_events = [ev.payload for ev in stack.events(run, "edge.skipped")]
    assert [p["target"]["node"] for p in traversed] == [passed]
    assert [p["target"]["node"] for p in skipped_events] == [skipped]
    assert skipped_events[0]["reason"] == CONDITION_FALSE
    for payload in (*traversed, *skipped_events):
        cond = payload["condition"]
        assert cond["combinator"] == "all"
        assert cond["items"][0]["path"] == "/output"
        assert cond["items"][0]["op"] == "contains"
    assert traversed[0]["condition"]["result"] is True
    assert skipped_events[0]["condition"]["result"] is False


async def test_structured_result_is_visible_to_conditions() -> None:
    check = agent(
        "check", rules=[{"response": "done", "structured": {"verdict": "ok", "score": 0.9}}]
    )
    stack = make_stack(check, agent("ok"))
    cond = {"all": [{"path": "/structured/score", "op": "gte", "value": 0.8}]}
    g = graph(
        [node("check"), node("ok")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("w", "check", "out", "ok", "in", "when", conditions=cond),
            edge("a", "ok", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(g, "go")
    assert run.status == "completed", run.error
    assert stack.node_runs(run)["ok"].status == "succeeded"


async def test_unknown_operator_warns_and_skips_at_runtime() -> None:
    stack = make_stack(agent("check"), agent("ok"))
    cond = {"all": [{"path": "/output", "op": "gone_operator", "value": "x"}]}
    g = graph(
        [node("check"), node("ok")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("w", "check", "out", "ok", "in", "when", conditions=cond),
            edge("a", "check", "out", "you", "hears", "reply"),
        ],
    )
    issues = stack.runtime().validate(g)
    assert [(i.severity, i.code, i.edge_id, i.path) for i in issues] == [
        ("warning", ConditionIssueCodes.UNKNOWN_OPERATOR, "w", "/conditions/all/0/op")
    ]
    run = await stack.run(g, "hi")
    assert run.status == "completed", run.error
    warnings = [ev.payload for ev in stack.events(run, "log.warning")]
    assert [w["details"] for w in warnings] == [
        {
            "code": ConditionIssueCodes.UNKNOWN_OPERATOR,
            "op": "gone_operator",
            "path": "/output",
            "edge_id": "w",
            "kind": "when",
        }
    ]
    assert stack.events(run, "edge.skipped")[0].payload["condition"]["items"][0]["reason"] == (
        "unknown_operator"
    )
    assert stack.node_runs(run)["ok"].status == "skipped"


async def test_validation_reports_condition_issues_before_save() -> None:
    stack = make_stack(agent("check"), agent("ok"))
    bad = {
        "all": [
            {"path": "/iteration", "op": "gt", "value": "3"},
            {"path": "/output", "op": "matches", "value": "(a+)+"},
        ]
    }
    g = graph(
        [node("check"), node("ok"), node("other")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("w1", "check", "out", "ok", "in", "when", conditions=bad),
            edge("w2", "check", "out", "other", "in", "when"),
        ],
    )
    got = [(i.severity, i.code, i.edge_id, i.path) for i in stack.runtime().validate(g)]
    assert ("error", ConditionIssueCodes.INVALID_VALUE, "w1", "/conditions/all/0/value") in got
    assert ("error", ConditionIssueCodes.INVALID_VALUE, "w1", "/conditions/all/1/value") in got
    assert ("warning", ConditionIssueCodes.EMPTY, "w2", "/conditions") in got
    assert isinstance(stack.registries.edge_types.get("when"), EdgeValidator)


async def test_on_error_handles_failure_and_run_completes() -> None:
    failing = agent("check", rules=[{"fail": {"code": "tests.failed", "message": "3 failed"}}])
    stack = make_stack(failing, agent("fix"))
    g = graph(
        [node("check"), node("fix")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("err", "check", "out", "fix", "in", "on_error"),
            edge("a", "fix", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(g, "go")
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert runs["check"].status == "failed"
    assert runs["fix"].status == "succeeded"
    assert "tests.failed" in str(runs["fix"].outputs["out"])
    traversed = stack.events(run, "edge.traversed")
    assert [ev.payload["kind"] for ev in traversed if ev.payload["edge_id"] == "err"] == [
        "on_error"
    ]


async def test_failure_without_on_error_still_fails_run() -> None:
    failing = agent("check", rules=[{"fail": {"code": "tests.failed", "message": "x"}}])
    stack = make_stack(failing, agent("fix"))
    g = graph(
        [node("check"), node("fix")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("h", "check", "out", "fix", "in", "handoff"),
        ],
    )
    run = await stack.run(g, "go")
    assert run.status == "failed"


async def test_on_error_does_not_pass_on_success() -> None:
    stack = make_stack(agent("check"), agent("fix"))
    g = graph(
        [node("check"), node("fix")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("err", "check", "out", "fix", "in", "on_error"),
            edge("a", "check", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(g, "go")
    assert run.status == "completed"
    assert stack.node_runs(run)["fix"].status == "skipped"


# ---------------------------------------------------------------- 주입·이름 바꾸기(R0)


class WordsAtLeast:
    """테스트 연산자: 단어 수 >= 기대 값."""

    descriptor = ConditionOperatorDescriptor(
        id="words_at_least", title="단어 수 이상", value_schema={"type": "integer"}
    )

    def evaluate(self, actual: Any, expected: Any) -> bool:
        return (
            isinstance(actual, str)
            and isinstance(expected, int)
            and (len(actual.split()) >= expected)
        )


class RenamedWhen(WhenEdge):
    """이름을 바꾼 테스트 연결 종류(엔진·검증이 id `when`을 모른다는 확인)."""

    descriptor = WhenEdge.descriptor.model_copy(update={"id": "if_words"}, deep=True)


async def test_injected_operator_entry_point_and_renamed_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = types.ModuleType("ac_nodes_core_test_ops")
    mod.WordsAtLeast = WordsAtLeast  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, mod.__name__, mod)
    registry = new_operator_registry()
    reports = load_condition_operators(
        registry,
        entry_points=[
            importlib.metadata.EntryPoint(
                "words_at_least", f"{mod.__name__}:WordsAtLeast", CONDITION_OPERATORS_GROUP
            )
        ],
    )
    assert all(r.ok for r in reports)

    stack = make_stack(agent("check"), agent("ok"))
    stack.registries.edge_types.register("if_words", RenamedWhen(lambda: operator_map(registry)))
    cond = {"all": [{"path": "/output", "op": "words_at_least", "value": 3}]}
    g = graph(
        [node("check"), node("ok")],
        [
            edge("m", "you", "says", "check", "in", "message"),
            edge("w", "check", "out", "ok", "in", "if_words", conditions=cond),
            edge("a", "ok", "out", "you", "hears", "reply"),
        ],
    )
    assert stack.runtime().validate(g) == []
    run = await stack.run(g, "one two three")  # check 응답 = "check:one two three"(단어 3개)
    assert run.status == "completed", run.error
    assert stack.node_runs(run)["ok"].status == "succeeded"
    passed = [
        ev.payload for ev in stack.events(run, "edge.traversed") if ev.payload["edge_id"] == "w"
    ]
    assert passed[0]["condition"]["result"] is True
    assert passed[0]["kind"] == "if_words"

    registry.unregister("words_at_least")  # 플러그인 제거 → 저장 warning·실행 거짓
    assert [i.code for i in stack.runtime().validate(g)] == [ConditionIssueCodes.UNKNOWN_OPERATOR]
    run = await stack.run(g, "one two three")
    assert stack.node_runs(run)["ok"].status == "skipped"
