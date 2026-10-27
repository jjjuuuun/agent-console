"""5.7R.7(M-2, design §5.7R.9): 대응표 목록 값 `{each, ...항목 틀}`.

`documents`·`tags`·`correlation`에 쓴다.

- 항목 틀의 `{./키}`·`{.}`·`pointer: ./키`는 목록 원소 기준, 빈 항목은 빼고 같은 항목은 한 번.
- 목록이 비었거나 목록이 아니거나 원소가 객체가 아니어도 예외 없이 항목 0개.
- 기본 데이터: `agent.context_prepared`의 리소스 → 문서(규칙 리소스가 먼저, 종류 rule → rules).
- 기존 값 형식(글자 그대로의 태그·틀 문자열 근거)은 같은 뜻(회귀).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts.logs import LogEvent
from agent_console_link_logs_runs import load_event_map
from agent_console_link_logs_runs.event_map import (
    render,
    resolve,
    resolve_documents,
    resolve_strings,
)
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import ConfigError, LogFilter, query_context

EVENT: dict[str, Any] = {
    "type": "x.go",
    "payload": {
        "resources": [
            {"id": "s1", "kind": "skill"},
            {"id": "r1", "kind": "rule"},
            {"id": "r2", "kind": "rule"},
            {"id": "r1", "kind": "rule"},
        ],
        "words": ["a", "b", "a", ""],
        "op": "write",
    },
}
NAMES = {"node": "n1"}


def _events(rig: PlatformRunsRig) -> list[LogEvent]:
    return rig.index.query_events(LogFilter(limit=200), query_context(None)).items


def _scan(overrides: dict[str, Any] | None, *events: object) -> list[LogEvent]:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(*events)  # type: ignore[arg-type]
    rig.scan({"event_map": overrides} if overrides else None)
    return _events(rig)


# --- 순수 함수 ---


def test_item_pointers_resolve_against_element_and_event() -> None:
    item = {"id": "r1", "kind": "rule"}
    assert render("{./kind}:{./id}@{/type}/{node}", EVENT, NAMES, item) == "rule:r1@x.go/n1"
    assert render("{.}", EVENT, NAMES, "a") == "a"
    assert render("{./kind}", EVENT, NAMES) == ""  # 항목 틀 밖에서는 원소가 없다
    spec = {"pointer": "./kind", "map": {"rule": "rules"}, "default": "{./kind}"}
    assert resolve(spec, EVENT, NAMES, item) == "rules"
    assert resolve(spec, EVENT, NAMES, {"kind": "skill"}) == "skill"


def test_strings_each_drops_empty_and_duplicates_in_order() -> None:
    spec = {"each": "/payload/resources", "value": "{./id}"}
    assert resolve_strings(spec, EVENT, NAMES) == ["s1", "r1", "r2"]
    assert resolve_strings({"each": "/payload/words", "value": "{.}"}, EVENT, NAMES) == ["a", "b"]
    mapped = {
        "each": "/payload/resources",
        "value": {"pointer": "./kind", "map": {"rule": "rules"}, "default": ""},
    }
    assert resolve_strings(mapped, EVENT, NAMES) == ["rules"]  # default "" → 그 항목을 뺀다


@pytest.mark.parametrize(
    "document",
    [
        {"payload": {"resources": []}},  # 빈 목록
        {"payload": {}},  # 없음
        {"payload": {"resources": {"id": "r1"}}},  # 목록이 아님
        {"payload": {"resources": [1, None, "x", ["y"]]}},  # 원소가 객체가 아님
    ],
)
def test_each_with_empty_or_malformed_list_yields_nothing(document: dict[str, Any]) -> None:
    assert resolve_strings({"each": "/payload/resources", "value": "{./id}"}, document, {}) == []
    docs = {"each": "/payload/resources", "path": "{./id}", "kind": "{./kind}"}
    assert resolve_documents(docs, document, {}) == []


def test_tags_literal_strings_keep_old_meaning_and_mix_with_each() -> None:
    spec = ["tool", "{node}", {"each": "/payload/words", "value": "w:{.}"}]
    # 빈 원소도 틀 결과("w:")가 비지 않으면 남는다(빼는 기준은 채운 결과)
    assert resolve_strings(spec, EVENT, NAMES, literal=True) == [
        "tool",
        "{node}",
        "w:a",
        "w:b",
        "w:",
    ]


def test_documents_single_template_with_conditional_value() -> None:
    spec = [
        {
            "kind": "memory",
            "path": "{/type}/{node}",
            "action": {"pointer": "/payload/op", "map": {"write": "written"}},
        }
    ]
    assert resolve_documents(spec, EVENT, NAMES) == [
        {"path": "x.go/n1", "kind": "memory", "action": "written"}
    ]


def test_documents_each_blocks_concatenate_filter_and_dedupe() -> None:
    spec = [
        {
            "each": "/payload/resources",
            "kind": "rules",
            "path": {"pointer": "./kind", "map": {"rule": "{./id}"}, "default": ""},
            "action": "read",
        },
        {
            "each": "/payload/resources",
            "kind": "{./kind}",
            "path": {"pointer": "./kind", "map": {"rule": ""}, "default": "{./id}"},
        },
    ]
    assert resolve_documents(spec, EVENT, NAMES) == [
        {"path": "r1", "kind": "rules", "action": "read"},
        {"path": "r2", "kind": "rules", "action": "read"},
        {"path": "s1", "kind": "skill"},  # 빈 action은 키를 빼 계약 기본값을 쓴다
    ]


# --- 설정 검증 ---


def test_schema_accepts_list_value_forms() -> None:
    table = load_event_map(
        """
