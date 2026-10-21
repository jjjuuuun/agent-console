"""계약 v5(design §4R.9 표 1~5, 0.6.0): 하위 모듈 `logs`, `WorkspaceSettings.logs`,
`ObserveSettings.collectors`·`hook_probe`·`CollectorDescriptor`, WS `logs.ingested`, 로그 이슈 코드.

"생략 = 상속" 왕복을 `logs.*`·`observe.*`로 넓히고,
layout 모델 "모르는 키 보존"을 모델 단독으로 확인한다(3R 후속, W4 QA).
"""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    LOG_EVENT_ORDERS,
    LOG_PROJECT_UNGROUPED,
    AgentSettings,
    BackendDescriptor,
    CollectorDescriptor,
    EdgeLayout,
    Graph,
    GraphUiLayout,
    HandoffCount,
    HandoffMatrix,
    KnownIssueCodes,
    KnownLogCategories,
    KnownLogDimensions,
    KnownLogMetrics,
    KnownLogTones,
    LogAggregateRequest,
    LogAggregateRow,
    LogArchive,
    LogClassifierDescriptor,
    LogEvent,
    LogEventDetail,
    LogEventPage,
    LogProjectSettings,
    LogQuerySchema,
    LogScanReport,
    LogSessionSummary,
    LogSettings,
    LogsIngestedMessage,
    LogSourceDescriptor,
    LogSourceInfo,
    LogTaxonomy,
    LogTimeline,
    LogWidget,
    NodeLayout,
    ObserveSettings,
    WorkspaceSettings,
    WsServerMessage,
    build_schema,
)
from agent_console_contracts import logs as logs_module

EVENT: dict[str, Any] = {
    "uid": "u1",
    "seq": 7,
    "source": "zz-source",
    "observed_at": 10.5,
    "category": "zz-category",
}


# ---------------------------------------------------------------- 버전·하위 모듈


def test_contracts_version_is_v5_or_later() -> None:
    """버전 값 자체는 v7 테스트가 고정한다(0.8.0). 여기서는 v5에서 생긴 것만 본다."""
    assert tuple(int(x) for x in CONTRACTS_VERSION.split(".")) >= (0, 6, 0)
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS
    assert CONTRACT_VERSIONS["logs"] == "1.0.0"
    assert tuple(int(x) for x in CONTRACT_VERSIONS["modules"].split(".")) >= (1, 1, 0)
    # logs는 definitions 아래 층(설정 모델을 definitions가 쓴다)
    assert CONTRACT_SUBMODULES.index("logs") < CONTRACT_SUBMODULES.index("definitions")


def test_logs_submodule_groups_log_models() -> None:
    grouped = build_schema()["x-modules"]
    expected = {
        "LogEvent",
        "LogDocumentRef",
        "LogEventPage",
        "LogEventDetail",
        "LogEvidenceLink",
        "LogSourceDescriptor",
        "LogClassifierDescriptor",
        "LogSourceInfo",
        "LogScanReport",
        "LogSessionSummary",
        "LogTimeline",
        "LogAggregateRequest",
        "LogAggregateRow",
        "LogTaxonomy",
        "LogArchive",
        "LogSettings",
        "LogDashboard",
        "LogWidget",
    }
    assert expected <= set(grouped["logs"])
    assert "CollectorSetting" in grouped["definitions"]
    assert "CollectorDescriptor" in grouped["runs"]
    assert "LogsIngestedMessage" in grouped["modules"]


# ---------------------------------------------------------------- 표 1: 이벤트


def test_log_event_from_alias_round_trip() -> None:
    doc = {**EVENT, "from": ["main"], "to": ["helper"], "via": "Task"}
    event = LogEvent.model_validate(doc)
    assert event.from_ == ["main"]
    assert event.model_dump(mode="json", exclude_unset=True) == doc
    assert "from_" not in event.model_dump_json()
    # 이름으로도 만들 수 있다(분류기 코드)
    by_name = LogEvent.model_validate({**EVENT, "from_": ["a"]})
    assert by_name.model_dump(exclude_unset=True)["from"] == ["a"]
    assert "from" in build_schema()["$defs"]["LogEvent"]["properties"]


