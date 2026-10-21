"""공용 테스트 sink: `ValidatingSink`(계약 검증·하위 경로)·`ListeningSink`·`InteractiveSink`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_console_runtime import (
    BackendEventSink,
    InteractionRequest,
    InteractivePort,
    SubagentResultListener,
)
from agent_console_runtime.testing_sink import InteractiveSink, ListeningSink, ValidatingSink


async def test_records_and_validates_events() -> None:
    sink = ValidatingSink()
    typed: BackendEventSink = sink  # 구조적으로 BackendEventSink를 만족한다(mypy)
    assert typed is sink
    await sink.emit("agent.message", {"role": "assistant", "text": "hi"})
    await sink.emit(
        "agent.message",
        {"role": "assistant", "text": "sub"},
        actor="worker",
        node_path=sink.child_path("w"),
    )
    assert sink.types == ["agent.message", "agent.message"]
    assert [e.node_path for e in sink.events] == [["n1"], ["n1", "w"]]
    assert sink.events[1].actor == "worker"
    assert [e.payload["text"] for e in sink.at("n1", "w")] == ["sub"]
    assert sink.of("agent.message")[0]["text"] == "hi"


async def test_rejects_contract_violation_and_foreign_path() -> None:
    sink = ValidatingSink(["lead"])
    with pytest.raises(ValidationError):
        await sink.emit("agent.message", {"text": 1})
    with pytest.raises(ValueError, match="시작"):
        await sink.emit("log.warning", {"message": "x"}, node_path=["other", "w"])


async def test_listening_sink_records_and_can_fail() -> None:
    sink = ListeningSink(["lead"])
    assert isinstance(sink, SubagentResultListener)
    await sink.on_subagent_result("w", text="t", status="succeeded", actor="a", tool_use_id="x")
    assert sink.results == [
        {"name": "w", "text": "t", "status": "succeeded", "actor": "a", "tool_use_id": "x"}
    ]
    with pytest.raises(RuntimeError):
        await ListeningSink(fail=True).on_subagent_result(
            "w", text="t", status="failed", actor=None, tool_use_id="x"
        )


async def test_interactive_sink_answers_from_function() -> None:
    sink = InteractiveSink(lambda req: {"ok": req.kind})
    assert isinstance(sink, InteractivePort)
    out = await sink.request_input(InteractionRequest(kind="question"))
    assert (out.status, out.response) == ("answered", {"ok": "question"})
    cancelled = await InteractiveSink().request_input(InteractionRequest(kind="question"))
    assert cancelled.status == "cancelled"
    assert [r.kind for r in sink.requests] == ["question"]
