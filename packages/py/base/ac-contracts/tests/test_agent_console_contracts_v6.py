"""계약 v6(design §5R.9 표 1~9, 0.7.0): 반복·조건·실패 연결, 독립·혼합 위임, 중첩 팀(자식 Run).

- 새 필드는 모두 선택이고, phase-4r(0.6.0) 계약으로 읽고 쓴 결과
  (`fixtures/phase4r_reference.json`)와 dump·해시를 비교한다
  (기존 YAML·스냅샷·4R 실행 기록 무수정 읽기).
- "생략 = 상속" 왕복을 `flow.*`·`delegation.max_nesting`으로 넓힌다.
"""

import hashlib
import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import agent_console_contracts as contracts
from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    KNOWN_RUN_EVENT_TYPES,
    BackendCapabilities,
    ConditionItem,
    ConditionOperatorDescriptor,
    ConditionOutcome,
    ConditionSpec,
    CyclePolicy,
    DelegationSettings,
    DelegationStrategyDescriptor,
    EdgeSkippedEvent,
    EdgeTraversedEvent,
    EdgeTypeDescriptor,
    FlowSettings,
    Graph,
    GraphSettings,
    Interaction,
    KnownIssueCodes,
    LoopExhaustedEvent,
    LoopIterationEvent,
    NodeRun,
    NodeStatusPayload,
    Run,
    RunChildFinishedEvent,
    RunChildStartedEvent,
    RunChildStartedPayload,
    RunEvent,
    RunSnapshot,
    TraceLink,
    TraceSpan,
    WorkspaceSettings,
    build_schema,
    parse_run_event,
)
from agent_console_contracts import runs as runs_module

RUN: dict[str, Any] = {
    "id": "r2",
    "graph_id": "child",
    "graph_version": "v",
    "status": "running",
    "input": {},
    "origin": "api",
    "created_at": 1.0,
}
EVENT: dict[str, Any] = {"event_id": "e", "run_id": "r1", "seq": 1, "ts": 1.0, "node_path": []}
ENDPOINTS: dict[str, Any] = {
    "source": {"node": "a", "port": "out"},
    "target": {"node": "b", "port": "in"},
}


def _sha(doc: Any) -> str:
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 버전·하위 모듈


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("."))


def test_contracts_version_is_v6_or_later() -> None:
    """버전 값 자체는 v7 테스트가 고정한다(0.8.0). 여기서는 v6에서 올린 것만 본다."""
    assert _ver(CONTRACTS_VERSION) >= (0, 7, 0)
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS
    for sub in ("common", "definitions", "runs"):
        assert _ver(CONTRACT_VERSIONS[sub]) >= (1, 2, 0), sub


def test_new_models_belong_to_their_submodules() -> None:
    grouped = build_schema()["x-modules"]
    assert {
        "CyclePolicy",
        "ConditionSpec",
        "ConditionItem",
        "ConditionOutcome",
        "ConditionItemOutcome",
        "ConditionOperatorDescriptor",
        "EdgeSkippedPayload",
        "LoopIterationPayload",
        "LoopExhaustedPayload",
        "RunChildStartedPayload",
        "RunChildFinishedPayload",
    } <= set(grouped["runs"])
    assert "FlowSettings" in grouped["definitions"]


def test_runs_submodule_alone_has_v6_models() -> None:
    for name in (
        "ConditionSpec",
        "ConditionOperatorDescriptor",
        "CyclePolicy",
        "LoopIterationEvent",
    ):
        assert getattr(runs_module, name) is getattr(contracts, name)


# ---------------------------------------------------------------- 표 1·2: 디스크립터


def test_edge_type_cycle_and_failure_defaults() -> None:
    desc = EdgeTypeDescriptor.model_validate({"id": "zz", "title": "t"})
    assert desc.cycle is None
    assert desc.handles_failure is False
    looped = EdgeTypeDescriptor.model_validate(
        {"id": "zz-loop", "title": "t", "cycle": {"max_iterations": 3, "title": "최대 3회"}}
    )
    assert looped.cycle == CyclePolicy(max_iterations=3, title="최대 3회")
    with pytest.raises(ValidationError):
        CyclePolicy.model_validate({"max_iterations": 0})
    with pytest.raises(ValidationError):
        CyclePolicy.model_validate({})


def test_delegation_composable_and_backend_host_tools_defaults() -> None:
    desc = DelegationStrategyDescriptor.model_validate(
        {"id": "zz", "title": "t", "member_fields": [], "max_depth": None}
    )
    assert desc.composable is False
    assert BackendCapabilities().host_tools is False
    assert BackendCapabilities.model_validate({"host_tools": True}).host_tools is True