def test_log_event_defaults_and_list_shape() -> None:
    event = LogEvent.model_validate(EVENT)
    assert (event.stage, event.status, event.evidence) == ("info", "", "observed")
    assert event.detail is None
    assert event.raw is None
    assert event.time is None
    assert event.duration_ms is None
    assert (event.from_, event.to, event.tags, event.documents) == ([], [], [], [])
    assert event.correlation == {}


def test_log_event_full_detail_round_trip() -> None:
    doc = {
        **EVENT,
        "ref": "proj/abc.jsonl",
        "title": "도구 호출",
        "summary": "Read a.py",
        "stage": "start",
        "status": "ok",
        "thread": "t1",
        "role": "subagent",
        "actor": "t1",
        "tool": "mcp__srv__do",
        "call_id": "toolu_1",
        "turn_id": "turn",
        "message_id": "msg_1",
        "session": "s1",
        "cwd": "/w",
        "repo_root": "/repo",
        "model": "zz-model",
        "run_id": "r1",
        "node_path": ["n1"],
        "time": 1.25,
        "duration_ms": 30.0,
        "evidence": "zz-inferred",
        "tags": ["zz-category", "tool"],
        "documents": [{"path": "SKILL.md", "kind": "skill", "action": "read"}],
        "correlation": {"session": "s1", "call_id": ["a", "b"]},
        "detail": {"input": {"x": 1}},
        "raw": [1, "two", None],
    }
    event = LogEvent.model_validate(doc)
    assert event.model_dump(mode="json", exclude_unset=True) == doc
    detail = LogEventDetail.model_validate(
        {
            "event": doc,
            "related": [EVENT],
            "evidence_links": [{"uid": "u2", "title": "결과", "basis": "call_id", "value": "a"}],
            "truncated": True,
        }
    )
    assert detail.event.detail == {"input": {"x": 1}}
    assert detail.related[0].detail is None
    # 근거 1000 상한(truncated)과 본문 잘림(detail_truncated)은 별개
    assert (detail.truncated, detail.detail_truncated, detail.usage) == (True, False, None)
    with_usage = LogEventDetail.model_validate(
        {
            "event": doc,
            "detail_truncated": True,
            "usage": {"thread": "t1", "message_id": "msg_1", "output_tokens": 5},
        }
    )
    assert with_usage.truncated is False
    assert with_usage.usage is not None
    assert with_usage.usage.output_tokens == 5
    assert with_usage.usage.input_tokens is None


def test_log_names_are_open_strings_in_schema() -> None:
    """범주·단계·근거·출처·위젯 종류·차원·지표에 고정 값이 없다(R0.1)."""
    defs = build_schema()["$defs"]
    for name in (
        "LogEvent",
        "LogSourceDescriptor",
        "LogClassifierDescriptor",
        "LogSourceInfo",
        "LogAggregateRequest",
        "LogWidget",
        "LogWidgetQuery",
        "LogTaxonomy",
        "LogCategory",
        "CollectorDescriptor",
        "CollectorSetting",
    ):
        text = repr(defs[name])
        assert "'enum'" not in text, name
        assert "'const'" not in text, name
    widget = LogWidget.model_validate(
        {"id": "w", "kind": "zz-widget", "query": {"group_by": ["zz-dim"], "metric": "zz-metric"}}
    )
    assert widget.query.metric == "zz-metric"
    info = LogSourceInfo.model_validate(
        {"descriptor": {"id": "s", "title": "S", "format": "f"}, "enabled": True, "origin": "zz"}
    )
    assert info.origin == "zz"
    assert info.status.refs == 0


def test_known_log_categories_are_documentation_only() -> None:
    values = [v for k, v in vars(KnownLogCategories).items() if k.isupper()]
    assert {"tool_call", "tool_result", "mcp", "hook", "handoff", "error", "other"} <= set(values)
    assert all(isinstance(v, str) for v in values)
    constants = build_schema()["x-constants"]
    assert "agents_md" not in repr(constants)
    assert "KnownLogCategories" not in build_schema()["$defs"]


