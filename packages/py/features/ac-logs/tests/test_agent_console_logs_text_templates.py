"""LogEventDraft.text_templates(I.7f): 값이 섞인 제목의 원문 틀 + 값.

코어가 제목과 같이 가리고, 가린·자른 제목과 맞는 틀만 ``LogEvent.text_templates``에 남긴다. SQLite
색인 목록·상세에도 그대로 실린다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import TextTemplate, render_text_parts
from agent_console_logs import LogEventDraft, LogFilter, build_record, query_context
from agent_console_logs._index import IndexBatch
from agent_console_logs.sqlite import open_log_index

RUN = TextTemplate(template="실행 {status}", params={"status": "completed"})


def _event(draft: LogEventDraft, redact: Any = None) -> Any:
    return build_record(
        draft, source_id="s", origin="r", offset=0, index=0, observed_at=1.0, redact=redact
    ).event


def test_matching_title_template_is_kept() -> None:
    event = _event(
        LogEventDraft(category="system", title="실행 completed", text_templates={"/title": [RUN]})
    )
    assert event.text_templates == {"/title": [RUN]}
    assert render_text_parts(event.text_templates["/title"]) == event.title


def test_mismatched_or_unknown_pointers_are_dropped() -> None:
    other = TextTemplate(template="다른 {x}", params={"x": "1"})
    event = _event(
        LogEventDraft(
            category="system",
            title="실행 completed",
            text_templates={"/title": [other], "/detail": [RUN], "/summary": []},
        )
    )
    assert event.text_templates == {}
    assert _event(LogEventDraft(category="system")).text_templates == {}


def test_redaction_applies_to_params_too() -> None:
    def redact(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("sk-777", "[가림]")
        if isinstance(value, list):
            return [redact(v) for v in value]
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        return value

    secret = TextTemplate(template="키 {key}", params={"key": "sk-777"})
    event = _event(
        LogEventDraft(category="x", title="키 sk-777", text_templates={"/title": [secret]}), redact
    )
    assert event.title == "키 [가림]"
    assert event.text_templates["/title"][0].params == {"key": "[가림]"}


def test_sqlite_index_keeps_templates(tmp_path: Path) -> None:
    index = open_log_index(tmp_path / "i.sqlite3")
    record = build_record(
        LogEventDraft(category="system", title="실행 completed", text_templates={"/title": [RUN]}),
        source_id="s",
        origin="r",
        offset=0,
        index=0,
        observed_at=1.0,
    )
    plain = build_record(
        LogEventDraft(category="system", title="고정"),
        source_id="s",
        origin="r",
        offset=1,
        index=0,
        observed_at=1.0,
    )
    index.write(IndexBatch(records=[record, plain]))
    items = {e.title: e for e in index.query_events(LogFilter(), query_context(None)).items}
    assert items["실행 completed"].text_templates == {"/title": [RUN]}
    assert items["고정"].text_templates == {}
    detail = index.get_event(items["실행 completed"].uid, query_context(None))
    assert detail is not None
    assert detail.event.text_templates == {"/title": [RUN]}
    index.close()
