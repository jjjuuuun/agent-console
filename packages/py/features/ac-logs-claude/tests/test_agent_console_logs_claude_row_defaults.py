"""기본 행 규칙·요약(데이터)의 4R.6·4R.12 QA 후속 보강.

세션 메타 행(`custom-title`·`ai-title`·`permission-mode`·`mode` 등)과 hook·MCP·file-history 요약.
행 모양은 공개 커뮤니티 형식 정리를 본뜬 합성 행이다(실제 기록 아님).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from agent_console_contracts.logs import LogSettings
from agent_console_logs import (
    TAG_SESSION_TITLE,
    ClassifyContext,
    LogFilter,
    LogIngestor,
    LogRegistries,
    RawRecord,
    SessionTitleRule,
    SourceRef,
    effective_config,
    query_context,
)
from agent_console_logs.testing import MemoryLogIndex
from agent_console_logs_claude import ClaudeCodeClassifier, classifier_config_schema, summary_text

MAIN = {"kind": "session", "session": "S", "thread": "S", "project": "p"}


def _classify(row: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> list[Any]:
    cfg = effective_config(classifier_config_schema(), config)
    ctx = ClassifyContext(source_id="claude-code-jsonl", ref=SourceRef(ref="p/s.jsonl"), config=cfg)
    record = RawRecord(origin="p/s.jsonl", offset=0, data=dict(row), meta=dict(MAIN))
    return ClaudeCodeClassifier().classify(record, ctx)


def _one(row: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> Any:
    [event] = _classify({"sessionId": "S", **row}, config)
    return event


# ---------------------------------------------------------------- 요약 틀


def test_summary_template_fills_slots_and_skips_when_any_is_missing() -> None:
    detail = {"name": "h", "out": "ok", "code": 0, "files": {"/a.py": {}, "/b.py": {}}, "empty": {}}
    assert summary_text(detail, ["{/name} · {/out}"]) == "h · ok"
    assert summary_text(detail, ["{/name} · {/missing}", "{/name} · 코드 {/code}"]) == "h · 코드 0"
    assert summary_text(detail, ["{/files|keys}"]) == "/a.py, /b.py"
    assert summary_text(detail, ["{/empty|keys}", "없음"]) == "없음"  # 자리 표시 없는 틀 = 글자
    assert summary_text(detail, ["{/files}"]) is None  # 객체는 평문이 아니다(|keys로만)
    assert summary_text(detail, ["/name"]) == "h"  # 포인터는 그대로
    assert summary_text(detail, [""]) is None  # 빈 문자열 = detail 전체 포인터(객체라 평문 아님)


# ---------------------------------------------------------------- 세션 메타 행


def test_title_rows_are_session_title_candidates() -> None:
    ai = _one({"type": "ai-title", "aiTitle": "로그 화면 정리"})
    # 제목은 값 그대로(세션 목록 제목이 되므로), 무엇인지는 요약이 말한다.
    # 5R.19: 자동 제목은 반복되므로 숨김 범주 meta(타임라인 소음), 순위 태그 session_title.generated
    assert (ai.category, ai.title, ai.summary) == (
        "meta",
        "로그 화면 정리",
        "세션 제목(자동 생성)",
    )
    assert TAG_SESSION_TITLE in ai.tags
    assert "session_title.generated" in ai.tags
    custom = _one({"type": "custom-title", "customTitle": "내 이름"})
    assert (custom.category, custom.title, custom.summary) == (
        "other",
        "내 이름",
        "세션 이름(/rename)",
    )
    assert TAG_SESSION_TITLE in custom.tags
    assert "session_title.renamed" in custom.tags
    agent = _one({"type": "agent-name", "agentName": "리뷰어"})
    assert (agent.title, agent.summary, agent.tags) == ("에이전트 이름 · 리뷰어", "리뷰어", ())


@pytest.mark.parametrize(
    ("row", "title", "summary"),
    [
        ({"type": "permission-mode", "permissionMode": "plan"}, "권한 모드 · plan", "plan"),
        ({"type": "mode", "mode": "normal"}, "모드 · normal", "normal"),
    ],
)
def test_mode_rows_are_control_events(row: dict[str, Any], title: str, summary: str) -> None:
    event = _one(row)
    assert (event.category, event.title, event.summary) == ("control", title, summary)


def test_queue_last_prompt_and_file_history_rows() -> None:
    queue = _one({"type": "queue-operation", "operation": "enqueue", "content": "다음 일"})
    assert (queue.category, queue.title, queue.summary) == (
        "meta",
        "입력 대기열 · enqueue",
        "enqueue · 다음 일",
    )
    dequeue = _one({"type": "queue-operation", "operation": "dequeue"})
    assert dequeue.summary == "dequeue"
    last = _one({"type": "last-prompt", "lastPrompt": "고쳐 줘", "leafUuid": "u9"})
    assert (last.title, last.summary) == ("마지막 입력", "고쳐 줘")
    snapshot = _one(
        {
            "type": "file-history-snapshot",
            "messageId": "u1",
            "snapshot": {"trackedFileBackups": {"src/a.py": {"version": 1}, "b.md": {}}},
        }
    )
    assert (snapshot.category, snapshot.title) == ("meta", "파일 기록 · file-history-snapshot")
    assert snapshot.summary == "src/a.py, b.md"
    empty = _one({"type": "file-history-snapshot", "snapshot": {"trackedFileBackups": {}}})
    assert empty.summary == "추적 파일 없음"
    delta = _one({"type": "file-history-delta", "trackingPath": "/w/c.ts", "messageId": "u2"})
    assert (delta.title, delta.summary) == ("파일 기록 · file-history-delta", "/w/c.ts")


def test_unknown_rows_stay_other_with_raw() -> None:
    event = _one({"type": "brand-new-row", "x": 1})
    assert (event.category, event.title, event.summary) == ("other", "brand-new-row", None)
    assert event.raw["type"] == "brand-new-row"


@pytest.mark.parametrize(
    ("kind", "title"),
    [
        ("cost-state", "비용 상태"),
        ("api-request", "API 요청 기록 · api-request"),
        ("api-request-blob", "API 요청 기록 · api-request-blob"),
        ("atis-latch", "atis-latch"),
    ],
)
def test_noise_rows_go_to_hidden_meta_category(kind: str, title: str) -> None:
    """5R.19: 타임라인 소음 행은 기본 분류 체계의 숨김 범주 meta로 간다(데이터)."""
    event = _one({"type": kind, "x": 1})
    assert (event.category, event.title) == ("meta", title)
    assert "meta" in query_context(None).hidden_categories


# ---------------------------------------------------------------- hook·MCP 요약


def test_hook_summaries_are_name_plus_result() -> None:
    def attachment(**extra: Any) -> dict[str, Any]:
        return {"type": "attachment", "attachment": {"hookName": "PreToolUse:Bash", **extra}}

    ok = _one(attachment(type="hook_success", content="", stdout="통과", stderr="", exitCode=0))
    assert (ok.summary, ok.status) == ("PreToolUse:Bash · 통과", "completed")
    err = _one(attachment(type="hook_non_blocking_error", stderr="실패함", exitCode=1))
    assert (err.summary, err.category) == ("PreToolUse:Bash · 실패함", "error")
    silent = _one(attachment(type="hook_success", stdout="", exitCode=0))
    assert silent.summary == "PreToolUse:Bash · 종료 코드 0"
    bare = _one(attachment(type="hook_cancelled"))
    assert bare.summary == "PreToolUse:Bash · hook_cancelled"
    progress = _one(
        {
            "type": "progress",
            "data": {"type": "hook_progress", "hookName": "PreToolUse:Read", "command": "echo x"},
        }
    )
    assert progress.summary == "PreToolUse:Read · echo x"
    stop = _one(
        {
            "type": "system",
            "subtype": "stop_hook_summary",
            "hookCount": 1,
            "hookInfos": [{"command": "echo done"}],
            "stopReason": "",
            "preventedContinuation": False,
        }
    )
    assert (stop.summary, stop.status) == ("echo done", "completed")


def test_mcp_summaries_are_server_tool_plus_text() -> None:
    progress = _one(
        {
            "type": "progress",
            "data": {
                "type": "mcp_progress",
                "status": "completed",
                "serverName": "tracker",
                "toolName": "create_issue",
            },
        }
    )
    assert progress.summary == "tracker/create_issue · completed"

    def call(data: dict[str, Any]) -> Any:
        content = [{"type": "tool_use", "id": "t", "name": "mcp__tracker__find", "input": data}]
        return _one({"type": "assistant", "message": {"id": "m", "content": content}})

    assert call({"query": "로그"}).summary == "tracker/find · 로그"
    assert call({"limit": 3}).summary == "tracker/find"  # 아는 글 필드가 없으면 서버/도구만


# ---------------------------------------------------------------- 세션 제목 우선순위


def _rows() -> list[dict[str, Any]]:
    base = {"sessionId": "S1", "cwd": "/w"}
    return [
        {
            **base,
            "type": "user",
            "timestamp": "2026-10-01T00:00:00Z",
            "message": {"content": "첫 입력"},
        },
        {**base, "type": "ai-title", "aiTitle": "자동 제목", "timestamp": "2026-10-01T00:00:01Z"},
        {
            **base,
            "type": "custom-title",
            "customTitle": "바꾼 이름",
            "timestamp": "2026-10-01T00:00:02Z",
        },
    ]


def _session_title(
    tmp: Any,
    rows: list[dict[str, Any]],
    classifier: dict[str, Any],
    rules: tuple[SessionTitleRule, ...] | None = None,
) -> str:
    import json

    path = tmp / "projects" / "-w" / "S1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    registries = LogRegistries()
    registries.load()
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, registries, environ={"CLAUDE_CONFIG_DIR": str(tmp)})
    source: dict[str, Any] = {"id": "claude-code-jsonl", "enabled": True}
    if classifier:
        source["config"] = {"classifier": {"config": classifier}}
    settings = LogSettings.model_validate({"sources": [source]})
    ingestor.scan(settings)
    ctx = query_context(settings, session_title_rules=rules)
    [summary] = index.list_sessions(LogFilter(), ctx)
    return summary.title


def _later(row: dict[str, Any], second: int, **fields: Any) -> dict[str, Any]:
    return {**row, "timestamp": f"2026-10-01T00:00:{second:02d}Z", **fields}


def test_session_title_rank_is_renamed_then_generated_then_first_input(tmp_path: Any) -> None:
    """5R.19: 기본 순위 데이터 = 마지막 custom-title > 마지막 ai-title > 첫 입력."""
    first, ai, custom = _rows()
    assert _session_title(tmp_path / "a", [first, ai, custom], {}) == "바꾼 이름"
    renamed_twice = [first, custom, _later(custom, 5, customTitle="다시 바꾼 이름"), ai]
    assert _session_title(tmp_path / "b", renamed_twice, {}) == "다시 바꾼 이름"
    two_ai = [first, ai, _later(ai, 6, aiTitle="새 자동 제목")]
    assert _session_title(tmp_path / "c", two_ai, {}) == "새 자동 제목"
    second_input = _later(first, 7, message={"content": "두 번째 입력"})
    assert _session_title(tmp_path / "d", [first, second_input], {}) == "첫 입력"
    commands_only = [{**first, "message": {"content": "<command-name>/clear</command-name>"}}]
    assert _session_title(tmp_path / "e", commands_only, {}) == ""


def test_session_title_rules_are_data(tmp_path: Any) -> None:
    """규칙을 바꾸면(4R 동작: 태그 session_title의 첫 후보) 코드 수정 없이 결과가 바뀐다."""
    old = (SessionTitleRule("session_title", "first"),)
    assert _session_title(tmp_path / "a", _rows(), {}, old) == "첫 입력"
    off = {"session_title_from_input": False}
    assert _session_title(tmp_path / "b", _rows(), off, old) == "자동 제목"
    assert _session_title(tmp_path / "c", _rows(), {}, ()) == ""  # 규칙이 없으면 제목 없음


# ---------------------------------------------------------------- 2차: 첨부·도구 결과 요약


def _attachment(kind: str, **fields: Any) -> Any:
    return _one({"type": "attachment", "attachment": {"type": kind, **fields}})


@pytest.mark.parametrize(
    ("kind", "fields", "summary"),
    [
        ("total_tokens_reminder", {"text": "토큰 1000 사용"}, "토큰 1000 사용"),
        ("silent_turn_reminder", {"text": "조용히"}, "조용히"),
        ("silent_turn_reminder", {}, "silent_turn_reminder"),
        ("edited_text_file", {"filename": "/w/a.py", "snippet": "x"}, "edited_text_file · /w/a.py"),
        ("compact_file_reference", {"filename": "b.md"}, "compact_file_reference · b.md"),
        (
            "deferred_tools_record",
            {"entries": [{"name": "A"}, {"name": "B"}], "toolInputCopies": {}},
            "지연 도구 2개 · 입력 사본 0개",
        ),
        ("deferred_tools_record", {"entries": ["A"]}, "지연 도구 1개"),
        ("date", {"date": "2026-10-18"}, "날짜 2026-10-18"),
        ("language", {"language": "ko"}, "언어 ko"),
        ("command_permissions", {"allowedTools": ["Bash", "Read"]}, "허용 도구 2개"),
        ("auto_mode", {"enabled": True}, "auto_mode"),
        ("plan_mode", {"planFilePath": "/p.md"}, "plan_mode"),
        ("prompt_snapshot", {"prompt": "긴 입력"}, "prompt_snapshot"),
    ],
)
def test_attachment_summaries_are_plain(kind: str, fields: dict[str, Any], summary: str) -> None:
    event = _attachment(kind, **fields)
    assert (event.category, event.title, event.summary) == (
        "context",
        f"첨부 맥락 · {kind}",
        summary,
    )
    assert event.detail == {"type": kind, **fields}  # 원문은 detail에 그대로


def test_credential_like_attachment_summary_shows_kind_only() -> None:
    event = _attachment("credential_org", org="acme-secret-org", token="sk-FAKE")
    assert event.summary == "credential_org (값은 요약에 넣지 않음)"
    assert "acme" not in event.summary
    assert "sk-" not in event.summary
    # 모르는 첨부도 본문 대신 종류만.
    unknown = _attachment("new_kind", text="본문")
    assert unknown.summary == "new_kind"


def test_atis_latch_summary() -> None:
    assert _one({"type": "atis-latch", "atis": "on"}).summary == "atis on"
    assert _one({"type": "atis-latch", "atis": {"x": 1}}).summary == "atis-latch"


def test_tool_result_and_call_fallback_summaries() -> None:
    def result(content: Any) -> Any:
        block = {"type": "tool_result", "tool_use_id": "t", "content": content}
        return _one({"type": "user", "message": {"content": [block]}})

    images = [{"type": "image", "source": {}}, {"type": "image", "source": {}}]
    assert result(images).summary == "image 블록 2개"
    assert result("").summary == "결과 없음"
    assert result(None).summary == "결과 없음"
    assert result([]).summary == "결과 없음"

    def call(name: str, data: dict[str, Any]) -> Any:
        content = [{"type": "tool_use", "id": "c", "name": name, "input": data}]
        return _one({"type": "assistant", "message": {"id": "m", "content": content}})

    assert call("CronDelete", {"id": "job-1"}).summary == "CronDelete · job-1"
    assert call("TodoWrite", {"todos": []}).summary == "TodoWrite"


# ---------------------------------------------------------------- 5.5R.7 C6·C7


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/work/demo/CLAUDE.md", "rules"),
        ("/work/demo/CLAUDE.local.md", "rules"),
        ("/work/demo/.claude/rules/api.md", "rules"),
        ("C:\\work\\demo\\.claude\\rules\\db.md", "rules"),
        ("/work/demo/AGENTS.md", "agents_md"),
        ("/work/demo/docs/rules/x.md", "document"),
    ],
)
def test_document_kinds_rules_by_name_and_path_glob(path: str, kind: str) -> None:
    """C7: rules 종류는 데이터(파일 이름·경로 글롭)다."""
    row = {
        "type": "assistant",
        "message": {
            "id": "m",
            "content": [
                {"type": "tool_use", "id": "t", "name": "Read", "input": {"file_path": path}}
            ],
        },
    }
    [call] = _classify(row)
    assert [d.kind for d in call.documents] == [kind]


def test_document_kinds_glob_is_user_data() -> None:
    row = {
        "type": "assistant",
        "message": {
            "id": "m",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t",
                    "name": "Read",
                    "input": {"file_path": "/p/x.rules.md"},
                }
            ],
        },
    }
    [call] = _classify(row, {"document_kinds": {"*.rules.md": "house"}})
    assert [d.kind for d in call.documents] == ["house"]


def test_api_request_meta_row_and_request_ref_link() -> None:
    """C6: api-request 행은 요청 설정(모델·한도)만 detail로, 응답 행은 requestRef로 같은 근거."""
    request = {
        "type": "api-request",
        "id": "req-1",
        "sessionId": "S",
        "params": {"model": "claude-x", "max_tokens": 32000, "betas": ["b"]},
    }
    event = _one(request)
    assert (event.category, event.title, event.model) == ("meta", "API 요청 · claude-x", "claude-x")
    assert event.correlation["request_id"] == "req-1"
    assert event.detail == request["params"]
    assert event.summary == "claude-x · 최대 32000 토큰"
    reply = {
        "type": "assistant",
        "requestRef": "req-1",
        "message": {
            "id": "m",
            "content": [
                {"type": "text", "text": "답"},
                {"type": "tool_use", "id": "t", "name": "Bash", "input": {}},
            ],
        },
    }
    events = _classify(reply)
    assert [e.correlation.get("request_id") for e in events] == ["req-1", "req-1"]
    # 끄면 근거를 더하지 않는다(데이터)
    events = _classify(reply, {"row_correlation": {}})
    assert [e.correlation.get("request_id") for e in events] == [None, None]
