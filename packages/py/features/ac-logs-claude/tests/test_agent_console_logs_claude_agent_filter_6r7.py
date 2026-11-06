"""6R.7(L-18): 하위 에이전트를 ``agent`` 필터로 고르면 그 에이전트의 이벤트·세션이 나온다.

5.2R.38 QA 관찰("하위 에이전트 세션을 고르면 빈 결과")을 서버가 쓰는 SQLite 색인으로 다시 본다.
새 형식(``subagents/agent-*.jsonl`` + 메타)과 옛 형식(메인 파일 안 ``isSidechain`` 행) 모두
``actor``가 하위 에이전트 thread라 ``agent`` 필터에 걸린다. 값은 thread id(레인 id)이며 레인
표시 이름(메타 ``agentType``)은 필터 값이 아니다.

로그는 테스트 안에서 ``tmp_path``에 만든다(공개본은 ``tests/data`` 픽스처를 싣지 않는다).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_contracts.logs import LogSettings
from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index

SESSION = "11111111-1111-4111-8111-111111111111"
SUBAGENT = "agent-a1b2"
SETTINGS = LogSettings.model_validate({"sources": [{"id": "claude-code-jsonl", "enabled": True}]})


def _index(tmp_path: Path, config_dir: Path) -> SqliteLogIndex:
    index = open_log_index(tmp_path / "index.sqlite3")
    registries = LogRegistries()
    registries.load()
    ingestor = LogIngestor(
        index, registries, environ={"CLAUDE_CONFIG_DIR": str(config_dir)}, clock=lambda: 1.0
    )
    ingestor.scan(SETTINGS, source_ids={"claude-code-jsonl"})
    return index


def _write_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _subagent_config(root: Path) -> Path:
    """새 형식: 메인 세션 파일 + ``<세션>/subagents/agent-<id>.jsonl`` + 메타."""
    project = root / "projects" / "-work-demo"
    base = {"sessionId": SESSION, "cwd": "/work/demo", "version": "2.1.0"}
    agent_call = {
        "type": "tool_use",
        "id": "toolu_agent",
        "name": "Agent",
        "input": {"subagent_type": "reviewer", "prompt": "검토해 줘"},
    }
    agent_result = {"type": "tool_result", "tool_use_id": "toolu_agent", "content": "검토 완료"}
    main = [
        {
            **base,
            "isSidechain": False,
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "timestamp": "2026-10-01T00:00:00.000Z",
            "message": {"role": "user", "content": "문서를 정리해 줘"},
        },
        {
            **base,
            "isSidechain": False,
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "timestamp": "2026-10-01T00:00:01.000Z",
            "message": {
                "id": "msg_1",
                "role": "assistant",
                "model": "claude-test-model",
                "content": [agent_call],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        },
        {
            **base,
            "isSidechain": False,
            "type": "user",
            "uuid": "u2",
            "parentUuid": "a1",
            "timestamp": "2026-10-01T00:00:10.000Z",
            "message": {"role": "user", "content": [agent_result]},
            "toolUseResult": {"status": "completed", "agentId": "a1b2"},
        },
    ]
    sub = {**base, "isSidechain": True, "agentId": "a1b2"}
    subagent = [
        {**sub, "type": "user", "uuid": "s-u1", "parentUuid": None,
         "timestamp": "2026-10-01T00:00:02.000Z",
         "message": {"role": "user", "content": "검토해 줘"}},
        {**sub, "type": "assistant", "uuid": "s-a1", "parentUuid": "s-u1",
         "timestamp": "2026-10-01T00:00:03.000Z",
         "message": {"id": "msg_s1", "role": "assistant", "model": "claude-test-small",
                     "content": [{"type": "text", "text": "문제 없습니다."}],
                     "usage": {"input_tokens": 1, "output_tokens": 1}}},
    ]  # fmt: skip
    _write_jsonl(project / f"{SESSION}.jsonl", main)
    sub_dir = project / SESSION / "subagents"
    _write_jsonl(sub_dir / f"{SUBAGENT}.jsonl", subagent)
    (sub_dir / f"{SUBAGENT}.meta.json").write_text(
        json.dumps({"agentType": "reviewer", "toolUseId": "toolu_agent"}), encoding="utf-8"
    )
    return root


def test_subagent_file_agent_filter_finds_events_and_session(tmp_path: Path) -> None:
    index = _index(tmp_path, _subagent_config(tmp_path / "claude"))
    try:
        ctx = query_context(SETTINGS)
        events = list(index.query_events(LogFilter(agent=(SUBAGENT,)), ctx).items)
        assert events
        assert all(SUBAGENT in (e.actor, *e.from_, *e.to) for e in events)  # actor·from·to 중 하나
        sessions = index.list_sessions(LogFilter(agent=(SUBAGENT,)), ctx)
        assert [s.session for s in sessions] == [SESSION]
        lanes = {lane.id: lane for lane in index.lanes()}
        assert lanes[SUBAGENT].parent_id == SESSION  # 필터 값 = 레인 id
    finally:
        index.close()


def test_inline_sidechain_agent_filter(tmp_path: Path) -> None:
    root = tmp_path / "claude"
    project = root / "projects" / "-work-old"
    project.mkdir(parents=True)
    rows = [
        {"type": "user", "sessionId": "S-old", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"role": "user", "content": "메인 입력"}},
        {"type": "user", "sessionId": "S-old", "uuid": "u2", "isSidechain": True, "agentId": "zz",
         "timestamp": "2026-01-01T00:00:01Z", "message": {"role": "user", "content": "옛 형식"}},
    ]  # fmt: skip
    (project / "S-old.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    index = _index(tmp_path, root)
    try:
        ctx = query_context(SETTINGS)
        events = list(index.query_events(LogFilter(agent=("agent-zz",)), ctx).items)
        assert [e.actor for e in events] == ["agent-zz"]
        assert [s.session for s in index.list_sessions(LogFilter(agent=("agent-zz",)), ctx)] == [
            "S-old"
        ]
    finally:
        index.close()
