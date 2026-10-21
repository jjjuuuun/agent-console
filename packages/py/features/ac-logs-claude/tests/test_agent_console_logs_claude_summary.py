"""목록 요약(summary)은 사람이 읽는 평문이다. 위치는 설정 데이터(`summaries`·행 규칙 `summary`)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_logs import (
    ClassifyContext,
    RawRecord,
    SourceRef,
    effective_config,
)
from agent_console_logs_claude import (
    ClaudeCodeClassifier,
    classifier_config_schema,
    summary_text,
)

MAIN = {"kind": "session", "session": "S", "thread": "S", "project": "p"}


def _classify(row: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> list[Any]:
    cfg = effective_config(classifier_config_schema(), config)
    ctx = ClassifyContext(source_id="claude-code-jsonl", ref=SourceRef(ref="p/s.jsonl"), config=cfg)
    record = RawRecord(origin="p/s.jsonl", offset=0, data=dict(row), meta=dict(MAIN))
    return ClaudeCodeClassifier().classify(record, ctx)


def _user(content: Any, **extra: Any) -> dict[str, Any]:
    return {
        "type": "user",
        "sessionId": "S",
        "message": {"role": "user", "content": content},
        **extra,
    }


def test_summary_text_reads_strings_and_text_blocks() -> None:
    detail = {
        "output": [
            {"type": "text", "text": "가"},
            {"type": "image"},
            {"type": "text", "text": "나"},
        ]
    }
    assert summary_text(detail, ["/missing", "/output"]) == "가\n나"
    assert summary_text({"text": "  "}, ["/text"]) is None  # 빈 글은 건너뛴다
    assert summary_text({"n": 3}, ["/n"]) is None  # 숫자·객체는 평문이 아니다
    assert summary_text({"t": "x"}, None) is None


def test_input_and_tool_result_summaries_are_plain_text() -> None:
    [inp] = _classify(_user("문서를 정리해 줘"))
    assert inp.summary == "문서를 정리해 줘"
    assert inp.detail == {"text": "문서를 정리해 줘"}  # 원문은 detail에 그대로
    block = {"type": "tool_result", "tool_use_id": "t1", "content": "권한 없음", "is_error": True}
    [res] = _classify(_user([block]))
    assert res.summary == "권한 없음"
    assert res.status == "failed"  # 오류 여부는 요약이 아니라 상태로
    assert res.detail == {"output": "권한 없음", "is_error": True}


def test_tool_call_summary_uses_configured_input_fields() -> None:
    row = {
        "type": "assistant",
        "sessionId": "S",
        "message": {
            "id": "m",
            "content": [
                {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "ls"}}
            ],
        },
    }
    [call] = _classify(row)
    assert call.summary == "ls"
    [custom] = _classify(row, {"summaries": {"tool_call": ["/name"]}})
    assert custom.summary == "Bash"  # 위치는 설정 데이터
    [none] = _classify(row, {"summaries": {"tool_call": []}})
    assert none.summary is None  # 못 찾으면 코어 기본(detail 문자열)


def test_row_rule_summary_pointer() -> None:
    rule = {"name": "x", "match": {"/type": "note"}, "category": "context", "summary": ["/body"]}
    [ev] = _classify({"type": "note", "body": "메모"}, {"extra_row_rules": [rule]})
    assert ev.summary == "메모"
