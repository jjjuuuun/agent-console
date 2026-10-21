"""LogEventDraft.summary: 분류기가 준 평문 요약을 쓰고(가리기·길이 제한 적용), 없으면 detail에서."""

from __future__ import annotations

from typing import Any

from agent_console_logs import LogEventDraft, build_record
from agent_console_logs._build import SUMMARY_CHARS


def _summary(draft: LogEventDraft, redact: Any = None) -> str:
    record = build_record(
        draft, source_id="s", origin="r", offset=0, index=0, observed_at=1.0, redact=redact
    )
    return record.event.summary


def test_draft_summary_wins_over_detail_and_detail_is_kept() -> None:
    draft = LogEventDraft(category="input", detail={"text": "안녕"}, summary="안녕")
    record = build_record(draft, source_id="s", origin="r", offset=0, index=0, observed_at=1.0)
    assert record.event.summary == "안녕"
    assert record.event.detail == {"text": "안녕"}


def test_without_draft_summary_detail_is_stringified() -> None:
    assert _summary(LogEventDraft(category="x", detail={"a": 1})) == '{"a": 1}'


def test_draft_summary_is_redacted_and_bounded() -> None:
    def redact(value: Any) -> Any:
        return value.replace("SECRET", "[가림]") if isinstance(value, str) else value

    assert _summary(LogEventDraft(category="x", summary="키 SECRET"), redact) == "키 [가림]"
    assert len(_summary(LogEventDraft(category="x", summary="가" * (SUMMARY_CHARS + 50)))) == (
        SUMMARY_CHARS
    )
