"""엣지 판정 결과의 근거·경고·사유(`Activation.condition`·`warnings`, `Blocked`)와 선택 능력
`EdgeValidator`(design §5R.5·§5R.8, 작업 5R.8).

테스트 전용 엣지 타입만 쓴다(엔진은 조건 연결 이름·연산자를 모른다).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    ConditionItemOutcome,
    ConditionOutcome,
    EdgeSpec,
    EdgeTypeDescriptor,
    Issue,
    LogWarningPayload,
)
from agent_console_runtime import (
    Activation,
    Blocked,
    EdgeValidationContext,
    NodeRunView,
)
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness

EVIDENCE = ConditionOutcome(
    result=True,
    combinator="all",
    items=[ConditionItemOutcome(path="/output", op="t.op", value="x", actual="x", result=True)],
)


class JudgeEdge:
    """config `pass`가 참이면 근거와 함께 통과, 아니면 `Blocked`. config `warn`이면 경고를 단다."""

    descriptor = EdgeTypeDescriptor(id="t.judge", title="판정")

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | Blocked | None:
        if source.status != "succeeded":
            return None
        warnings = (
            (LogWarningPayload(message="주의", details={"code": "t.warn"}),)
            if edge.config.get("warn")
            else ()
        )
        if edge.config.get("pass"):
            return Activation(source.outputs.get("out"), condition=EVIDENCE, warnings=warnings)
        failed = EVIDENCE.model_copy(update={"result": False})
        return Blocked(reason="t.no", condition=failed, warnings=warnings)

    def validate_edge(self, edge: EdgeSpec, ctx: EdgeValidationContext) -> list[Issue]:
        if edge.config.get("bad"):
            return [Issue(severity="error", code="t.bad", message="bad", path="/bad")]
        return []


@pytest.fixture
def h() -> Harness:
    harness = make_harness()
    harness.registries.edge_types.register("t.judge", JudgeEdge())
    return harness


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def _payloads(h: Harness, run_id: str, type: str) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in h.recorder.events.list(run_id) if e.type == type]


async def test_traversed_carries_condition_and_blocked_emits_skipped(
    h: Harness, b: Builders
) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": "v"}), b.node("yes"), b.node("no")],
        [
            b.edge("a", "yes", kind="t.judge", **{"pass": True}),
            b.edge("a", "no", kind="t.judge", warn=True),
        ],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    statuses = {nr.node_id: nr.status for nr in h.recorder.runs.list_node_runs(run.id)}
    assert statuses["yes"] == "succeeded"
    assert statuses["no"] == "skipped"

    traversed = [p for p in _payloads(h, run.id, "edge.traversed") if p["kind"] == "t.judge"]
    assert len(traversed) == 1
    assert traversed[0]["condition"]["result"] is True
    assert traversed[0]["condition"]["items"][0]["op"] == "t.op"

    skipped = _payloads(h, run.id, "edge.skipped")
    assert len(skipped) == 1
    assert skipped[0]["edge_id"] == "a.out->no.in"
    assert skipped[0]["reason"] == "t.no"
    assert skipped[0]["kind"] == "t.judge"
    assert skipped[0]["condition"]["result"] is False

    warnings = _payloads(h, run.id, "log.warning")
    assert [w["details"] for w in warnings] == [
        {"code": "t.warn", "edge_id": "a.out->no.in", "kind": "t.judge"}
    ]


async def test_plain_dead_path_emits_no_skipped_event(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={}), b.node("x")],
        [b.edge("a", "x")],
        entries=["a"],
    )
    run = await h.make().run(g)
    assert _payloads(h, run.id, "edge.skipped") == []


def test_edge_validator_issues_join_graph_validation(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a"), b.node("x")],
        [b.edge("a", "x", kind="t.judge", bad=True), b.edge("x", "a", kind="t.unknown")],
        entries=["a"],
    )
    issues = h.make().validate(g)
    found = [(i.code, i.edge_id, i.path) for i in issues if i.code == "t.bad"]
    assert found == [("t.bad", "a.out->x.in", "/bad")]
