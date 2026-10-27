"""4R.11 QA 추가: 재시작 뒤 커서 이어 읽기, max_runs 초과, 대응표 하드코딩 없음, 토큰 이중 집계."""

from __future__ import annotations

import re
from pathlib import Path

from ruamel.yaml import YAML

import agent_console_link_logs_runs as pkg
from agent_console_link_logs_runs import platform_runs
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context

PKG_DIR = Path(pkg.__file__).parent


def _load_map() -> dict[str, dict[str, object]]:
    data = YAML(typ="safe").load(PKG_DIR / "data" / "run_event_map.yaml")
    return dict(data["types"])


def test_restart_resumes_from_cursor_without_duplicates() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record(status="running"))
    rig.records.events.append(*(run_event(i, "node.started") for i in range(1, 4)))
    assert rig.scan().new_events == 3
    # 서버 재시작 흉내: 출처·수집기를 새로 만들고 같은 색인(영속 커서)을 쓴다
    item = platform_runs(rig.records.runs, rig.records.events)
    again = LogIngestor(rig.index, LogRegistries())
    again.add_runtime_source(item.source, classifier=item.classifier)
    assert again.scan().new_events == 0
    rig.records.events.append(run_event(4, "node.completed"))
    assert again.scan().new_events == 1
    page = rig.index.query_events(LogFilter(limit=50), query_context(None))
    assert len(page.items) == 4
    assert len({e.uid for e in page.items}) == 4


def test_runs_beyond_max_runs_keep_indexed_events_and_do_not_duplicate() -> None:
    rig = PlatformRunsRig()
    for i in range(3):
        rig.records.runs.save(run_record(f"r{i}", created_at=float(i)))
        rig.records.events.append(run_event(1, "node.started", run_id=f"r{i}"))
    rig.scan({"max_runs": 3})
    for i in (3, 4):
        rig.records.runs.save(run_record(f"r{i}", created_at=float(i)))
        rig.records.events.append(run_event(1, "node.started", run_id=f"r{i}"))
    report = rig.scan({"max_runs": 2})  # r0~r2는 범위 밖
    assert report.new_events == 2
    page = rig.index.query_events(LogFilter(limit=50), query_context(None))
    assert sorted(e.run_id for e in page.items) == ["r0", "r1", "r2", "r3", "r4"]


def test_event_type_names_and_categories_live_only_in_data() -> None:
    names = [k for k in _load_map() if not any(c in k for c in "*?")]
    assert "hook.finished" in names
    code = "\n".join(
        p.read_text(encoding="utf-8")
        for p in PKG_DIR.glob("*.py")
        if p.name not in {"testing.py", "__init__.py"}
    )
    for name in names:
        assert f'"{name}"' not in code, name
        assert f"'{name}'" not in code, name
    for cat in ("hook", "mcp", "handoff", "tool_call", "tool_result", "llm"):
        assert not re.search(rf"[\"']{cat}[\"']", code), cat


def test_event_map_override_changes_hook_category_and_mcp() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "hook.finished", {"event": "Stop", "name": "g", "exit_code": 0}),
        run_event(2, "mcp.call_started", {"server": "s", "tool": "t", "tool_use_id": "x"}),
    )
    rig.scan({"event_map": {"hook.finished": {"category": "guardrail"}, "mcp.call_started": {}}})
    page = rig.index.query_events(LogFilter(limit=10), query_context(None))
    assert [e.category for e in page.items] == ["guardrail", "other"]


def test_default_map_has_no_usage_pointers_so_tokens_are_not_double_counted() -> None:
    assert not [k for k, r in _load_map().items() if r.get("usage")]
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "agent.usage", {"usage": {"input_tokens": 100, "output_tokens": 50}}),
        run_event(2, "agent.session_started", {"session_id": "s1", "backend": "fake-agent"}),
        run_event(3, "agent.usage", {"usage": {"input_tokens": 100, "output_tokens": 50}}),
    )
    rig.scan()
    ctx = query_context(None)
    assert rig.index.token_samples(LogFilter(), ctx) == []
    assert rig.index.token_samples(LogFilter(session=("s1",)), ctx) == []
