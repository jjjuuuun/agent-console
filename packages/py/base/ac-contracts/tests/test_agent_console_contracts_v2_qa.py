"""계약 v2 QA 추가 테스트: Phase 1 정의 호환, 중첩 설정 묶음의 부분 층, null 채움 함정."""

from typing import Any

from agent_console_contracts import Agent, Graph, WorkspaceSettings

PHASE1_AGENT: dict[str, Any] = {
    "kind": "agent",
    "id": "quick-answer",
    "schema_version": 1,
    "name": "바로 답변",
    "description": "d",
    "labels": ["example"],
    "attributes": {"role": "answer"},
    "backend": "fake-agent",
    "model": None,
    "tools": [],
    "system_prompt": "짧게",
    "limits": None,
    "backend_options": {"delay_ms": 30},
    "legacy_unknown_field": {"keep": True},
}

PHASE1_GRAPH: dict[str, Any] = {
    "kind": "graph",
    "id": "g",
    "schema_version": 1,
    "name": "그래프",
    "inputs": [{"name": "text"}],
    "outputs": [{"name": "out"}],
    "nodes": [{"id": "a", "type": "whatever-type", "config": {"x": 1}}],
    "edges": [
        {
            "id": "e1",
            "source": {"node": "a", "port": "out"},
            "target": {"node": "a", "port": "in"},
            "kind": "any-kind",
        }
    ],
    "limits": {"directories": ["{workspace}"], "network": "deny"},
}


def test_phase1_definitions_load_and_round_trip_unchanged() -> None:
    agent = Agent.model_validate(PHASE1_AGENT)
    assert agent.model_dump(mode="json", exclude_unset=True) == PHASE1_AGENT
    graph = Graph.model_validate(PHASE1_GRAPH)
    assert graph.settings is None
    assert graph.model_dump(mode="json", exclude_unset=True) == PHASE1_GRAPH


def test_phase1_explicit_null_and_empty_are_layer_values_in_v2() -> None:
    """Phase 1 파일의 `model: null`·`tools: []`는 v2에서 '이 층이 정함'이다(상속 아님).

    1R.4/1R.3은 이 데이터를 그대로 병합하지 말고 마이그레이션(null 키 삭제 등)하거나
    작업 공간 파일을 다시 써야 한다.
    """
    agent = Agent.model_validate(PHASE1_AGENT)
    assert {"model", "tools", "limits"} <= agent.model_fields_set


def test_partial_nested_chat_layer_keeps_only_given_keys() -> None:
    doc = {
        "id": "g",
        "name": "n",
        "kind": "graph",
        "settings": {"chat": {"reply_display": "merged"}},
    }
    graph = Graph.model_validate(doc)
    assert graph.settings is not None
    assert graph.settings.chat is not None
    assert graph.settings.chat.model_fields_set == {"reply_display"}
    assert graph.model_dump(mode="json", exclude_unset=True)["settings"] == {
        "chat": {"reply_display": "merged"}
    }


def test_plain_dump_fills_defaults_which_would_break_inheritance() -> None:
    """저장소가 exclude_unset 없이 덤프하면 생략이 null/기본값으로 굳는다(1R.4가 막아야 할 함정)."""
    agent = Agent.model_validate({"id": "a", "name": "A"})
    assert "limits" in agent.model_dump(mode="json")
    assert "limits" not in agent.model_dump(mode="json", exclude_unset=True)
    ws = WorkspaceSettings.model_validate({})
    assert "chat" not in ws.model_dump(mode="json", exclude_unset=True)
    assert ws.model_dump(mode="json")["chat"]["busy_policy"] == "queue"
