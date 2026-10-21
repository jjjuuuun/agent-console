"""외톨이 서로게이트(`\\ud800`)가 든 실제 jsonl 행·서브에이전트 메타도 정상 이벤트가 된다.

pydantic은 외톨이 서로게이트 문자열을 거부하므로, 분류기는 모델(LogLane·LogDocumentRef·
TokenSample)을 만들기 전에 행·맥락을 `scrub_surrogates`로 정리한다(U+FFFD).
"""

from __future__ import annotations

from pathlib import Path

from agent_console_contracts.logs import LogSettings
from agent_console_logs import TAG_DIAGNOSTIC, LogFilter, LogIngestor, LogRegistries, query_context
from agent_console_logs.testing import MemoryLogIndex

SESSION = "33333333-3333-4333-8333-333333333333"
BAD = "\\ud800"  # JSON 이스케이프 그대로(파일에는 6글자로 들어간다)
FFFD = "�"


def _write(root: Path) -> None:
    project = root / "projects" / "-work-x"
    subagents = project / SESSION / "subagents"
    subagents.mkdir(parents=True)
    head = f'"sessionId": "{SESSION}", "cwd": "/work/x{BAD}", "timestamp": "2026-10-01T00:00:0'
    tool = (
        '{"type": "tool_use", "id": "toolu_w", "name": "Write", '
        f'"input": {{"file_path": "/work/x/SPEC{BAD}.md", "content": "a"}}}}'
    )
    task = (
        '{"type": "tool_use", "id": "toolu_t", "name": "Task", '
        f'"input": {{"subagent_type": "qa{BAD}", "description": "검사{BAD}"}}}}'
    )
    main = [
        f'{{{head}0Z", "type": "user", "uuid": "u1", "parentUuid": null, '
        f'"message": {{"role": "user", "content": "안녕{BAD}"}}}}',
        f'{{{head}1Z", "type": "assistant", "uuid": "a1", "parentUuid": "u1", '
        f'"message": {{"id": "m1{BAD}", "model": "model{BAD}", "content": [{tool}, {task}], '
        '"usage": {"input_tokens": 1, "output_tokens": 2}}}',
    ]
    (project / f"{SESSION}.jsonl").write_text("\n".join(main) + "\n", encoding="utf-8")
    sub = [
        f'{{{head}2Z", "type": "user", "uuid": "s1", "parentUuid": null, "agentId": "x1", '
        f'"message": {{"role": "user", "content": "돌려{BAD}"}}}}',
    ]
    (subagents / "agent-x1.jsonl").write_text("\n".join(sub) + "\n", encoding="utf-8")
    meta = f'{{"agentType": "qa{BAD}", "description": "검사{BAD}", "toolUseId": "toolu_t"}}'
    (subagents / "agent-x1.meta.json").write_text(meta, encoding="utf-8")


def test_lone_surrogates_become_normal_events(tmp_path: Path) -> None:
    _write(tmp_path)
    registries = LogRegistries()
    registries.load()
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, registries, environ={"CLAUDE_CONFIG_DIR": str(tmp_path)})
    settings = LogSettings.model_validate(
        {"sources": [{"id": "claude-code-jsonl", "enabled": True}]}
    )
    ingestor.scan(settings, source_ids={"claude-code-jsonl"})
    ctx = query_context(settings)
    events = index.query_events(LogFilter(limit=200), ctx).items
    assert events
    assert not [e for e in events if TAG_DIAGNOSTIC in e.tags or e.source == "diagnostic"]
    by_title = {e.title: e for e in events}
    assert by_title["안녕" + FFFD].summary == "안녕" + FFFD
    write = next(e for e in events if e.tool == "Write")
    assert [d.path for d in write.documents] == [f"/work/x/SPEC{FFFD}.md"]
    received = by_title["위임 작업 수신"]
    assert received.thread == "agent-x1"
    assert received.role == "qa" + FFFD
    assert received.correlation == {"tool_use_id": "toolu_t"}
    timeline = index.timeline(SESSION, ctx)
    assert timeline is not None
    lanes = {lane.id: lane for lane in timeline.lanes}
    assert lanes["agent-x1"].label == "qa" + FFFD
    [session] = index.list_sessions(LogFilter(), ctx)
    assert session.tokens is not None
    assert session.tokens.output == 2
    assert session.models == ["model" + FFFD]