def test_descriptors_defaults() -> None:
    source = LogSourceDescriptor(id="zz", title="Z", format="zz-format")
    assert (source.default_enabled, source.reads_paths, source.config_schema) == (False, True, {})
    classifier = LogClassifierDescriptor(id="c", title="C")
    assert classifier.formats == []


def test_pages_reports_and_aggregates() -> None:
    page = LogEventPage()
    assert (page.items, page.total, page.next_cursor) == ([], None, None)
    report = LogScanReport.model_validate(
        {
            "started_at": 1,
            "finished_at": 2,
            "sources": [
                {"source_id": "s", "new_events": 3, "diagnostics": 1},
                {"source_id": "t", "error_code": "zz-failed", "message": "읽기 실패"},
            ],
            "new_events": 3,
            "max_seq": 9,
        }
    )
    assert report.sources[0].read_bytes == 0
    assert report.sources[0].error_code is None
    assert report.sources[1].new_events == 0
    with pytest.raises(ValidationError):
        LogScanReport.model_validate({"started_at": 1, "finished_at": 2, "new_events": -1})
    request = LogAggregateRequest.model_validate(
        {"group_by": ["project", "model"], "metric": "tokens.total", "tz": "Asia/Seoul"}
    )
    assert request.filter == {}
    row = LogAggregateRow.model_validate({"keys": {"project": "p", "model": None}})
    assert row.value is None  # 값이 없으면 null(0으로 채우지 않음)


def test_session_timeline_and_archive_round_trip() -> None:
    session = {
        "session": "s1",
        "sources": ["zz-source"],
        "first_time": 1.0,
        "last_time": 2.0,
        "events": 2,
        "errors": 1,
        "thread_count": 2,
        "project": {"id": "zz-group", "label": "Z"},
        "models": ["zz-model"],
        "tokens": {"input": 3, "output": 4, "cache_read": None, "total": 7},
    }
    lanes = [{"id": "main"}, {"id": "t2", "label": "helper", "parent_id": "main"}]
    summary = LogSessionSummary.model_validate(session)
    assert summary.model_dump(mode="json", exclude_unset=True) == session
    bare = LogSessionSummary.model_validate({"session": "s"})
    assert (bare.project, bare.tokens, bare.thread_count, bare.models) == (None, None, 0, [])
    timeline = LogTimeline.model_validate(
        {"session": session, "lanes": lanes, "events": [{**EVENT, "duration_ms": 12.5}]}
    )
    assert timeline.lanes[1].parent_id == "main"
    assert timeline.lanes[0].label is None
    assert timeline.events[0].duration_ms == 12.5
    archive = {
        "version": 1,
        "exported_at": 3.0,
        "filter": {"session": "s1"},
        "taxonomy": {"categories": {"zz-category": {"label": "Z"}}},
        "lanes": lanes,
        "sessions": [session],
        "events": [{**EVENT, "from": ["main"], "detail": {"k": "v"}}],
        "evidence_links": {"u1": [{"uid": "u2", "basis": "call_id", "value": "x"}]},
    }
    parsed = LogArchive.model_validate(archive)
    assert parsed.model_dump(mode="json", exclude_unset=True) == archive
    assert LogArchive.model_validate_json(parsed.model_dump_json()) == parsed


