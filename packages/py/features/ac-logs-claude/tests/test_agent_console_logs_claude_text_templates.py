"""값이 섞인 이벤트 제목·요약의 원문 틀 + 값(`text_templates`)과 영어 문구 묶음 대조.

영어 화면에 파서가 만든 한글 제목이 남던 문제(실화면 판정 C2)의 회귀 시험이다. 제목·요약이 서버
원문(한국어)이면, 고정 문구는 묶음 키 그대로, 값이 섞인 문구는 틀(`text_templates`)이 묶음에 있어야
웹이 옮길 수 있다. 행 모양은 합성 행이다(실제 기록 아님).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

import agent_console_logs_claude
from agent_console_contracts import TextTemplate, render_text_parts
from agent_console_contracts.logs import LogSettings
from agent_console_logs import (
    ClassifyContext,
    LogFilter,
    LogIngestor,
    LogRegistries,
    RawRecord,
    SourceRef,
    effective_config,
    query_context,
)
from agent_console_logs.testing import MemoryLogIndex
from agent_console_logs_claude import (
    ClaudeCodeClassifier,
    classifier_config_schema,
    pointer_text_template,
    slot_name,
    summary_with_template,
)
from agent_console_logs_claude._templates import POINTER_SLOT

MAIN = {"kind": "session", "session": "S", "thread": "S", "project": "p"}
SUB = {"kind": "subagent", "session": "S", "thread": "agent-a1", "role": "reviewer", "parent": "S"}
_SOURCE = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")


def _classify(
    row: Mapping[str, Any], meta: Mapping[str, Any] = MAIN, config: Mapping[str, Any] | None = None
) -> list[Any]:
    cfg = effective_config(classifier_config_schema(), config)
    ctx = ClassifyContext(source_id="claude-code-jsonl", ref=SourceRef(ref="p/s.jsonl"), config=cfg)
    record = RawRecord(
        origin="p/s.jsonl", offset=0, data={"sessionId": "S", **row}, meta=dict(meta)
    )
    return ClaudeCodeClassifier().classify(record, ctx)


def _en() -> dict[str, str]:
    path = files(agent_console_logs_claude).joinpath("locales", "en.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    text = data["text"]
    assert isinstance(text, dict)
    return text


# ---------------------------------------------------------------- 틀 만들기


def test_slot_names_use_the_last_segment_and_mode() -> None:
    assert slot_name("/data/hookName") == "hookName"
    assert slot_name("/output", "count") == "output_count"
    assert slot_name("/output/0") == "v0"
    assert slot_name("/a~1b") == "a_b"
    assert slot_name("/") == "value"


def test_pointer_template_escapes_braces_and_checks_the_shown_value() -> None:
    built = pointer_text_template("{/a} 묶음 {x}", {("/a", None): "v"}, "v 묶음 {x}")
    assert built == TextTemplate(template="{a} 묶음 {{x}}", params={"a": "v"})
    assert pointer_text_template("{/a} 묶음", {("/a", None): "v"}, "다른 값") is None


def test_pointer_template_skips_value_only_fixed_and_colliding_templates() -> None:
    assert pointer_text_template("{/a}/{/b}", {}, "/") is None  # 값만으로 된 틀
    assert pointer_text_template("고정 문구", {}, "고정 문구") is None  # 자리 표시 없음
    colliding: dict[tuple[str, str | None], str] = {("/x/name", None): "1", ("/y/name", None): "2"}
    assert pointer_text_template("{/x/name} 와 {/y/name}", colliding, "1 와 2") is None


def test_summary_with_template_marks_only_templates_that_mix_in_values() -> None:
    detail = {"output": [{"type": "image"}], "text": "원문"}
    assert summary_with_template(detail, ["/text"]) == ("원문", None)  # 원문 데이터는 틀 없음
    assert summary_with_template({}, ["결과 없음"]) == ("결과 없음", None)  # 고정 문구
    found = summary_with_template(detail, ["{/output/0/type} 블록 {/output|count}개"])
    assert found == (
        "image 블록 1개",
        TextTemplate(
            template="{type} 블록 {output_count}개", params={"type": "image", "output_count": "1"}
        ),
    )


# ---------------------------------------------------------------- 분류기 출력


def test_row_rule_titles_and_summaries_carry_templates() -> None:
    [hook] = _classify(
        {"type": "system", "subtype": "stop_hook_summary", "hookCount": 2, "stopReason": "멈춤"}
    )
    assert hook.title == "hook 요약 · 2개"
    assert hook.text_templates["/title"] == [
        TextTemplate(template="hook 요약 · {hookCount}개", params={"hookCount": "2"})
    ]
    assert hook.summary == "멈춤"
    assert "/summary" not in hook.text_templates  # 요약은 기록의 값

    [run] = _classify(
        {
            "type": "progress",
            "data": {"type": "hook_progress", "hookName": "PreToolUse:Read", "command": "x"},
        }
    )
    assert run.title == "hook 실행 · PreToolUse:Read"
    assert render_text_parts(run.text_templates["/title"]) == run.title
    assert run.text_templates["/title"][0].template == "hook 실행 · {hookName}"

    [attachment] = _classify(
        {
            "type": "attachment",
            "attachment": {"type": "hook_non_blocking_error", "hookName": "h", "exitCode": 1},
        }
    )
    assert attachment.summary == "h · 종료 코드 1"
    assert attachment.text_templates["/summary"][0].template == "{hookName} · 종료 코드 {exitCode}"


def test_fixed_titles_have_no_templates_and_code_titles_do() -> None:
    [compact] = _classify({"type": "system", "subtype": "compact_boundary", "content": "c"})
    assert compact.title == "컨텍스트 압축"
    assert compact.text_templates == {}

    blocks = [{"type": "thinking", "thinking": "비밀"}, {"type": "odd"}]
    thinking, other = _classify({"type": "assistant", "message": {"id": "m", "content": blocks}})
    assert (thinking.title, thinking.summary) == ("내부 추론", "내부 추론 본문 생략")
    assert thinking.text_templates == {}
    assert other.title == "응답 블록 · odd"
    assert other.text_templates["/title"] == [
        TextTemplate(template="응답 블록 · {kind}", params={"kind": "odd"})
    ]

    call = {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "rev"}}
    [delegation] = _classify({"type": "assistant", "message": {"id": "m", "content": [call]}})
    assert delegation.title == "서브에이전트 위임 · rev"
    assert delegation.text_templates["/title"][0].template == "서브에이전트 위임 · {value}"


def test_ingested_events_keep_templates_that_match_the_stored_title(tmp_path: Path) -> None:
    rows = [
        {"type": "system", "subtype": "stop_hook_summary", "hookCount": 3, "sessionId": "S1"},
        {"type": "user", "message": {"content": "질문"}, "sessionId": "S1"},
    ]
    path = tmp_path / "projects" / "-w" / "S1.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    registries = LogRegistries()
    registries.load()
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, registries, environ={"CLAUDE_CONFIG_DIR": str(tmp_path)})
    settings = LogSettings.model_validate(
        {"sources": [{"id": "claude-code-jsonl", "enabled": True}]}
    )
    ingestor.scan(settings)
    page = index.query_events(LogFilter(), query_context(settings))
    by_title = {e.title: e for e in page.items}
    hook = by_title["hook 요약 · 3개"]
    assert render_text_parts(hook.text_templates["/title"]) == hook.title
    assert by_title["질문"].text_templates == {}  # 사용자 입력은 사용자 데이터


# ---------------------------------------------------------------- 영어 묶음


def _source_keys(template: str) -> Iterator[str]:
    """설정 틀 하나 → 화면 번역 키(값이 섞였으면 이름 자리 표시 틀, 아니면 그대로)."""
    if not _SOURCE.search(template):
        return
    values = {(m.group(1), m.group(2)): "x" for m in POINTER_SLOT.finditer(template)}
    shown = POINTER_SLOT.sub("x", template).strip()
    built = pointer_text_template(template, values, shown)
    yield built.template if built is not None else template


def _default_templates() -> Iterator[tuple[str, str]]:
    schema = classifier_config_schema()
    props = schema["properties"]
    for i, rule in enumerate(props["row_rules"]["default"]):
        yield f"row_rules[{i}].title", str(rule.get("title") or "")
        for item in rule.get("summary") or []:
            yield f"row_rules[{i}].summary", str(item)
    for kind, items in props["summaries"]["default"].items():
        for item in items:
            yield f"summaries.{kind}", str(item)
    yield "thinking_note", str(props["thinking_note"]["default"])


def test_every_default_title_and_summary_has_an_english_text() -> None:
    en = _en()
    missing = [
        (where, key)
        for where, template in _default_templates()
        for key in _source_keys(template)
        if not en.get(key)
    ]
    assert missing == []


_CODE_ROWS: list[tuple[dict[str, Any], Mapping[str, Any]]] = [
    (
        {"type": "assistant", "message": {"id": "m", "content": [{"type": "text", "text": "a"}]}},
        MAIN,
    ),
    (
        {
            "type": "assistant",
            "isApiErrorMessage": True,
            "message": {"id": "m", "content": [{"type": "text", "text": "e"}]},
        },
        MAIN,
    ),
    ({"type": "assistant", "message": {"id": "m", "content": []}}, MAIN),
    ({"type": "assistant", "message": {"id": "m", "content": [{"type": "odd"}]}}, MAIN),
    ({"type": "assistant", "message": {"id": "m", "content": [{"type": "thinking"}]}}, MAIN),
    (
        {"type": "assistant", "message": {"id": "m", "content": [{"type": "tool_use", "id": "t"}]}},
        MAIN,
    ),
    (
        {
            "type": "assistant",
            "message": {"id": "m", "content": [{"type": "tool_use", "id": "t", "name": "Agent"}]},
        },
        MAIN,
    ),
    ({"type": "user", "message": {"content": []}}, MAIN),
    ({"type": "user", "message": {"content": [{"type": "image"}]}}, MAIN),
    ({"type": "user", "parentUuid": None, "message": {"content": "일"}}, SUB),
    (
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t"}]}},
        MAIN,
    ),
    (
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "is_error": True}]},
        },
        MAIN,
    ),
    (
        {
            "type": "user",
            "toolUseResult": {"agentId": "a1"},
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t"}]},
        },
        MAIN,
    ),
    (
        {
            "type": "user",
            "toolUseResult": {"agentId": "a1"},
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "is_error": True}]},
        },
        MAIN,
    ),
    ({}, MAIN),
]


@pytest.mark.parametrize(("row", "meta"), _CODE_ROWS)
def test_code_built_titles_have_an_english_text(
    row: dict[str, Any], meta: Mapping[str, Any]
) -> None:
    en = _en()
    for event in _classify(row, meta):
        if not _SOURCE.search(event.title):
            continue
        parts = event.text_templates.get("/title")
        keys = [p.template for p in parts] if parts else [event.title]
        assert [k for k in keys if not en.get(k)] == [], event.title
