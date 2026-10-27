"""platform-runs 출처·분류기: seq 워터마크 증분, 세션 연결, 대응표·설정 덮어쓰기, 상관·식별."""

from __future__ import annotations

from agent_console_contracts import NodeRun
from agent_console_contracts.logs import LogEvent
from agent_console_link_logs_runs import (
    CLASSIFIER_ID,
    SOURCE_ID,
    PlatformRunsClassifier,
    PlatformRunsSource,
)
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogClassifier, LogFilter, LogSource, query_context


def _events(rig: PlatformRunsRig, **flt: object) -> list[LogEvent]:
    page = rig.index.query_events(LogFilter(limit=200).with_(**flt), query_context(None))
    return page.items


def test_source_and_classifier_satisfy_log_protocols() -> None:
    rig = PlatformRunsRig()
    assert isinstance(rig.item.source, LogSource)
    assert isinstance(rig.item.classifier, LogClassifier)
    assert isinstance(rig.item.source, PlatformRunsSource)
    assert isinstance(rig.item.classifier, PlatformRunsClassifier)
    desc = rig.item.source.descriptor
    assert (desc.id, desc.format, desc.default_enabled, desc.reads_paths) == (
        SOURCE_ID,
        CLASSIFIER_ID,
        True,
        False,
    )
    assert "event_map" in desc.config_schema["properties"]


def test_incremental_by_seq_watermark_without_duplicates() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record(status="running"))
    rig.records.events.append(run_event(1, "node.started", {"status": "running"}))
    assert rig.scan().new_events == 1
    assert rig.scan().new_events == 0  # 바뀌지 않음
    rig.records.events.append(run_event(2, "node.completed", {"status": "succeeded"}))
    assert rig.scan().new_events == 1
    assert [e.title for e in _events(rig)] == ["a running", "a succeeded"]
    cursor = rig.index.get_cursor(SOURCE_ID, "r1")
    assert cursor is not None
    assert cursor.offset == 2


def test_budget_spreads_reading_over_scans() -> None:
    rig = PlatformRunsRig(budget_bytes=1, page_size=2)
    rig.records.runs.save(run_record())
    rig.records.events.append(*(run_event(i, "node.started") for i in range(1, 6)))
    counts = [rig.scan().new_events for _ in range(6)]
    assert sum(counts) == 5
    assert counts[0] == 1


def test_finished_run_cache_and_invalidate() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record(status="completed"))
    rig.records.events.append(run_event(1, "node.started"))
    rig.scan()
    rig.records.events.append(run_event(2, "node.started"))  # 끝난 Run에 늦게 온 이벤트
    assert rig.scan().new_events == 0  # 마지막 seq 캐시
    rig.item.source.invalidate("r1")  # runs.event 구독이 부른다
    assert rig.scan().new_events == 1


def test_session_from_announcing_event_children_and_node_run_fallback() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.runs.save_node_run(
        NodeRun(run_id="r1", node_id="b", status="succeeded", backend_session_id="sb")
    )
    rig.records.events.append(
        run_event(1, "run.started", {"status": "running"}, path=()),
        run_event(2, "agent.session_started", {"session_id": "sa", "backend": "fake-agent"}),
        run_event(3, "agent.subagent_started", {"subagent_id": "t1", "name": "c"}, ("a", "c")),
        run_event(4, "node.started", {"status": "running"}, ("b",)),
    )
    rig.scan()
    by_seq = {e.seq: e for e in _events(rig)}
    assert by_seq[1].session == ""  # Run 수준 이벤트에는 세션이 없다
    assert by_seq[2].session == "sa"
    assert by_seq[3].session == "sa"  # 하위 노드(서브에이전트)는 부모 세션
    assert by_seq[4].session == "sb"  # 알린 이벤트가 없으면 NodeRun.backend_session_id
    assert by_seq[2].correlation == {"session": "sa"}
    assert by_seq[3].thread == "a/c"
    assert (by_seq[3].from_, by_seq[3].to, by_seq[3].via) == (["a"], ["c"], "delegate")


def test_session_survives_incremental_reads() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record(status="running"))
    rig.records.events.append(
        run_event(1, "agent.session_started", {"session_id": "sa", "backend": "fake-agent"})
    )
    rig.scan()
    rig.records.events.append(run_event(2, "agent.message", {"role": "assistant", "text": "hi"}))
    rig.scan()
    assert [e.session for e in _events(rig)] == ["sa", "sa"]


def test_unknown_type_is_other_and_skip_rule_drops() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "agent.text_delta", {"text": "x"}),
        run_event(2, "brand.new_event", {"x": 1}),
    )
    rig.scan()
    [only] = _events(rig)
    assert (only.category, only.title) == ("other", "brand.new_event")


def test_event_map_setting_overrides_defaults() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "brand.new_event", {"who": "kim"}),
        run_event(2, "agent.text_delta", {"text": "x"}),
    )
    report = rig.scan(
        {
            "event_map": {
                "brand.*": {"category": "custom", "title": "by {/payload/who}"},
                "agent.text_delta": {"category": "llm"},
            }
        }
    )
    assert report.sources[0].error_code is None
    assert [(e.category, e.title) for e in _events(rig)] == [
        ("custom", "by kim"),
        ("llm", "agent.text_delta"),
    ]


def test_invalid_event_map_setting_is_source_error() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    report = rig.scan({"event_map": {"x": {"category": 1}}})
    assert report.sources[0].error_code == "logs.invalid_config"


def test_max_runs_setting_limits_recent_runs() -> None:
    rig = PlatformRunsRig()
    for i in range(3):
        rig.records.runs.save(run_record(f"r{i}", created_at=float(i)))
        rig.records.events.append(run_event(1, "node.started", run_id=f"r{i}"))
    rig.scan({"max_runs": 2})
    assert sorted({e.run_id for e in _events(rig)}) == ["r1", "r2"]


def test_tool_events_use_tool_identity_and_status_map() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "agent.tool_call", {"tool_use_id": "t1", "name": "Bash"}),
        run_event(2, "agent.tool_result", {"tool_use_id": "t1", "is_error": True}),
    )
    rig.scan()
    call, result = _events(rig)
    assert (call.category, call.stage) == ("tool_call", "start")
    assert (call.tool, call.call_id) == ("Bash", "t1")
    assert (result.stage, result.status) == ("complete", "error")
    assert "tool" in call.tags
    assert call.correlation == {"call_id": "t1"}


def test_usage_is_opt_in_data() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "agent.usage", {"usage": {"input_tokens": 7, "output_tokens": 3}})
    )
    rig.scan()
    ctx = query_context(None)
    assert rig.index.token_samples(LogFilter(), ctx) == []
    opt_in = PlatformRunsRig()
    opt_in.records.runs.save(run_record())
    opt_in.records.events.append(
        run_event(1, "agent.usage", {"usage": {"input_tokens": 7, "output_tokens": 3}}),
        run_event(2, "agent.usage", {"usage": {"input_tokens": 9, "output_tokens": 5}}),
    )
    pointers = {"input_tokens": "/payload/usage/input_tokens"}
    pointers["output_tokens"] = "/payload/usage/output_tokens"
    opt_in.scan({"event_map": {"agent.usage": {"category": "usage", "usage": pointers}}})
    [sample] = opt_in.index.token_samples(LogFilter(), ctx)  # 누적값: 같은 응답 키로 한 번만
    assert (sample.input_tokens, sample.output_tokens) == (9, 5)
