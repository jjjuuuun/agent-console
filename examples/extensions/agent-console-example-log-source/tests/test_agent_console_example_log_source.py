"""예제 로그 출처·분류기 `example.text_log`: entry point 로딩(+ 제거·enabled 필터), 출처 목록,
증분 수집, 진단 이벤트, 설정 데이터로 범주 바꾸기, 원본 읽기 전용.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). entry point는 `EntryPoint` 객체를 직접
만들어 로더에 넘긴다(설치했을 때 로더가 찾는 것과 같은 값).
"""

from __future__ import annotations

import tomllib
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.logs import LogSettings
from agent_console_example_log_source import (
    FORMAT_ID,
    TextLogClassifier,
    TextLogSource,
    parse_text_line,
)
from agent_console_logs import (
    LOG_CLASSIFIERS_GROUP,
    LOG_SOURCES_GROUP,
    ClassifyContext,
    LogFilter,
    LogIngestor,
    LogRegistries,
    RawRecord,
    SourceRef,
    query_context,
)
from agent_console_logs.testing import MemoryLogIndex, no_writes_under, tree_digest

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
SOURCE_VALUE = "agent_console_example_log_source:TextLogSource"
CLASSIFIER_VALUE = "agent_console_example_log_source:TextLogClassifier"

LOG = (
    "2026-10-17T09:00:00Z INFO [worker] 작업 시작\n"
    "이 줄은 형식이 틀렸다\n"
    "2026-10-17T09:00:02Z error 연결 실패\n"
)


def entry_points() -> list[EntryPoint]:
    return [
        EntryPoint(name=FORMAT_ID, value=SOURCE_VALUE, group=LOG_SOURCES_GROUP),
        EntryPoint(name=FORMAT_ID, value=CLASSIFIER_VALUE, group=LOG_CLASSIFIERS_GROUP),
    ]


def loaded(eps: list[EntryPoint] | None = None, **kw: Any) -> LogRegistries:
    registries = LogRegistries()
    reports = registries.load(entry_points=entry_points() if eps is None else eps, **kw)
    assert all(r.ok for group in reports.values() for r in group)
    return registries


def settings(root: Path, **source: Any) -> LogSettings:
    item = {"id": FORMAT_ID, "enabled": True, "config": {"roots": [str(root)]}}
    item["config"].update(source)  # type: ignore[attr-defined]
    return LogSettings.model_validate({"sources": [item]})


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    root = tmp_path / "logs"
    (root / "nested").mkdir(parents=True)
    (root / "nested" / "app.log").write_text(LOG, encoding="utf-8")
    (root / "ignored.jsonl").write_text("{}\n", encoding="utf-8")  # 포함 패턴 밖
    return root


# ------------------------------------------------------------------ 등록


def test_entry_points_declared() -> None:
    eps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    assert eps[LOG_SOURCES_GROUP] == {FORMAT_ID: SOURCE_VALUE}
    assert eps[LOG_CLASSIFIERS_GROUP] == {FORMAT_ID: CLASSIFIER_VALUE}


def test_installed_appears_in_source_list_and_removed_disappears() -> None:
    ingestor = LogIngestor(MemoryLogIndex(), loaded())
    [info] = ingestor.sources()
    desc = info.descriptor
    assert (desc.id, desc.format, info.enabled) == (FORMAT_ID, FORMAT_ID, False)
    assert [d.id for d in loaded().classifier_descriptors()] == [FORMAT_ID]

    removed = LogIngestor(MemoryLogIndex(), loaded([]))  # 제거 = entry point 없음
    assert removed.sources() == []


def test_enabled_filter_skips_plugin() -> None:
    registries = LogRegistries()
    reports = registries.load(
        entry_points=entry_points(), enabled_sources={"other"}, enabled_classifiers={"other"}
    )
    assert {r.status for group in reports.values() for r in group} == {"skipped"}
    assert registries.source_descriptors() == []


def test_module_path_registration() -> None:
    registries = LogRegistries()
    registries.load(
        entry_points=[],
        source_modules=[f"{FORMAT_ID}={SOURCE_VALUE}"],
        classifier_modules=[f"{FORMAT_ID}={CLASSIFIER_VALUE}"],
    )
    assert [d.id for d in registries.source_descriptors()] == [FORMAT_ID]
    assert [d.id for d in registries.classifier_descriptors()] == [FORMAT_ID]


