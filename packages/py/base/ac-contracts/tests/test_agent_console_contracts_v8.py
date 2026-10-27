"""계약 v8(design §5.5R.2.4, 0.9.0): 하위 모듈 `architecture` 1.0.0, `runs` 1.4.0, `common` 1.4.0.

- 구조도 프로필·사용자 설정은 사용자 데이터다: YAML 예시 → 모델 → JSON 왕복,
  모든 층에서 모르는 키 보존.
- 투영 결과의 지표 `value: null`(수집 안 됨)은 0으로 바뀌지 않는다(R8.8).
- `runs`: `agent.context_prepared`(본문 없음), `node.*` `tool_use_id`, `agent.message`·`agent.usage`
  `duration_ms`. 새 필드는 전부 선택이라 옛 이벤트가 그대로 읽힌다.
"""

import json
from io import StringIO
from typing import Any

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

import agent_console_contracts as root
from agent_console_contracts import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    KNOWN_RUN_EVENT_TYPES,
    X_UI,
    ErrorCodes,
    XUiKeys,
    build_schema,
    parse_run_event,
    x_ui,
)
from agent_console_contracts import architecture as arch
from agent_console_contracts.runs import (
    AgentContextPreparedEvent,
    AgentMessageEvent,
    AgentUsageEvent,
    NodeStatusEvent,
)
from agent_console_contracts.schema_help import contract_form_roots, lint_schema_help

# 사용자가 손으로 쓴 설정 YAML(design §5.5R.2.2·§5.5R.2.3, 화면 명세 §9 모양). 모든 층에 모르는 키
# (`x-*`)를 둔다. 칸·연결·영역·출처 이름은 일부러 기본 프로필과 다른 임의 이름이다.
SETTINGS_YAML = """\
include_defaults: false
default_profile: zz-view
x-settings-note: 사용자 메모
profiles:
  agent-architecture: null
  zz-view:
    title: 임의 구조도
    canvas: {width: 1520, height: 812, x-grid: 10}
    zones:
      - {id: zz-outer, label: "바깥", description: "설명 줄", x: 10, y: 16, w: 1260, h: 780,
         style: zz-boundary, x-zone-note: 1}
    error_when: {any: [{path: /status, op: in, value: [failed, error]}]}
    source_priority: [zz-kind-a, zz-kind-b]
    group_limit: 3
    unassigned: false
    options: {inferred_llm_duration: true, x-option: kept}
    x-profile-note: {nested: [1, 2]}
    cells:
      c1:
        label: 칸 하나
        description: 첫 칸
        x: 130
        y: 130
        tone: zz-tone
        when: {all: [{path: /category, op: eq, value: zz-cat}]}
        metrics: [count, errors, tokens, zz-metric]
        unavailable: [{item: 본문, reason: 로그에 없음, x-item: 1}]
        x-cell-note: kept
      c2:
        label: 묶는 칸
        view: zz-grouped
        group_by: /thread
        drill: {filter: thread, value: "{group}", x-drill: true}
        w: 200
        h: 80
    edges:
      - {id: e1, from: c1, to: c2, label: 연결, kind: observed, style: zz-style,
         points: [[226, 130], [374, 130]], label_at: [300, 130], label_max_w: 92,
         when: {all: [{path: /tool, op: exists}]}, metrics: [count, duration], x-edge-note: e}
      - {id: e2, from: c2, to: c1, kind: zz-unknown-kind}
    coverage:
      zz-kind-a: {cells: [c1, c2], partial: {c2: 일부만 기록됨}, x-coverage: 1}
      zz-kind-b: {cells: [c1]}
"""