# ---------------------------------------------------------------- 표 3·5: 실행 기록


def test_run_lineage_fields_are_optional() -> None:
    run = Run.model_validate(RUN)
    assert run.root_run_id is None
    assert run.parent_node_id is None
    assert run.parent_run_id is None
    child = Run.model_validate(
        {**RUN, "parent_run_id": "r1", "root_run_id": "r0", "parent_node_id": "team"}
    )
    assert child.model_dump(mode="json", exclude_unset=True) == {
        **RUN,
        "parent_run_id": "r1",
        "root_run_id": "r0",
        "parent_node_id": "team",
    }


def test_node_run_call_and_invoked_by() -> None:
    base = {"run_id": "r", "node_id": "n", "status": "succeeded"}
    plain = NodeRun.model_validate(base)
    assert plain.call == 0
    assert plain.invoked_by is None
    assert plain.iteration == 0
    called = NodeRun.model_validate({**base, "call": 2, "invoked_by": ["lead"], "iteration": 1})
    assert called.call == 2
    assert called.invoked_by == ["lead"]
    with pytest.raises(ValidationError):
        NodeRun.model_validate({**base, "call": -1})


def test_run_snapshot_children_null_means_not_filled() -> None:
    snap = RunSnapshot.model_validate({"run": RUN, "node_runs": [], "last_seq": 0})
    assert snap.children is None
    with_children = RunSnapshot.model_validate(
        {"run": RUN, "node_runs": [], "last_seq": 0, "children": [RUN]}
    )
    assert with_children.children is not None
    assert with_children.children[0].id == "r2"
    empty = RunSnapshot.model_validate({"run": RUN, "node_runs": [], "last_seq": 0, "children": []})
    assert empty.children == []


def test_interaction_root_run_id() -> None:
    doc = {
        "id": "i",
        "run_id": "r2",
        "node_id": "n",
        "kind": "zz",
        "status": "pending",
        "created_at": 1.0,
    }
    assert Interaction.model_validate(doc).root_run_id is None
    assert Interaction.model_validate({**doc, "root_run_id": "r1"}).root_run_id == "r1"


def test_trace_span_and_link_round_and_run_fields() -> None:
    span = TraceSpan.model_validate(
        {"id": "s", "kind": "zz-span", "iteration": 2, "call": 1, "run_id": "child"}
    )
    assert (span.iteration, span.call, span.run_id) == (2, 1, "child")
    assert TraceLink.model_validate({"source": "a", "target": "b", "run_id": "c"}).run_id == "c"


# ---------------------------------------------------------------- 표 4: 이벤트


@pytest.mark.parametrize(
    ("type_", "payload", "cls"),
    [
        (
            "loop.iteration",
            {"edge_id": "e", "iteration": 1, "nodes": ["a", "b"]},
            LoopIterationEvent,
        ),
        ("loop.exhausted", {"edge_id": "e", "iteration": 3}, LoopExhaustedEvent),
        ("run.child_started", {"child_run_id": "c", "node_id": "team"}, RunChildStartedEvent),
        (
            "run.child_finished",
            {"child_run_id": "c", "node_id": "team", "status": "completed"},
            RunChildFinishedEvent,
        ),
        ("edge.skipped", {"edge_id": "e", **ENDPOINTS, "reason": "zz"}, EdgeSkippedEvent),
    ],
)
def test_new_known_events_parse(type_: str, payload: dict[str, Any], cls: type[BaseModel]) -> None:
    assert type_ in KNOWN_RUN_EVENT_TYPES
    assert type_ in build_schema()["x-constants"]["KNOWN_RUN_EVENT_TYPES"]
    doc = {**EVENT, "type": type_, "payload": payload}
    event = parse_run_event(doc)
    assert isinstance(event, cls)
    # 저장·전송 형식(일반 RunEvent)으로도 그대로 왕복한다
    assert RunEvent.model_validate(doc).model_dump(mode="json", exclude_unset=True) == doc


def test_child_finished_status_is_child_run_status() -> None:
    with pytest.raises(ValidationError):
        parse_run_event(
            {
                **EVENT,
                "type": "run.child_finished",
                "payload": {"child_run_id": "c", "node_id": "n", "status": "zz"},
            }
        )
    # 시작 이벤트에는 status가 없다(부모 Run 상태로 오해하지 않게)
    assert "status" not in RunChildStartedPayload.model_fields


