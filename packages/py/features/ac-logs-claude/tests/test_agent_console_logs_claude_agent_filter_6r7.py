"""6R.7(L-18): 하위 에이전트를 ``agent`` 필터로 고르면 그 에이전트의 이벤트·세션이 나온다.

5.2R.38 QA 관찰("하위 에이전트 세션을 고르면 빈 결과")을 서버가 쓰는 SQLite 색인으로 다시 본다.
새 형식(``subagents/agent-*.jsonl`` + 메타)과 옛 형식(메인 파일 안 ``isSidechain`` 행) 모두
``actor``가 하위 에이전트 thread라 ``agent`` 필터에 걸린다. 값은 thread id(레인 id)이며 레인
표시 이름(메타 ``agentType``)은 필터 값이 아니다.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_console_contracts.logs import LogSettings
from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index

DATA = Path(__file__).parent / "data" / "claude_config"
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


def test_subagent_file_agent_filter_finds_events_and_session(tmp_path: Path) -> None:
    index = _index(tmp_path, DATA)
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
