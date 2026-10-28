"""5.7R.16(design §5.7R.9): 기본 대응표의 메모리 도구 호출 규칙 `memory.*`.

- payload(계약 `MemoryEventPayload` 모양)의 범위·키 → 문서 표지 `{kind: memory, path, action}`,
  상태 대응(`ok`→ok, `denied`→block, 나머지→error), 근거 `tool_use_id`·`memory_scope`.
- 동작 → 문서 action은 데이터(지우기 = `removed`, 파일 변경 어휘 `deleted`와 겹치지 않는다).
- 설정 `event_map`으로 범주 이름을 바꾸거나 규칙을 끄면(`{}`) 범주가 바뀌거나 `other`가 된다.
  다른 형식의 색인은 그대로다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts.logs import LogEvent
from agent_console_contracts.memory import KNOWN_MEMORY_EVENT_TYPES, MemoryEventPayload
from agent_console_link_logs_runs import load_default_event_map
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogFilter, query_context

RULE = "memory.*"


def _payload(op: str, status: str = "ok", **extra: Any) -> dict[str, Any]:
    payload = {
        "op": op,
        "status": status,
        "scope": {"kind": "shelf", "id": "g1"},
        "key": "결정/api",
        "tool": "my_memory_tool",
        "tool_use_id": f"tu-{op}",
        **extra,
    }
    return MemoryEventPayload.model_validate(payload).model_dump(mode="json")


def _scan(overrides: dict[str, Any] | None, *events: Any) -> list[LogEvent]:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(*events)
    rig.scan({"event_map": overrides} if overrides is not None else None)
    return rig.index.query_events(LogFilter(limit=200), query_context(None)).items


def test_default_map_has_memory_rule_for_every_known_type() -> None:
    table = load_default_event_map()
    assert RULE in table.rules
    for event_type in KNOWN_MEMORY_EVENT_TYPES:
        assert table.rule_for(event_type).get("category") == "memory"


@pytest.mark.parametrize(
    ("op", "action"),
    [("read", "read"), ("write", "written"), ("delete", "removed"), ("search", "searched")],
)
def test_memory_event_becomes_memory_document(op: str, action: str) -> None:
    [event] = _scan(None, run_event(1, f"memory.{op}", _payload(op)))
    assert event.category == "memory"
    assert event.title == f"메모리 {op} shelf:결정/api"
    assert event.status == "ok"
    assert [d.model_dump() for d in event.documents] == [
        {"kind": "memory", "path": "shelf/g1/결정/api", "action": action}
    ]
    assert event.correlation["tool_use_id"] == f"tu-{op}"
    assert event.correlation["memory_scope"] == "shelf"


@pytest.mark.parametrize(
    ("status", "mapped"),
    [("ok", "ok"), ("denied", "block"), ("not_found", "error"), ("scope_unavailable", "error")],
)
def test_status_mapping_is_data(status: str, mapped: str) -> None:
    [event] = _scan(None, run_event(1, "memory.write", _payload("write", status)))
    assert event.status == mapped


def test_rename_category_and_turn_off_rule_by_settings() -> None:
    other = run_event(2, "agent.message", {"text": "안녕", "role": "assistant"})
    renamed = dict(load_default_event_map().rules[RULE], category="notes")
    events = _scan({RULE: renamed}, run_event(1, "memory.read", _payload("read")), other)
    assert [e.category for e in events if e.title.startswith("메모리")] == ["notes"]

    off = _scan({RULE: {}}, run_event(1, "memory.read", _payload("read")), other)
    by_title = {e.title: e for e in off}
    assert by_title["memory.read"].category == "other"  # 대체 범주·제목 = 형식 이름
    assert by_title["memory.read"].documents == []
    assert by_title["안녕"].category == "llm"  # 다른 형식은 그대로


def test_unknown_scope_leaves_no_document() -> None:
    payload = _payload("write", "denied", scope=None)
    [event] = _scan(None, run_event(1, "memory.write", payload))
    assert (event.category, event.status) == ("memory", "block")
    assert event.documents == []
    assert "memory_scope" not in event.correlation or not event.correlation["memory_scope"]
