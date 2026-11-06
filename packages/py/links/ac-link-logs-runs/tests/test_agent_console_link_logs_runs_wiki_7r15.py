"""7R.15(design §7R.4 로그·구조도 행): 기본 대응표의 위키 도구 호출 규칙 `wiki.*`.

- payload(계약 `WikiEventPayload`)의 위키·페이지 경로 → 문서 표지
  `{kind: wiki, path: <위키>/<경로>}`. 옮기기는 문서 둘(옛 경로 `moved_from`, 새 경로 `moved_to`),
  페이지가 없는 호출(검색·목록)은 표지 없음.
- 상태 대응(`ok`→ok, `denied`·`rule_rejected`→block, 나머지→error), 근거 `tool_use_id`·`wiki`.
- 동작 → 문서 action은 데이터(파일 변경 어휘 created·modified·deleted를 쓰지 않는다).
- 설정 `event_map`으로 범주 이름을 바꾸거나 규칙을 끄면(`{}`) 범주가 바뀌거나 `other`가 되고
  이벤트는 남는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts.logs import LogEvent
from agent_console_contracts.wiki import KNOWN_WIKI_EVENT_TYPES, WikiEventPayload
from agent_console_link_logs_runs import load_default_event_map
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogFilter, query_context

RULE = "wiki.*"
WORKSPACE_ACTIONS = {"created", "modified", "deleted"}  # 기본 구조도 Workspace 칸 조건의 어휘


def _payload(op: str, status: str = "ok", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "op": op,
        "status": status,
        "wiki": "team-notes",
        "path": "결정/형식",
        "tool": "my_wiki_tool",
        "tool_use_id": f"tu-{op}",
        "bytes": 12,
        **extra,
    }
    # 연동은 빈 값을 뺀 JSON을 싣는다(`event_payload` = exclude_none)
    return WikiEventPayload.model_validate(payload).model_dump(mode="json", exclude_none=True)


def _scan(overrides: dict[str, Any] | None, *events: Any) -> list[LogEvent]:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(*events)
    rig.scan({"event_map": overrides} if overrides is not None else None)
    return rig.index.query_events(LogFilter(limit=200), query_context(None)).items


def _docs(event: LogEvent) -> list[dict[str, Any]]:
    return [d.model_dump() for d in event.documents]


def test_default_map_has_wiki_rule_for_every_known_type() -> None:
    table = load_default_event_map()
    assert RULE in table.rules
    for event_type in KNOWN_WIKI_EVENT_TYPES:
        assert table.rule_for(event_type).get("category") == "wiki"


@pytest.mark.parametrize(
    ("op", "action"),
    [
        ("read", "read"),
        ("links", "read_links"),
        ("write", "written"),
        ("delete", "removed"),
    ],
)
def test_page_event_becomes_wiki_document(op: str, action: str) -> None:
    [event] = _scan(None, run_event(1, f"wiki.{op}", _payload(op)))
    assert event.category == "wiki"
    assert event.title == f"위키 {op} team-notes/결정/형식"
    assert event.status == "ok"
    assert _docs(event) == [{"kind": "wiki", "path": "team-notes/결정/형식", "action": action}]
    assert event.correlation["tool_use_id"] == f"tu-{op}"
    assert event.correlation["wiki"] == "team-notes"
    assert action not in WORKSPACE_ACTIONS


def test_move_gives_old_and_new_documents() -> None:
    [event] = _scan(None, run_event(1, "wiki.move", _payload("move", to="결정/형식-v2")))
    assert _docs(event) == [
        {"kind": "wiki", "path": "team-notes/결정/형식", "action": "moved_from"},
        {"kind": "wiki", "path": "team-notes/결정/형식-v2", "action": "moved_to"},
    ]


@pytest.mark.parametrize("op", ["search", "list"])
def test_search_and_list_have_no_document(op: str) -> None:
    payload = _payload(op, path=None, results=3, query_chars=4)
    [event] = _scan(None, run_event(1, f"wiki.{op}", payload))
    assert (event.category, event.title, event.status) == ("wiki", f"위키 {op} team-notes", "ok")
    assert event.documents == []
    assert event.correlation["wiki"] == "team-notes"


@pytest.mark.parametrize(
    ("status", "mapped"),
    [
        ("ok", "ok"),
        ("denied", "block"),
        ("rule_rejected", "block"),
        ("not_found", "error"),
        ("rate_limited", "error"),
        ("wiki_unavailable", "error"),
        ("secret_rejected", "error"),
    ],
)
def test_status_mapping_is_data(status: str, mapped: str) -> None:
    [event] = _scan(None, run_event(1, "wiki.write", _payload("write", status)))
    assert event.status == mapped


def test_denied_without_wiki_has_no_document() -> None:
    # 위키를 고를 수 없는 거부(접근 설정에 기본 위키 없음): payload에 wiki·path가 없다
    payload = _payload("write", "denied", wiki=None, path=None, code="wiki.denied")
    [event] = _scan(None, run_event(1, "wiki.write", payload))
    assert (event.category, event.status, event.title) == ("wiki", "block", "위키 write")
    assert event.documents == []
    assert not event.correlation.get("wiki")


def test_rename_category_and_turn_off_rule_by_settings() -> None:
    other = run_event(2, "agent.message", {"text": "안녕", "role": "assistant"})
    renamed = dict(load_default_event_map().rules[RULE], category="knowledge")
    events = _scan({RULE: renamed}, run_event(1, "wiki.read", _payload("read")), other)
    assert [e.category for e in events if e.title.startswith("위키")] == ["knowledge"]

    off = _scan({RULE: {}}, run_event(1, "wiki.read", _payload("read")), other)
    by_title = {e.title: e for e in off}
    assert by_title["wiki.read"].category == "other"  # 대체 범주·제목 = 형식 이름, 이벤트는 남음
    assert by_title["wiki.read"].documents == []
    assert by_title["안녕"].category == "llm"  # 다른 형식은 그대로