def _yaml_load(text: str) -> Any:
    return YAML(typ="safe").load(StringIO(text))


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _null_paths(doc: Any, at: str = "") -> set[str]:
    """JSON 문서에서 값이 null인 경로 모음(0으로 바뀌지 않았는지 볼 때)."""
    found: set[str] = set()
    if isinstance(doc, dict):
        for key, value in doc.items():
            if value is None:
                found.add(f"{at}/{key}")
            found |= _null_paths(value, f"{at}/{key}")
    elif isinstance(doc, list):
        for i, value in enumerate(doc):
            found |= _null_paths(value, f"{at}/{i}")
    return found


# ---------------------------------------------------------------- 버전·하위 모듈


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_v8() -> None:
    """0.9.0에서 정한 버전 이상이다(정확한 지금 값은 v9 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 9, 0)
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS
    v8 = {
        "common": "1.4.0",
        "resources": "1.1.0",
        "logs": "1.0.0",
        "definitions": "1.3.0",
        "runs": "1.4.0",
        "usage": "1.1.0",
        "projects": "1.0.0",
        "chat": "1.1.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "modules": "1.2.0",
    }
    for sub, version in v8.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_architecture_submodule_sits_with_chat_exports_imports() -> None:
    order = list(CONTRACT_SUBMODULES)
    assert order.index("runs") < order.index("architecture") < order.index("modules")
    assert order.index("logs") < order.index("architecture")
    grouped = build_schema()["x-modules"]
    assert {
        "ArchitectureSettings",
        "ArchitectureProfile",
        "ArchitectureCell",
        "ArchitectureEdge",
        "ArchitectureZone",
        "ArchitectureProfileInfo",
        "ArchitectureView",
        "ArchitectureCellView",
        "ArchitectureEdgeView",
        "ArchitectureGroupView",
        "ArchitectureMetric",
        "ArchitectureSelector",
        "ArchitectureMembership",
        "ArchitectureProjectRequest",
    } <= set(grouped["architecture"])
    # 다른 하위 모듈의 모델은 그 하위 모듈에 남는다
    assert "LogEvent" in grouped["logs"]
    assert "ConditionSpec" in grouped["runs"]
    for name in arch.__all__:
        assert getattr(root, name) is getattr(arch, name), name


# ---------------------------------------------------------------- 프로필·설정 왕복(사용자 데이터)


def test_settings_yaml_round_trip_keeps_everything() -> None:
    """YAML 예시 → 모델 → JSON → 모델: 적은 값과 모르는 키가 그대로 남는다."""
    data = _yaml_load(SETTINGS_YAML)
    settings = arch.ArchitectureSettings.model_validate(data)
    dumped = _dump(settings)
    assert dumped == json.loads(json.dumps(data))
    again = arch.ArchitectureSettings.model_validate(json.loads(json.dumps(dumped)))
    assert again == settings
    assert _dump(again) == dumped


def test_unknown_keys_are_preserved_at_every_level() -> None:
    settings = arch.ArchitectureSettings.model_validate(_yaml_load(SETTINGS_YAML))
    dumped = _dump(settings)
    profile = dumped["profiles"]["zz-view"]
    assert dumped["x-settings-note"] == "사용자 메모"
    assert profile["x-profile-note"] == {"nested": [1, 2]}
    assert profile["canvas"]["x-grid"] == 10
    assert profile["zones"][0]["x-zone-note"] == 1
    assert profile["options"]["x-option"] == "kept"
    assert profile["cells"]["c1"]["x-cell-note"] == "kept"
    assert profile["cells"]["c1"]["unavailable"][0]["x-item"] == 1
    assert profile["cells"]["c2"]["drill"]["x-drill"] is True
    assert profile["edges"][0]["x-edge-note"] == "e"
    assert profile["coverage"]["zz-kind-a"]["x-coverage"] == 1


def test_open_names_are_not_validated_by_the_contract() -> None:
    """칸·연결 종류·지표·색·모양 이름은 열린 문자열이다(값 검사는 프로필 검사 몫)."""
    settings = arch.ArchitectureSettings.model_validate(_yaml_load(SETTINGS_YAML))
    profile = settings.profiles["zz-view"]
    assert profile is not None
    assert profile.edges[1].kind == "zz-unknown-kind"
    assert profile.cells["c1"].metrics == ["count", "errors", "tokens", "zz-metric"]
    assert profile.cells["c1"].tone == "zz-tone"
    assert profile.zones[0].style == "zz-boundary"
    # 선언 순서(= Tab 순서)가 유지된다
    assert list(profile.cells) == ["c1", "c2"]


def test_null_profile_means_disable_and_survives_round_trip() -> None:
    settings = arch.ArchitectureSettings.model_validate(_yaml_load(SETTINGS_YAML))
    assert "agent-architecture" in settings.profiles
    assert settings.profiles["agent-architecture"] is None
    assert _dump(settings)["profiles"]["agent-architecture"] is None


def test_settings_defaults_and_omit_unset() -> None:
    empty = arch.ArchitectureSettings()
    assert empty.include_defaults is True
    assert empty.default_profile is None
    assert empty.profiles == {}
    assert _dump(empty) == {}
    profile = arch.ArchitectureProfile()
    assert profile.group_limit == arch.DEFAULT_GROUP_LIMIT
    assert profile.unassigned is True
    assert profile.cells == {}
    assert profile.edges == []
    assert arch.ArchitectureEdge.model_validate({"id": "e", "from": "a", "to": "b"}).kind == (
        arch.KnownArchitectureEdgeKinds.OBSERVED
    )


def test_edge_from_uses_alias_both_ways() -> None:
    by_alias = arch.ArchitectureEdge.model_validate({"id": "e", "from": "a", "to": "b"})
    by_name = arch.ArchitectureEdge.model_validate({"id": "e", "from_": "a", "to": "b"})
    assert by_alias == by_name
    assert by_name.model_dump(mode="json", exclude_unset=True) == {
        "id": "e",
        "from": "a",
        "to": "b",
    }
    props = build_schema()["$defs"]["ArchitectureEdge"]["properties"]
    assert "from" in props
    assert "from_" not in props


@pytest.mark.parametrize("bad", [[1], [1, 2, 3], ["a", 2]])
def test_points_are_two_numbers(bad: list[Any]) -> None:
    with pytest.raises(ValidationError):
        arch.ArchitectureEdge.model_validate(
            {"id": "e", "from": "a", "to": "b", "points": [[0, 0], bad]}
        )
    with pytest.raises(ValidationError):
        arch.ArchitectureEdge.model_validate({"id": "e", "from": "a", "to": "b", "label_at": bad})


def test_zone_description_and_label_max_w_are_formal_fields() -> None:
    """화면 명세의 영역 설명·라벨 최대 폭은 정식 필드다(투영 결과로 그대로 옮겨진다)."""
    zone_props = build_schema()["$defs"]["ArchitectureZone"]["properties"]
    edge_props = build_schema()["$defs"]["ArchitectureEdge"]["properties"]
    view_props = build_schema()["$defs"]["ArchitectureEdgeView"]["properties"]
    assert "description" in zone_props
    assert "label_max_w" in edge_props
    assert "label_max_w" in view_props
    with pytest.raises(ValidationError):
        arch.ArchitectureEdge.model_validate({"id": "e", "from": "a", "to": "b", "label_max_w": 0})


def test_settings_form_help_is_complete() -> None:
    """설정 폼 뿌리에 들어가고, 모든 필드에 라벨·설명·분류가 있다(도움말 린트 0건)."""
    roots = contract_form_roots()
    assert "ArchitectureSettings" in roots
    assert "ArchitectureProfile" in roots
    issues = lint_schema_help(
        build_schema(), roots=("ArchitectureSettings", "ArchitectureProfile"), objects=True
    )
    assert issues == []
    profiles = build_schema()["$defs"]["ArchitectureSettings"]["properties"]["profiles"]
    assert profiles[X_UI][XUiKeys.WIDGET] == "architecture-profiles"


def test_x_ui_widget_key() -> None:
    assert XUiKeys.WIDGET == "widget"
    assert x_ui(tier="basic", widget="zz") == {X_UI: {"tier": "basic", "widget": "zz"}}
    assert XUiKeys.WIDGET not in x_ui(tier="basic")[X_UI]


# ---------------------------------------------------------------- 투영 결과(지표 null ≠ 0)


def _selector(target: str) -> dict[str, Any]:
    return {"arch": f"zz-view:{target}"}


VIEW: dict[str, Any] = {
    "profile": "zz-view",
    "title": "임의 구조도",
    "canvas": {"width": 800, "height": 400},
    "zones": [{"id": "z", "label": "바깥", "x": 0, "y": 0, "w": 800, "h": 400}],
    "cells": [
        {
            "id": "c1",
            "label": "칸 하나",
            "x": 130,
            "y": 130,
            "w": 180,
            "h": 68,
            "status": "observed",
            "metrics": {
                "count": {"status": "observed", "value": 0},
                "errors": {"status": "observed", "value": 0},
                "tokens": {"status": "not_collected", "value": None},
                "duration": {
                    "status": "observed",
                    "value": 120.5,
                    "detail": {"samples": 2, "total_ms": 241, "avg_ms": 120.5, "max_ms": 200},
                },
            },
            "selector": _selector("cell:c1"),
            "unavailable": [{"cell": "c1", "item": "본문", "reason": "로그에 없음"}],
        },
        {
            "id": "c2",
            "label": "묶는 칸",
            "w": 180,
            "h": 68,
            "status": "partial",
            "partial_reason": "일부만 기록됨",
            "metrics": {"count": {"status": "observed", "value": 3}},
            "selector": _selector("cell:c2"),
            "groups": [
                {
                    "key": "t-1",
                    "metrics": {"count": {"status": "observed", "value": 2}},
                    "selector": {**_selector("cell:c2"), "arch_group": "t-1"},
                    "drill": {"filter": "thread", "value": "t-1"},
                },
                {
                    "key": None,
                    "metrics": {"count": {"status": "observed", "value": 1}},
                    "selector": {**_selector("cell:c2"), "arch_group": ""},
                },
            ],
            "groups_rest": {"groups": 4, "metrics": {"count": {"status": "observed", "value": 9}}},
            "drillable": True,
        },
        {
            "id": "c3",
            "label": "빈 칸",
            "w": 180,
            "h": 68,
            "status": "not_collected",
            "metrics": {
                "count": {"status": "not_collected", "value": None},
                "inferred_duration": {"status": "inferred", "value": 1200},
            },
            "selector": _selector("cell:c3"),
        },
    ],
    "edges": [
        {
            "id": "e1",
            "from": "c1",
            "to": "c2",
            "kind": "observed",
            "points": [[226, 130], [374, 130]],
            "label_at": [300, 130],
            "label_max_w": 92,
            "status": "observed",
            "metrics": {"count": {"status": "observed", "value": 0}},
            "selector": {**_selector("edge:e1"), "arch_sources": ["src-a"]},
        },
        {
            "id": "e2",
            "from": "c2",
            "to": "c3",
            "kind": "structural",
            "status": "observed",
            "metrics": {},
            "selector": None,
        },
    ],
    "unassigned": {
        "metrics": {"count": {"status": "observed", "value": 5}},
        "selector": _selector("unassigned"),
    },
    "unavailable": [{"cell": "c1", "item": "본문", "reason": "로그에 없음"}],
    "sources": [{"id": "src-a", "kind": "zz-kind-a", "events": 8}],
    "event_total": 8,
    "max_seq": 42,
    "notes": [
        {
            "code": "architecture.profile_fallback",
            "message": "선택한 프로필이 없어 임의 구조도로 바꿨습니다.",
            "details": {"requested": "gone", "used": "zz-view"},
        }
    ],
}


def test_view_json_round_trip() -> None:
    view = arch.ArchitectureView.model_validate(VIEW)
    dumped = view.model_dump(mode="json", by_alias=True)
    again = arch.ArchitectureView.model_validate(json.loads(json.dumps(dumped)))
    assert again == view
    assert dumped["edges"][0]["from"] == "c1"
    assert dumped["edges"][1]["selector"] is None
    assert dumped["cells"][1]["groups"][1]["key"] is None


def test_null_metric_value_is_never_zero() -> None:
    """수집 안 됨(`value: null`)은 검증·직렬화·다시 읽기에서 0이 되지 않는다(R8.8)."""
    metric = arch.ArchitectureMetric.model_validate({"status": "not_collected"})
    assert metric.value is None
    assert metric.model_dump(mode="json")["value"] is None
    explicit = arch.ArchitectureMetric.model_validate({"status": "not_collected", "value": None})
    assert explicit.value is None
    zero = arch.ArchitectureMetric.model_validate({"status": "observed", "value": 0})
    assert zero.value == 0
    assert zero.value is not None

    view = arch.ArchitectureView.model_validate(VIEW)
    dumped = view.model_dump(mode="json", by_alias=True)
    nulls = _null_paths(dumped)
    assert "/cells/0/metrics/tokens/value" in nulls
    assert "/cells/2/metrics/count/value" in nulls
    assert dumped["cells"][0]["metrics"]["count"]["value"] == 0
    again = arch.ArchitectureView.model_validate(json.loads(json.dumps(dumped)))
    assert again.cells[2].metrics["count"].value is None
    assert again.cells[0].metrics["tokens"].value is None
    schema = build_schema()["$defs"]["ArchitectureMetric"]["properties"]["value"]
    assert {"type": "null"} in schema["anyOf"]


@pytest.mark.parametrize("status", ["zero", "unknown", ""])
def test_metric_and_item_status_are_closed(status: str) -> None:
    with pytest.raises(ValidationError):
        arch.ArchitectureMetric.model_validate({"status": status, "value": 1})
    bad = json.loads(json.dumps(VIEW))
    bad["cells"][0]["status"] = status
    with pytest.raises(ValidationError):
        arch.ArchitectureView.model_validate(bad)


def test_membership_and_selector() -> None:
    member = arch.ArchitectureMembership.model_validate(
        {
            "profile": "zz-view",
            "uid": "u1",
            "cells": ["c2", "c1"],
            "edges": ["e1"],
            "groups": [{"cell": "c2", "key": None}],
        }
    )
    assert member.unassigned is False
    assert member.cells == ["c2", "c1"]
    assert member.groups[0].key is None
    sel = arch.ArchitectureSelector.model_validate({"arch": "p:cell:c1"})
    assert sel.arch_group is None
    assert sel.arch_sources is None
    with pytest.raises(ValidationError):
        arch.ArchitectureSelector.model_validate({"arch": ""})


def test_project_request_and_profile_dtos() -> None:
    req = arch.ArchitectureProjectRequest.model_validate(
        {
            "inline": _yaml_load(SETTINGS_YAML)["profiles"]["zz-view"],
            "inline_id": "draft",
            "events": [
                {
                    "uid": "u1",
                    "seq": 1,
                    "source": "src-a",
                    "observed_at": 1.0,
                    "category": "zz-cat",
                }
            ],
            "tokens": [{"thread": "t", "message_id": "m", "input_tokens": 3}],
            "source_kinds": {"src-a": "zz-kind-a"},
            "error_categories": ["zz-error"],
        }
    )
    assert req.inline is not None
    assert req.inline.cells["c1"].label == "칸 하나"
    assert req.events[0].category == "zz-cat"
    assert req.tokens[0].input_tokens == 3
    assert req.profile is None

    info = arch.ArchitectureProfileInfo(id="p", origin="plugin:zz-dist", cells=2, edges=1)
    assert info.overrides is None
    assert info.disabled is False
    detail = arch.ArchitectureProfileDetail(
        id="p", origin=arch.KnownArchitectureOrigins.USER, profile=arch.ArchitectureProfile()
    )
    assert detail.problems == []
    listing = arch.ArchitectureProfileList(profiles=[info])
    assert listing.include_defaults is True
    check = arch.ArchitectureProfileCheckRequest.model_validate({"profile": {"cells": 3}})
    assert check.profile == {"cells": 3}  # 형식이 틀린 본문도 받는다(검사가 문제로 알림)
    assert arch.ArchitectureProfileCheckResult().issues == []


def test_architecture_error_codes() -> None:
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.ARCHITECTURE_PROFILE_NOT_FOUND] == 404
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.ARCHITECTURE_SCOPE_TOO_LARGE] == 422
    codes = build_schema()["x-constants"]["ERROR_CODES"]
    assert codes["ARCHITECTURE_SCOPE_TOO_LARGE"] == "architecture.scope_too_large"
    details = arch.ArchitectureScopeTooLargeDetails(events=300_000, limit=200_000)
    assert details.model_dump() == {"events": 300_000, "limit": 200_000}


# ---------------------------------------------------------------- runs 1.4.0


def _event(type_: str, payload: dict[str, Any], seq: int = 1) -> dict[str, Any]:
    return {
        "event_id": f"e{seq}",
        "run_id": "r",
        "seq": seq,
        "ts": 1.0,
        "node_path": ["n"],
        "type": type_,
        "payload": payload,
    }


def test_context_prepared_event_carries_no_body() -> None:
    raw = _event(
        "agent.context_prepared",
        {
            "resources": [
                {"id": "r1", "kind": "zz-kind", "bytes": 120, "sha256": "ab" * 32},
                {"id": "r2", "kind": "rules"},
            ],
            "fragments": 3,
        },
    )
    event = parse_run_event(raw)
    assert isinstance(event, AgentContextPreparedEvent)
    assert "agent.context_prepared" in KNOWN_RUN_EVENT_TYPES
    assert event.payload.resources[1].bytes is None
    fields = set(build_schema()["$defs"]["ContextResourceRef"]["properties"])
    assert fields == {"id", "kind", "bytes", "sha256"}
    payload_fields = set(build_schema()["$defs"]["AgentContextPreparedPayload"]["properties"])
    assert payload_fields == {"resources", "fragments"}
    assert parse_run_event(_event("agent.context_prepared", {})).payload.resources == []  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        parse_run_event(
            _event("agent.context_prepared", {"resources": [{"id": "r", "kind": "k", "bytes": -1}]})
        )


def test_node_events_carry_delegation_tool_use_id() -> None:
    event = parse_run_event(_event("node.started", {"status": "running", "tool_use_id": "tu-1"}))
    assert isinstance(event, NodeStatusEvent)
    assert event.payload.tool_use_id == "tu-1"
    old = parse_run_event(_event("node.completed", {"status": "succeeded"}))
    assert isinstance(old, NodeStatusEvent)
    assert old.payload.tool_use_id is None


def test_message_and_usage_carry_optional_duration() -> None:
    message = parse_run_event(
        _event("agent.message", {"role": "assistant", "text": "hi", "duration_ms": 850})
    )
    assert isinstance(message, AgentMessageEvent)
    assert message.payload.duration_ms == 850
    usage = parse_run_event(_event("agent.usage", {"usage": {}, "duration_ms": 0}))
    assert isinstance(usage, AgentUsageEvent)
    assert usage.payload.duration_ms == 0
    legacy = parse_run_event(_event("agent.usage", {"usage": {}}))
    assert isinstance(legacy, AgentUsageEvent)
    assert legacy.payload.duration_ms is None  # 모르면 null(추정해 채우지 않음)
    with pytest.raises(ValidationError):
        parse_run_event(_event("agent.message", {"role": "a", "text": "", "duration_ms": -1}))
