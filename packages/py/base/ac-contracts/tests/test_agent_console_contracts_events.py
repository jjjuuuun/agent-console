"""RunEvent 일반형·판별 유니온·parse_run_event."""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    KNOWN_RUN_EVENT_TYPES,
    AgentUsageEvent,
    NodeStatusEvent,
    RunEvent,
    parse_run_event,
)


def _event(type_: str, payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "event_id": "e1",
        "run_id": "r1",
        "seq": 1,
        "ts": 1.5,
        "node_path": ["n3"],
        "type": type_,
        "payload": payload,
        **extra,
    }


def test_node_waiting_event_with_attempt_and_path() -> None:
    ev = parse_run_event(
        _event("node.waiting", {"status": "waiting", "wait": {"reason": "approval"}}, attempt=2)
    )
    assert isinstance(ev, NodeStatusEvent)
    assert ev.attempt == 2
    assert ev.node_path == ["n3"]
    assert ev.payload.wait is not None


def test_agent_usage_payload_uses_usage_model() -> None:
    ev = parse_run_event(_event("agent.usage", {"usage": {"input_tokens": 10, "output_tokens": 2}}))
    assert isinstance(ev, AgentUsageEvent)
    assert ev.payload.usage.input_tokens == 10


def test_old_route_decided_reads_as_generic() -> None:
    """저장된 옛 `route.decided` 이벤트는 일반형으로 읽힌다."""
    ev = parse_run_event(_event("route.decided", {"chosen_port": "p"}))
    assert type(ev) is RunEvent
    assert "route.decided" not in KNOWN_RUN_EVENT_TYPES


def test_unknown_type_falls_back_to_generic() -> None:
    ev = parse_run_event(_event("plugin.custom_thing", {"x": 1}))
    assert type(ev) is RunEvent
    assert ev.payload == {"x": 1}


def test_known_type_with_bad_payload_raises() -> None:
    with pytest.raises(ValidationError):
        parse_run_event(_event("node.completed", {"status": "not-a-status"}))


def test_generic_event_round_trips_into_typed() -> None:
    generic = RunEvent.model_validate(_event("agent.text_delta", {"text": "안녕"}))
    typed = parse_run_event(generic)
    assert typed.model_dump() == {
        **generic.model_dump(),
        "payload": {"text": "안녕", "message_id": None},
    }


def test_known_types_cover_design_phase1_list() -> None:
    for t in [
        "run.created",
        "run.interrupted",
        "node.queued",
        "node.waiting",
        "node.skipped",
        "edge.traversed",
        "agent.session_started",
        "agent.text_delta",
        "agent.tool_result",
        "agent.usage",
    ]:
        assert t in KNOWN_RUN_EVENT_TYPES
    assert len(set(KNOWN_RUN_EVENT_TYPES)) == len(KNOWN_RUN_EVENT_TYPES)


def test_seq_starts_at_one() -> None:
    with pytest.raises(ValidationError):
        RunEvent.model_validate({**_event("x", {}), "seq": 0})