# ------------------------------------------------------------------ 수집


def test_scan_is_incremental_read_only_and_keeps_bad_lines(logs: Path) -> None:
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, loaded())
    before = tree_digest(logs)
    with no_writes_under(logs):
        first = ingestor.scan(settings(logs))
        again = ingestor.scan(settings(logs))
    assert tree_digest(logs) == before
    assert (first.new_events, again.new_events) == (3, 0)

    events = index.query_events(LogFilter(), query_context(settings(logs))).items
    rows = [(e.source, e.category, e.title, e.status, e.thread, e.session) for e in events]
    assert rows[0] == (FORMAT_ID, "system", "작업 시작", "info", "worker", "nested/app.log")
    assert rows[2] == (FORMAT_ID, "error", "연결 실패", "error", "", "nested/app.log")
    assert rows[1][0:2] == ("diagnostic", "error")  # 형식이 틀린 줄은 진단 이벤트
    assert events[0].time == pytest.approx(1792227600.0)


def test_appended_lines_are_read_next_time(logs: Path) -> None:
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, loaded())
    ingestor.scan(settings(logs))
    with (logs / "nested" / "app.log").open("a", encoding="utf-8") as f:
        f.write("2026-10-17T09:00:05Z WARN [worker] 느림\n2026-10-17T09:00:06Z INFO 쓰는 중")
    assert ingestor.scan(settings(logs)).new_events == 1  # 끝나지 않은 줄은 보류
    assert ingestor.scan(settings(logs), final=True).new_events == 1


def test_level_categories_are_settings_data(logs: Path) -> None:
    index = MemoryLogIndex()
    custom = settings(
        logs,
        classifier={"config": {"level_categories": {"INFO": "llm"}, "default_category": "other"}},
    )
    LogIngestor(index, loaded()).scan(custom)
    by_title = {e.title: e.category for e in index.query_events(LogFilter(), query_context()).items}
    assert by_title["작업 시작"] == "llm"
    assert by_title["연결 실패"] == "other"  # 기본 대응표를 통째로 바꿨다


def test_invalid_classifier_config_fails_only_that_source(logs: Path) -> None:
    bad = settings(logs, classifier={"config": {"unknown": 1}})
    report = LogIngestor(MemoryLogIndex(), loaded()).scan(bad)
    assert report.new_events == 0
    [result] = report.sources
    assert result.error_code is not None


# ------------------------------------------------------------------ 순수 부분


def test_parse_text_line() -> None:
    assert parse_text_line("2026-10-17T09:00:00Z warn [a b] 메시지 본문") == {
        "time": "2026-10-17T09:00:00Z",
        "level": "WARN",
        "thread": "a b",
        "message": "메시지 본문",
    }
    assert parse_text_line("2026-10-17T09:00:00+09:00 INFO 그냥 메시지")["thread"] == ""
    for bad in ("", "INFO 시각없음", "어제 INFO 메시지", "2026-10-17T09:00:00Z INFO [t]"):
        with pytest.raises(ValueError):  # noqa: PT011 - 메시지는 사람용
            parse_text_line(bad)


def test_source_rejects_undecodable_bytes() -> None:
    with pytest.raises(UnicodeDecodeError):
        TextLogSource().parse_line(b"\xff\xfe")


def test_classifier_uses_injected_context_only() -> None:
    record = RawRecord(
        origin="x.log",
        offset=0,
        data={"time": "2026-10-17T09:00:00Z", "level": "FATAL", "thread": "t", "message": "죽음"},
    )
    ctx = ClassifyContext(
        source_id="renamed",
        ref=SourceRef(ref="x.log"),
        config={"level_categories": {"FATAL": "error"}, "actor": "app"},
    )
    [draft] = TextLogClassifier().classify(record, ctx)
    got = (draft.category, draft.actor, draft.thread, draft.session)
    assert got == ("error", "app", "t", "x.log")
    with pytest.raises(ValueError):  # noqa: PT011
        TextLogClassifier().classify(RawRecord(origin="x", offset=0, data=[1]), ctx)