types:
  x.go:
    tags: [tool, {each: /payload/words, value: "{.}"}]
    correlation:
      resource: {each: /payload/resources, value: "{./id}"}
      plain: "{/type}"
    documents:
      - {each: /payload/resources, path: "{./id}", kind: {pointer: ./kind, default: doc}}
      - {path: "{/type}", action: read}
  y.go:
    tags: {each: /payload/words, value: "{.}"}
    documents: {path: "{/type}"}
"""
    )
    assert table.rule_for("x.go").get("documents")


@pytest.mark.parametrize(
    "rule",
    [
        "{tags: [{each: /payload/words}]}",  # value 없음
        "{correlation: {r: {each: payload, value: x}}}",  # 포인터가 아님
        "{documents: {kind: rules}}",  # path 없음
        "{documents: [{path: x, extra: 1}]}",  # 모르는 키
    ],
)
def test_schema_rejects_malformed_list_values(rule: str) -> None:
    with pytest.raises(ConfigError):
        load_event_map(f"types:\n  x.go: {rule}\n")


# --- 분류기(수집 파이프라인) ---


def test_default_map_moves_context_resources_to_documents_rules_first() -> None:
    resources = [
        {"id": "sk", "kind": "skill", "bytes": 1, "sha256": "aa"},
        {"id": "house-rules", "kind": "rule", "bytes": 10, "sha256": "ab"},
    ]
    (event,) = _scan(
        None, run_event(1, "agent.context_prepared", {"resources": resources}, ("lead",))
    )
    assert event.category == "context"
    assert [(d.kind, d.path, d.action) for d in event.documents] == [
        ("rules", "house-rules", "read"),
        ("skill", "sk", "read"),
    ]


def test_default_map_context_without_resources_has_no_documents() -> None:
    (event,) = _scan(None, run_event(1, "agent.context_prepared", {"resources": []}, ("lead",)))
    assert event.documents == []


def test_user_rule_each_fills_tags_and_correlation_lists() -> None:
    overrides = {
        "x.go": {
            "category": "custom",
            "tags": ["fixed", {"each": "/payload/resources", "value": "kind:{./kind}"}],
            "correlation": {
                "resource": {"each": "/payload/resources", "value": "{./id}"},
                "plain": "{/payload/op}",
                "none": {"each": "/payload/missing", "value": "{./id}"},
            },
        }
    }
    (event,) = _scan(overrides, run_event(1, "x.go", EVENT["payload"], ("a",)))
    assert set(event.tags) >= {"fixed", "kind:skill", "kind:rule", "custom"}
    assert event.correlation["resource"] == ["s1", "r1", "r2"]
    assert event.correlation["plain"] == "write"  # 틀 문자열은 전처럼 값 하나
    assert "none" not in event.correlation  # 항목 0개면 근거를 싣지 않는다


def test_old_user_rule_forms_behave_as_before() -> None:
    overrides = {
        "x.go": {
            "category": "c",
            "tags": ["tool", "t2"],
            "correlation": {"mcp_server": "{/payload/op}", "empty": "{/payload/missing}"},
        }
    }
    (event,) = _scan(overrides, run_event(1, "x.go", EVENT["payload"], ("a",)))
    assert set(event.tags) == {"c", "tool", "t2"}
    assert event.correlation == {"mcp_server": "write"}
    assert event.documents == []