def test_edge_events_carry_condition_outcome() -> None:
    # 화면 명세 screen-delegation §12 S1 모양
    outcome = {
        "result": False,
        "combinator": "all",
        "negate": False,
        "items": [
            {
                "path": "/output",
                "op": "zz-op",
                "value": "PASS",
                "actual": "FAIL [REDACTED]",
                "result": False,
                "reason": "unknown_operator",
            }
        ],
    }
    traversed = parse_run_event(
        {
            **EVENT,
            "type": "edge.traversed",
            "payload": {"edge_id": "e", **ENDPOINTS, "condition": {"result": True}},
        }
    )
    assert isinstance(traversed, EdgeTraversedEvent)
    assert traversed.payload.condition == ConditionOutcome(result=True)
    skipped = parse_run_event(
        {
            **EVENT,
            "type": "edge.skipped",
            "payload": {"edge_id": "e", **ENDPOINTS, "condition": outcome},
        }
    )
    assert isinstance(skipped, EdgeSkippedEvent)
    assert skipped.payload.model_dump(mode="json", exclude_unset=True)["condition"] == outcome
    # 조건이 없는 4R 형식 그대로도 읽힌다
    old = parse_run_event(
        {**EVENT, "type": "edge.traversed", "payload": {"edge_id": "e", **ENDPOINTS}}
    )
    assert isinstance(old, EdgeTraversedEvent)
    assert old.payload.condition is None


def test_node_status_payload_call_is_optional() -> None:
    assert NodeStatusPayload.model_validate({"status": "running"}).call is None
    assert NodeStatusPayload.model_validate({"status": "running", "call": 1}).call == 1


# ---------------------------------------------------------------- 표 6: 조건


@pytest.mark.parametrize(
    "spec",
    [
        {},
        {"all": []},
        {"any": [{"path": "/output", "op": "zz-contains", "value": "PASS"}]},
        {"all": [{"path": "/iteration", "op": "gte", "value": 2}], "negate": True},
        {
            "all": [{"path": "", "op": "exists"}],
            "any": [{"path": "/a/b", "op": "in", "value": [1]}],
        },
        {"all": [{"path": "/x", "op": "eq", "value": None, "zz_note": "kept"}], "zz": 1},
    ],
)
def test_condition_spec_round_trip(spec: dict[str, Any]) -> None:
    """사용자 데이터: 생략·null·모르는 키가 저장 후에도 그대로다. 연산자 이름은 열린 문자열."""
    assert ConditionSpec.model_validate(spec).model_dump(mode="json", exclude_unset=True) == spec


def test_condition_item_requires_json_pointer_path_and_op() -> None:
    with pytest.raises(ValidationError):
        ConditionItem.model_validate({"path": "output", "op": "eq"})
    with pytest.raises(ValidationError):
        ConditionItem.model_validate({"path": "/output", "op": ""})
    assert ConditionItem.model_validate({"path": "/output", "op": "zz"}).value is None


def test_condition_operator_descriptor_defaults() -> None:
    desc = ConditionOperatorDescriptor.model_validate({"id": "zz", "title": "t"})
    assert desc.value_schema == {}
    assert desc.applies_to is None
    assert desc.description == ""


def test_condition_mode_is_fixed_vocabulary() -> None:
    with pytest.raises(ValidationError):
        ConditionOutcome.model_validate({"result": True, "combinator": "zz"})
    with pytest.raises(ValidationError):
        ConditionOutcome.model_validate(
            {"result": True, "items": [{"mode": "zz", "path": "", "op": "o", "result": True}]}
        )


# ---------------------------------------------------------------- 표 7: 설정(생략 = 상속)


def test_flow_settings_defaults() -> None:
    flow = FlowSettings()
    assert flow.max_iterations is None
    assert flow.max_node_runs == 200
    assert flow.model_dump(exclude_unset=True) == {}
    assert DelegationSettings().max_nesting == 3
    for bad in ({"max_iterations": 0}, {"max_node_runs": 0}):
        with pytest.raises(ValidationError):
            FlowSettings.model_validate(bad)
    with pytest.raises(ValidationError):
        DelegationSettings.model_validate({"max_nesting": 0})


def test_workspace_flow_omitted_is_inherited() -> None:
    settings = WorkspaceSettings.model_validate({})
    assert "flow" not in settings.model_dump(exclude_unset=True)
    assert settings.flow.max_node_runs == 200
    assert settings.delegation.max_nesting == 3
    # 공통 층의 기본값(유효 설정 계산의 기본값 층)은 전체 직렬화에 있다
    full = settings.model_dump(mode="json")
    assert full["flow"] == {"max_iterations": None, "max_node_runs": 200}
    assert full["delegation"]["max_nesting"] == 3


