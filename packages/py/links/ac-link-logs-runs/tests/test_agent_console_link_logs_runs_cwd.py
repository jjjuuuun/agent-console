"""5.2R.34: Run 유효 작업 폴더(``run.started`` payload ``cwd``) → 이 Run 이벤트의 ``cwd``(대응표
``cwd_from`` 규칙, 데이터). 로그 프로젝트 묶기·``project`` 필터가 플랫폼 실행에도 걸린다."""

from __future__ import annotations

from agent_console_contracts.logs import LogEvent, LogSettings
from agent_console_link_logs_runs import SOURCE_ID, load_default_event_map
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogFilter, query_context


def _events(
    rig: PlatformRunsRig, settings: LogSettings | None = None, **flt: object
) -> list[LogEvent]:
    page = rig.index.query_events(LogFilter(limit=200).with_(**flt), query_context(settings))
    return page.items


def test_default_map_reads_run_cwd_from_run_started() -> None:
    rule = load_default_event_map().rule_for("run.started")
    assert rule.get("cwd_from") == "/payload/cwd"


def test_run_cwd_applies_to_later_events_and_survives_incremental_reads() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record(status="running"))
    rig.records.events.append(
        run_event(1, "run.created", {"status": "queued"}, path=()),
        run_event(2, "run.started", {"status": "running", "cwd": "/w/app"}, path=()),
        run_event(3, "node.started", {"status": "running"}),
    )
    rig.scan()
    rig.records.events.append(run_event(4, "node.completed", {"status": "succeeded"}))
    rig.scan()  # 커서 state에서 cwd를 이어 받는다
    by_seq = {e.title: e.cwd for e in _events(rig)}
    assert by_seq["실행 queued"] == ""  # 알리기 전 이벤트
    assert by_seq["실행 running"] == "/w/app"
    assert by_seq["a running"] == "/w/app"
    assert by_seq["a succeeded"] == "/w/app"
    cursor = rig.index.get_cursor(SOURCE_ID, "r1")
    assert cursor is not None
    assert cursor.state.get("cwd") == "/w/app"
    # 프로젝트 묶기 규칙(경로 글롭)이 플랫폼 실행 이벤트에도 걸린다
    settings = LogSettings.model_validate(
        {"projects": {"groups": [{"id": "app", "match": ["/w/app/**", "/w/app"]}]}}
    )
    assert len(_events(rig, settings, project=["app"])) == 3
    assert len(_events(rig, cwd=["/w/app"])) == 3


def test_without_cwd_nothing_changes() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "run.started", {"status": "running"}, path=()),
        run_event(2, "node.started", {"status": "running"}),
    )
    rig.scan()
    assert {e.cwd for e in _events(rig)} == {""}
    cursor = rig.index.get_cursor(SOURCE_ID, "r1")
    assert cursor is not None
    assert "cwd" not in cursor.state