def test_screen_inputs_l1_to_l10() -> None:
    """4R.2 화면 명세 미확정 항목(screen-logs §10)을 확정한 design §4R.9 필드 보강 표."""
    # L1: 범주 강조(tone, 열린 문자열). 오류 표시 근거는 tone == danger뿐(F-25)
    taxonomy = LogTaxonomy.model_validate(
        {"categories": {"zz-cat": {"tone": KnownLogTones.DANGER}, "b": {"tone": "zz-tone"}}}
    )
    assert taxonomy.categories["zz-cat"].tone == "danger"
    assert taxonomy.categories["b"].tone == "zz-tone"
    # L4: 타임라인 상한
    timeline = LogTimeline.model_validate(
        {"session": {"session": "s"}, "total": 9, "truncated": True}
    )
    assert (timeline.total, timeline.truncated) == (9, True)
    assert LogTimeline.model_validate({"session": {"session": "s"}}).truncated is False
    # L6: 차원·지표·필터 목록(서버 데이터)
    schema = LogQuerySchema.model_validate(
        {
            "dimensions": [{"id": "day", "kind": "time"}, {"id": "zz-dim"}],
            "metrics": [{"id": "tokens.total", "unit": "tokens"}],
            "filters": [{"id": "category", "multi": True}, {"id": "q"}],
        }
    )
    assert schema.dimensions[0].kind == "time"
    assert schema.filters[0].multi is True
    assert schema.filters[1].multi is None
    assert KnownLogDimensions.DAY == "day"
    assert KnownLogMetrics.TOKENS_TOTAL == "tokens.total"
    # 위젯 크기: options 예약 키 w·h(좌표 없음), 기간은 절대 시각으로 filter에(F-22·F-23)
    widget = LogWidget.model_validate(
        {
            "id": "w",
            "kind": "k",
            "query": {"metric": "events", "filter": {"since": 1.0}},
            "options": {"w": 2, "h": 1, "zz": True},
        }
    )
    assert widget.options == {"w": 2, "h": 1, "zz": True}
    # L5: handoff 셀 {from, to, via?, count} + 옛 source·target·kind(하위 호환)
    cell = HandoffCount.model_validate({"from": "main", "to": "qa", "via": "Task", "count": 2})
    assert (cell.source, cell.target, cell.kind) == ("main", "qa", "Task")
    assert cell.model_dump(mode="json")["from"] == "main"
    old = HandoffMatrix.model_validate(
        {"cells": [{"source": "a", "target": "b", "count": 1}], "runs": 1}
    )
    assert (old.cells[0].from_, old.cells[0].to, old.cells[0].via) == ("a", "b", None)
    # L9: 정렬 어휘·묶이지 않음 예약 값
    assert LOG_EVENT_ORDERS == ("asc", "desc")
    constants = build_schema()["x-constants"]
    assert constants["LOG_EVENT_ORDERS"] == ["asc", "desc"]
    assert constants["LOG_PROJECT_UNGROUPED"] == LOG_PROJECT_UNGROUPED == "~ungrouped"


# ---------------------------------------------------------------- 표 2: WorkspaceSettings.logs


def test_workspace_logs_omitted_is_inherited() -> None:
    settings = WorkspaceSettings.model_validate({})
    assert "logs" not in settings.model_dump(exclude_unset=True)
    assert settings.logs.sources is None
    assert settings.logs.taxonomy is None
    assert settings.logs.projects is None
    assert settings.logs.dashboards is None
    empty = WorkspaceSettings.model_validate({"logs": {}})
    assert empty.model_dump(mode="json", exclude_unset=True) == {"logs": {}}


@pytest.mark.parametrize(
    "logs",
    [
        {"sources": []},
        {"sources": [{"id": "zz-source"}]},
        {"sources": [{"id": "zz-source", "enabled": False}]},
        {"sources": [{"id": "s", "enabled": True, "config": {"roots": ["/x"], "zz": 1}}]},
        {"sources": [{"id": "s", "config": {"classifier": {"id": "zz-cls", "config": {}}}}]},
        {"taxonomy": {}},
        {"taxonomy": {"categories": {"zz-cat": {"visible": False}}}},
        {"taxonomy": {"categories": {"tool": {"label": "도구", "color": "zz-token"}}}},
        {"taxonomy": {"order": ["b", "a"]}},
        {"projects": {}},
        {"projects": {"git_worktrees": False}},
        {"projects": {"ungrouped": "none"}},
        {"projects": {"groups": [{"id": "g", "match": ["/proj/**"]}]}},
        {"dashboards": []},
        {
            "dashboards": [
                {
                    "id": "d",
                    "title": "기본",
                    "widgets": [
                        {
                            "id": "w",
                            "kind": "bar",
                            "query": {"group_by": ["project", "model"], "metric": "tokens.total"},
                        },
                        {
                            "id": "w2",
                            "kind": "zz-widget",
                            "title": "t",
                            "query": {"metric": "events", "filter": {"category": "mcp"}},
                            "options": {"stacked": True},
                        },
                    ],
                }
            ]
        },
    ],
)
def test_workspace_logs_round_trip(logs: dict[str, Any]) -> None:
    settings = WorkspaceSettings.model_validate({"logs": logs})
    assert settings.model_dump(mode="json", exclude_unset=True) == {"logs": logs}