@pytest.mark.parametrize(
    "layer",
    [
        {"flow": {}},
        {"flow": {"max_iterations": 2}},
        {"flow": {"max_node_runs": None}},
        {"flow": {"max_iterations": None, "max_node_runs": 50, "zz": True}},
        {"delegation": {"max_nesting": 1}},
        {"delegation": {"max_nesting": None}},
        {"delegation": {"max_depth": 2, "max_nesting": 4}},
    ],
)
def test_flow_and_nesting_round_trip_on_both_layers(layer: dict[str, Any]) -> None:
    workspace = WorkspaceSettings.model_validate(layer)
    assert workspace.model_dump(mode="json", exclude_unset=True) == layer
    graph_layer = GraphSettings.model_validate(layer)
    assert graph_layer.model_dump(mode="json", exclude_unset=True) == layer


def test_graph_layer_flow_omitted_is_inherited() -> None:
    layer = GraphSettings.model_validate({})
    assert layer.flow is None
    assert layer.model_dump(exclude_unset=True) == {}
    assert GraphSettings.model_validate({"flow": None}).model_dump(exclude_unset=True) == {
        "flow": None
    }


def test_graph_layer_does_not_serialize_unset_new_fields() -> None:
    """그래프 버전 해시는 전체 직렬화로 계산하므로, 지정하지 않은 0.7.0 필드는 나타나지 않는다."""
    graph = Graph.model_validate(
        {"id": "g", "name": "g", "settings": {"delegation": {"max_depth": 2}}}
    )
    full = graph.model_dump(mode="json")
    assert "flow" not in full["settings"]
    assert full["settings"]["delegation"] == {"max_depth": 2}
    assert graph.settings is not None
    assert graph.settings.delegation is not None
    assert graph.settings.delegation.max_nesting == 3  # 값은 모델 기본값 그대로 읽힌다
    set_graph = Graph.model_validate(
        {
            "id": "g",
            "name": "g",
            "settings": {"flow": {"max_iterations": 2}, "delegation": {"max_nesting": 2}},
        }
    )
    full = set_graph.model_dump(mode="json")
    assert full["settings"]["flow"] == {"max_iterations": 2, "max_node_runs": 200}
    assert full["settings"]["delegation"] == {"max_depth": None, "max_nesting": 2}
    # JSON 직렬화도 같다
    assert json.loads(graph.model_dump_json())["settings"]["delegation"] == {"max_depth": 2}


def test_graph_settings_schemas_keep_properties() -> None:
    """직렬화 훅이 스키마를 일반 객체로 바꾸지 않는다(폼·OpenAPI·TS 생성)."""
    for mode in ("validation", "serialization"):
        schema = GraphSettings.model_json_schema(mode=mode)
        assert "flow" in schema["properties"], mode
        assert "delegation" in schema["properties"], mode
    defs = build_schema()["$defs"]
    assert "flow" in defs["GraphSettings"]["properties"]
    assert "flow" in defs["WorkspaceSettings"]["properties"]
    assert "max_nesting" in defs["DelegationSettings"]["properties"]


# ---------------------------------------------------------------- 표 8·9


def test_v6_issue_codes_are_documented_constants() -> None:
    assert {
        KnownIssueCodes.FLOW_MAX_ITERATIONS_INVALID,
        KnownIssueCodes.FLOW_MAX_NODE_RUNS_EXCEEDED,
        KnownIssueCodes.CONDITION_UNKNOWN_OPERATOR,
        KnownIssueCodes.CONDITION_INVALID_VALUE,
        KnownIssueCodes.TEAM_MIXED_STRATEGIES,
        KnownIssueCodes.TEAM_RECURSIVE,
        KnownIssueCodes.TEAM_NESTING_EXCEEDED,
        KnownIssueCodes.TEAM_TEAM_NOT_FOUND,
        KnownIssueCodes.TEAM_CHILD_NO_ENTRY,
        KnownIssueCodes.DELEGATION_DEPTH_EXCEEDED,
    } == {
        "flow.max_iterations_invalid",
        "flow.max_node_runs_exceeded",
        "condition.unknown_operator",
        "condition.invalid_value",
        "team.mixed_strategies",
        "team.recursive",
        "team.nesting_exceeded",
        "team.team_not_found",
        "team.child_no_entry",
        "delegation.depth_exceeded",
    }
    # 문서 상수: 클래스 이름이 아니라 이름 → 값 표(KNOWN_ISSUE_CODES)로만 나간다(5.2R.3 후속)
    assert "KnownIssueCodes" not in json.dumps(build_schema()["x-constants"])
    assert build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]["TEAM_RECURSIVE"] == "team.recursive"


def test_rest_models_are_in_schema() -> None:
    defs = build_schema()["$defs"]
    assert "ConditionOperatorDescriptor" in defs
    assert "ConditionSpec" in defs
    assert defs["RunSnapshot"]["properties"]["children"]
