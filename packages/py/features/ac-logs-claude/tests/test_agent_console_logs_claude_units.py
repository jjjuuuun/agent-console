"""분류기·출처 단위 테스트(행 단위 무상태, 설정 데이터, 메타 연결)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_console_logs import (
    TAG_SESSION_TITLE,
    TAG_TOOL,
    ClassifyContext,
    LogSourceContext,
    RawRecord,
    SourceRef,
    effective_config,
)
from agent_console_logs.testing import RecordingOpen
from agent_console_logs_claude import (
    ClaudeCodeClassifier,
    ClaudeCodeJsonlSource,
    McpPatternError,
    classifier_config_schema,
    compile_mcp_pattern,
    source_config_schema,
)


def _cctx(config: Mapping[str, Any] | None = None) -> ClassifyContext:
    cfg = effective_config(classifier_config_schema(), config)
    return ClassifyContext(
        source_id="claude-code-jsonl", ref=SourceRef(ref="p/s.jsonl"), config=cfg
    )


def _rec(row: Any, meta: Mapping[str, Any] | None = None) -> RawRecord:
    return RawRecord(origin="p/s.jsonl", offset=0, data=row, meta=dict(meta or {}))


MAIN = {"kind": "session", "session": "S", "thread": "S", "project": "p"}
SUB = {
    "kind": "subagent",
    "session": "S",
    "thread": "agent-x",
    "parent": "S",
    "role": "tester",
    "tool_use_id": "toolu_1",
}


def _assistant(content: list[Any], **extra: Any) -> dict[str, Any]:
    return {
        "type": "assistant",
        "sessionId": "S",
        "timestamp": "2026-10-01T00:00:00Z",
        "message": {
            "id": "msg_a",
            "model": "m",
            "content": content,
            "usage": {"input_tokens": 1, "output_tokens": 2},
        },
        **extra,
    }


def test_default_schemas_validate_and_have_defaults() -> None:
    cfg = effective_config(classifier_config_schema(), {})
    assert cfg["mcp_tool_pattern"]
    assert [t["name"] for t in cfg["delegation_tools"]] == ["Agent", "Task"]
    assert cfg["row_rules"]
    src = effective_config(source_config_schema(), {})
    assert src["default_root"] == "~/.claude/projects"
    assert src["config_dir_env"] == "CLAUDE_CONFIG_DIR"
    # 부분 설정은 나머지 기본값을 이어받는다
    partial = effective_config(classifier_config_schema(), {"categories": {"mcp_call": "tools"}})
    assert partial["categories"]["mcp_call"] == "tools"
    assert partial["categories"]["input"] == "input"


def test_schema_copies_are_independent() -> None:
    a = classifier_config_schema()
    a["properties"].clear()
    assert classifier_config_schema()["properties"]


def test_stateless_same_input_same_output() -> None:
    c = ClaudeCodeClassifier()
    row = _assistant([{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}])
    first = c.classify(_rec(row, MAIN), _cctx())
    c.classify(_rec(_assistant([{"type": "text", "text": "다른 행"}]), MAIN), _cctx())
    assert c.classify(_rec(row, MAIN), _cctx()) == first
    [event] = first
    assert TAG_TOOL in event.tags
    assert event.call_id == "t1"
    assert event.stage == "start"
    assert event.message_id == "msg_a"
    assert event.usage is not None
    assert event.usage.output_tokens == 2


def test_usage_only_on_first_event_of_row() -> None:
    c = ClaudeCodeClassifier()
    row = _assistant(
        [
            {"type": "text", "text": "a"},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
        ]
    )
    events = c.classify(_rec(row, MAIN), _cctx())
    assert [e.usage is not None for e in events] == [True, False]
    assert {e.message_id for e in events} == {"msg_a"}
    assert events[0].raw is not None
    assert events[1].raw is None


def test_non_object_row_raises() -> None:
    with pytest.raises(ValueError, match="JSON 객체"):
        ClaudeCodeClassifier().classify(_rec([1, 2]), _cctx())


def test_mcp_pattern_template() -> None:
    pat = compile_mcp_pattern("mcp__{server}__{tool}")
    m = pat.match("mcp__plugin_x__do__it")
    assert m is not None
    assert (m.group("server"), m.group("tool")) == ("plugin_x", "do__it")
    assert pat.match("xmcp__a__b") is None  # 이름 전체가 맞아야 한다
    assert pat.match("mcp__a.b__c") is not None  # 틀의 글자는 정규식이 아니다
    star = compile_mcp_pattern("*:{server}/{tool}")
    m2 = star.match("ext:srv/tool")
    assert m2 is not None
    assert m2.group("server") == "srv"
    for bad in ("mcp__{server}", "{server}{server}{tool}", "mcp__(.+)"):
        with pytest.raises(McpPatternError):
            compile_mcp_pattern(bad)
    row = _assistant([{"type": "tool_use", "id": "t", "name": "mcp__a__b", "input": {}}])
    with pytest.raises(ValueError, match="server"):  # → 수집기가 진단 이벤트로 남긴다
        ClaudeCodeClassifier().classify(_rec(row, MAIN), _cctx({"mcp_tool_pattern": "x{tool}"}))


def test_delegation_fallback_target_without_meta() -> None:
    row = _assistant(
        [{"type": "tool_use", "id": "toolu_9", "name": "Task", "input": {"subagent_type": "qa"}}]
    )
    [event] = ClaudeCodeClassifier().classify(_rec(row, MAIN), _cctx())
    assert event.category == "handoff"
    assert event.to == ("role:qa",)
    with_meta = {**MAIN, "subagents": {"toolu_9": "agent-q"}}
    [linked] = ClaudeCodeClassifier().classify(_rec(row, with_meta), _cctx())
    assert linked.to == ("agent-q",)


def test_delegation_tools_are_data() -> None:
    row = _assistant([{"type": "tool_use", "id": "t", "name": "Spawn", "input": {"who": "x"}}])
    cfg = {"delegation_tools": [{"name": "Spawn", "target_pointer": "/who", "via": "spawn"}]}
    [event] = ClaudeCodeClassifier().classify(_rec(row, MAIN), _cctx(cfg))
    assert (event.category, event.to, event.via) == ("handoff", ("x",), "spawn")
    no_agent: dict[str, Any] = {"delegation_tools": []}
    agent_row = _assistant([{"type": "tool_use", "id": "t", "name": "Agent", "input": {}}])
    [plain] = ClaudeCodeClassifier().classify(_rec(agent_row, MAIN), _cctx(no_agent))
    assert plain.category == "tool"


def test_subagent_first_input_and_agent_info() -> None:
    row = {"type": "user", "parentUuid": None, "message": {"content": "일 해 줘"}}
    [event] = ClaudeCodeClassifier().classify(_rec(row, SUB), _cctx())
    assert event.title == "위임 작업 수신"
    assert event.from_ == ("S",)
    assert event.to == ("agent-x",)
    assert event.correlation == {"tool_use_id": "toolu_1"}
    assert event.agent is not None
    assert (event.agent.id, event.agent.label, event.agent.parent_id) == ("agent-x", "tester", "S")
    assert TAG_SESSION_TITLE not in event.tags
    later = {"type": "user", "parentUuid": "u0", "message": {"content": "추가"}}
    [event2] = ClaudeCodeClassifier().classify(_rec(later, SUB), _cctx())
    assert event2.from_ == ()


def test_inline_sidechain_row_gets_subagent_thread() -> None:
    row = {
        "type": "user",
        "isSidechain": True,
        "agentId": "zz",
        "sessionId": "S",
        "message": {"content": "옛 형식"},
    }
    [event] = ClaudeCodeClassifier().classify(_rec(row, MAIN), _cctx())
    assert event.thread == "agent-zz"


def test_session_title_skip_prefixes() -> None:
    c = ClaudeCodeClassifier()
    cmd = {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}}
    [event] = c.classify(_rec(cmd, MAIN), _cctx())
    assert TAG_SESSION_TITLE not in event.tags
    [event2] = c.classify(_rec(cmd, MAIN), _cctx({"session_title_skip_prefixes": []}))
    assert TAG_SESSION_TITLE in event2.tags


def test_user_image_block_body_not_copied_to_detail() -> None:
    row = {
        "type": "user",
        "message": {
            "content": [
                {"type": "text", "text": "그림"},
                {"type": "image", "source": {"data": "QUJD"}},
            ]
        },
    }
    [event] = ClaudeCodeClassifier().classify(_rec(row, MAIN), _cctx())
    assert event.detail == {"text": "그림", "blocks": [{"type": "image"}]}


def test_api_error_message() -> None:
    row = _assistant([{"type": "text", "text": "API Error: 529"}], isApiErrorMessage=True)
    [event] = ClaudeCodeClassifier().classify(_rec(row, MAIN), _cctx())
    assert (event.category, event.status) == ("error", "failed")


def test_categories_are_data() -> None:
    row = {"type": "user", "message": {"content": "안녕"}}
    [event] = ClaudeCodeClassifier().classify(
        _rec(row, MAIN), _cctx({"categories": {"input": "prompt"}})
    )
    assert event.category == "prompt"


def test_hook_attachment_error_category_from_value_map() -> None:
    row = {
        "type": "attachment",
        "attachment": {"type": "hook_non_blocking_error", "hookName": "PostToolUse:Bash"},
    }
    [event] = ClaudeCodeClassifier().classify(_rec(row, MAIN), _cctx())
    assert (event.category, event.status) == ("error", "failed")
    ok = {"type": "attachment", "attachment": {"type": "hook_success", "hookName": "Stop"}}
    [event2] = ClaudeCodeClassifier().classify(_rec(ok, MAIN), _cctx())
    assert (event2.category, event2.status, event2.title) == ("hook", "completed", "hook · Stop")


def test_rule_match_list_and_bool() -> None:
    rule = {"match": {"/type": ["a", "b*"], "/flag": "true"}, "category": "c", "title": "{/n}"}
    c = ClaudeCodeClassifier()
    cfg = {"extra_row_rules": [rule]}
    [hit] = c.classify(_rec({"type": "bee", "flag": True, "n": 3}, MAIN), _cctx(cfg))
    assert (hit.category, hit.title) == ("c", "3")
    [miss] = c.classify(_rec({"type": "bee", "flag": False}, MAIN), _cctx(cfg))
    assert miss.category == "other"


# ---------------------------------------------------------------- 출처


def _sctx(root: Path, opener: Any = None, **config: Any) -> LogSourceContext:
    cfg = effective_config(source_config_schema(), {"roots": [str(root)], **config})
    kwargs: dict[str, Any] = {"source_id": "claude-code-jsonl", "config": cfg}
    if opener is not None:
        kwargs["open_read"] = opener
    return LogSourceContext(**kwargs)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_discover_layout_and_meta(tmp_path: Path) -> None:
    _write(tmp_path / "p" / "S.jsonl", "{}\n")
    sub = tmp_path / "p" / "S" / "subagents"
    _write(sub / "agent-1.jsonl", "{}\n")
    _write(sub / "agent-1.meta.json", json.dumps({"agentType": "r", "toolUseId": "tu"}))
    _write(sub / "workflows" / "wf_1" / "agent-2.jsonl", "{}\n")
    _write(sub / "workflows" / "wf_1" / "journal.jsonl", "{}\n")
    _write(tmp_path / "p" / "S" / "tool-results" / "x.jsonl", "{}\n")
    source = ClaudeCodeJsonlSource()
    refs = {r.ref: r for r in source.discover(_sctx(tmp_path))}
    assert sorted(refs) == [
        "p/S.jsonl",
        "p/S/subagents/agent-1.jsonl",
        "p/S/subagents/workflows/wf_1/agent-2.jsonl",
    ]
    assert refs["p/S.jsonl"].meta == {
        "kind": "session",
        "project": "p",
        "session": "S",
        "thread": "S",
        "subagents": {"tu": "agent-1"},
    }
    assert refs["p/S/subagents/agent-1.jsonl"].meta == {
        "kind": "subagent",
        "project": "p",
        "session": "S",
        "thread": "agent-1",
        "parent": "S",
        "role": "r",
        "tool_use_id": "tu",
    }
    assert refs["p/S/subagents/workflows/wf_1/agent-2.jsonl"].meta["parent"] == "S"


def test_meta_cache_and_size_limit(tmp_path: Path) -> None:
    sub = tmp_path / "p" / "S" / "subagents"
    _write(sub / "agent-1.jsonl", "{}\n")
    _write(sub / "agent-1.meta.json", json.dumps({"agentType": "r"}))
    _write(sub / "agent-2.jsonl", "{}\n")
    _write(sub / "agent-2.meta.json", json.dumps({"agentType": "x" * 200}))
    _write(sub / "agent-3.jsonl", "{}\n")
    _write(sub / "agent-3.meta.json", "{깨진")
    source = ClaudeCodeJsonlSource()
    recorder = RecordingOpen()
    ctx = _sctx(tmp_path, recorder, max_meta_bytes=100)
    refs = {r.ref.rsplit("/", 1)[-1]: r for r in source.discover(ctx)}
    assert refs["agent-1.jsonl"].meta["role"] == "r"
    assert "role" not in refs["agent-2.jsonl"].meta  # 한도 초과는 읽지 않음
    assert "role" not in refs["agent-3.jsonl"].meta  # 깨진 메타는 무시
    opened = len(recorder.opened)
    list(source.discover(ctx))
    assert len(recorder.opened) == opened  # 바뀌지 않은 메타는 다시 읽지 않는다


def test_meta_fields_are_data(tmp_path: Path) -> None:
    sub = tmp_path / "p" / "S" / "subagents"
    _write(sub / "agent-1.jsonl", "{}\n")
    _write(sub / "agent-1.meta.json", json.dumps({"kind": {"name": "new-role"}}))
    ctx = _sctx(tmp_path, meta_fields={"role": "/kind/name"})
    [ref] = ClaudeCodeJsonlSource().discover(ctx)
    assert ref.meta["role"] == "new-role"