def test_log_settings_keep_unknown_keys() -> None:
    """손으로 고친 settings.yaml의 모르는 키는 보존된다(DefinitionModel)."""
    doc = {
        "zz-future": {"a": 1},
        "sources": [{"id": "s", "zz-extra": [1]}],
        "taxonomy": {"zz-t": 1, "categories": {"c": {"zz-c": True}}},
        "projects": {"zz-p": "kept", "groups": [{"id": "g", "zz-g": 2}]},
        "dashboards": [
            {
                "id": "d",
                "title": "T",
                "zz-d": 3,
                "widgets": [{"id": "w", "kind": "k", "query": {"metric": "m", "zz-q": 4}}],
            }
        ],
    }
    parsed = LogSettings.model_validate(doc)
    assert parsed.model_dump(mode="json", exclude_unset=True) == doc


def test_ungrouped_policy_is_fixed_vocabulary() -> None:
    for value in ("cwd", "repo_root", "none"):
        assert LogProjectSettings.model_validate({"ungrouped": value}).ungrouped == value
    with pytest.raises(ValidationError):
        LogProjectSettings.model_validate({"ungrouped": "zz"})


def test_existing_settings_yaml_reads_unchanged() -> None:
    """0.5.x 형식 settings.yaml(로그 키 없음, 옛 observe 키)이 그대로 읽히고 그대로 써진다."""
    doc = {
        "schema_version": 1,
        "agent_defaults": {
            "backend": "zz-backend",
            "observe": {"hooks": True, "mcp": False, "hook_events": ["PreToolUse"]},
        },
        "usage": {"sources": [{"id": "u", "enabled": True}]},
        "ui": {"versions": {}},
        "console": {"kept": True},
    }
    settings = WorkspaceSettings.model_validate(doc)
    assert settings.model_dump(mode="json", exclude_unset=True) == doc


# ---------------------------------------------------------------- 표 3: 관측 수집기


def test_observe_new_fields_omitted_is_inherited() -> None:
    observe = ObserveSettings.model_validate({})
    assert observe.collectors is None
    assert observe.hook_probe is None
    assert observe.model_dump(exclude_unset=True) == {}
    agent = AgentSettings.model_validate({"observe": {"hooks": True}})
    assert agent.model_dump(exclude_unset=True) == {"observe": {"hooks": True}}


@pytest.mark.parametrize(
    "observe",
    [
        {"hook_probe": False},
        {"hook_probe": True},
        {"collectors": {}},
        {"collectors": {"zz-collector": {}}},
        {"collectors": {"zz-collector": {"enabled": False}}},
        {"collectors": {"c": {"config": {"events": ["PreToolUse"], "zz": 1}}}},
        {"collectors": {"c": {"enabled": True, "config": None}}},
        {"hooks": True, "collectors": {"c": {"enabled": False}}},
    ],
)
def test_observe_round_trip(observe: dict[str, Any]) -> None:
    graph = Graph.model_validate({"id": "g", "name": "g", "settings": {"observe": observe}})
    assert graph.model_dump(mode="json", exclude_unset=True)["settings"] == {"observe": observe}
    settings = WorkspaceSettings.model_validate({"agent_defaults": {"observe": observe}})
    dumped = settings.model_dump(mode="json", exclude_unset=True)
    assert dumped == {"agent_defaults": {"observe": observe}}


def test_collector_descriptor_and_backend_collectors() -> None:
    collector = CollectorDescriptor.model_validate(
        {"id": "zz-c", "title": "Z", "backend": "zz-backend", "emits": ["zz.*"]}
    )
    assert collector.config_schema == {}
    # 0.5.x 백엔드 디스크립터는 그대로 읽힌다(collectors 기본 빈 목록)
    backend = BackendDescriptor.model_validate({"id": "b", "title": "B"})
    assert backend.collectors == []
    assert "collectors" not in backend.model_dump(exclude_unset=True)
    with_collectors = BackendDescriptor.model_validate(
        {"id": "b", "title": "B", "collectors": [collector.model_dump()]}
    )
    assert with_collectors.collectors[0].backend == "zz-backend"


# ---------------------------------------------------------------- 표 4·5: WS·이슈 코드


def test_ws_logs_ingested_message() -> None:
    message = WsServerMessage.model_validate(
        {"type": "logs.ingested", "payload": {"source_ids": ["a"], "count": 2, "max_seq": 40}}
    )
    assert isinstance(message.root, LogsIngestedMessage)
    assert message.root.payload.max_seq == 40
    with pytest.raises(ValidationError):
        WsServerMessage.model_validate({"type": "logs.ingested", "payload": {"count": -1}})


def test_log_issue_codes_are_documented_constants() -> None:
    assert KnownIssueCodes.LOGS_SOURCE_FAILED == "logs.source_failed"
    assert KnownIssueCodes.LOGS_REDACTION_UNAVAILABLE == "logs.redaction_unavailable"
    assert KnownIssueCodes.LOGS_STORAGE_MEMORY == "logs.storage_memory"
    assert KnownIssueCodes.LOGS_UNKNOWN_CLASSIFIER == "logs.unknown_classifier"
    # 이름 → 값 표로만 나간다(열린 문자열, 5.2R.3 후속).
    table = build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]
    assert table["LOGS_SOURCE_FAILED"] == "logs.source_failed"


def test_logs_submodule_is_usable_alone() -> None:
    """`logs` 하위 모듈은 `common`만 쓴다(설정·이벤트 모델을 기능 패키지가 단독으로 import)."""
    assert logs_module.LogSettings is LogSettings
    assert set(logs_module.__all__) >= {"LogEvent", "LogSettings", "KnownLogCategories"}


# ---------------------------------------------------------------- 3R 후속: layout 모르는 키 보존


@pytest.mark.parametrize(
    ("model", "doc"),
    [
        (NodeLayout, {"direction": "tb", "zz-future": {"kept": [1]}}),
        (NodeLayout, {"zz-only": "x"}),
        (EdgeLayout, {"shape": "step", "zz-future": 1, "waypoints": [{"x": 1, "y": 2}]}),
        (EdgeLayout, {"label_offset": {"x": 1, "y": 2}, "zz": None}),
        (GraphUiLayout, {"direction": "lr", "zz-future": {"a": "b"}}),
        (GraphUiLayout, {"edge_shape_by_kind": {"k": "s"}, "zz": [1, 2]}),
    ],
)
def test_layout_models_keep_unknown_keys(model: type[NodeLayout], doc: dict[str, Any]) -> None:
    parsed = model.model_validate(doc)
    assert parsed.model_dump(mode="json", exclude_unset=True) == doc
    assert model.model_validate_json(parsed.model_dump_json(exclude_unset=True)) == parsed


def test_edge_traversed_payload_kind_is_optional() -> None:
    """4R.18 요청: edge.traversed payload에 연결 종류 id(선택, 0.5.x 이벤트도 그대로 읽힘)."""
    from agent_console_contracts import EdgeTraversedPayload

    base = {
        "edge_id": "e",
        "source": {"node": "a", "port": "o"},
        "target": {"node": "b", "port": "i"},
    }
    assert EdgeTraversedPayload.model_validate(base).kind is None
    assert EdgeTraversedPayload.model_validate({**base, "kind": "zz-kind"}).kind == "zz-kind"
