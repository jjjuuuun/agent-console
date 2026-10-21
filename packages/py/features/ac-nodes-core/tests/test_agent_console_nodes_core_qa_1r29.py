"""1R.29 QA: 반례 시도(비밀 노출, 검토 취소, 결정 목록 자유도, 다른 종류)."""

from __future__ import annotations

from typing import Any

from agent_console_contracts import WorkspaceSettings
from agent_console_nodes_core import AGENT_LOOKUP, WORKSPACE_SETTINGS
from agent_console_runtime import (
    EnvSecretProvider,
    GraphRuntime,
    SecretResolver,
    Services,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock

from .test_agent_console_nodes_core_interactions import (  # type: ignore[import-not-found]
    Stack,
    _entry_points,
    _Recording,
    agent,
    asking_graph,
    e,
    make_stack,
    n,
    team,
    user,
)

SECRET = "sk-ant-api-QA1R29SECRETVALUE"


def _stack_with_secret(*agents: Any) -> Stack:
    from agent_console_runtime import Registries, load_registries

    regs = Registries()
    load_registries(regs, entry_points=_entry_points())
    backend = _Recording()
    regs.backends.register("fake", backend)
    found = {a.id: a for a in agents}
    services = Services(
        {
            AGENT_LOOKUP: found.get,
            WORKSPACE_SETTINGS: WorkspaceSettings.model_validate(
                {"agent_defaults": {"backend": "fake"}}
            ),
        }
    )
    secrets = SecretResolver([EnvSecretProvider({"k": SECRET})])
    secrets.resolve("secret://k")  # 해석한 적 있는 값만 가려진다
    recorder = InMemoryRecorder()
    runtime = GraphRuntime(
        regs,
        recorder,
        services=services,
        clock=StepClock(),
        ids=SequentialIds("e"),
        secrets=secrets,
    )
    return Stack(runtime, recorder, backend, regs)


def _dump(stack: Stack, run_id: str) -> str:
    parts = [repr(stack.recorder.events.list(run_id))]
    parts.append(repr(stack.recorder.interactions.list(run_id=run_id)))
    parts.append(repr(stack.recorder.runs.list_node_runs(run_id)))
    return "\n".join(parts)


async def test_review_secret_not_stored() -> None:
    stack = _stack_with_secret(agent("pl", f"설계 {SECRET}"), agent("be"))
    graph = team(
        [user(), user("rv", review={"decisions": [{"id": "ok", "edit": True}]}), n("pl", "pl")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            e("h1", "pl", "out", "rv", "review", "handoff"),
            e("a", "rv", "ok", "you", "hears", "reply"),
        ],
    )
    handle = await stack.start(graph, "x")
    [pending] = await stack.pending(handle.run_id)
    assert SECRET not in repr(pending)
    await stack.runtime.respond(
        handle.run_id, pending.id, {"decision": "ok", "edited": f"고침 {SECRET}"}
    )
    run = await handle.wait()
    assert run.status == "completed", run.error
    assert SECRET not in _dump(stack, run.id)


async def test_question_secret_not_stored() -> None:
    a = agent(
        "a",
        "$answer_1",
        ask=[{"kind": "question", "payload": {"text": f"키 {SECRET}?"}, "title": SECRET}],
    )
    stack = _stack_with_secret(a)
    handle = await stack.start(asking_graph(), "x")
    [pending] = await stack.pending(handle.run_id)
    assert SECRET not in repr(pending)
    await stack.runtime.respond(handle.run_id, pending.id, {"response": f"답 {SECRET}"})
    run = await handle.wait()
    assert SECRET not in _dump(stack, run.id)


async def test_review_cancel_while_waiting() -> None:
    stack = make_stack(agent("pl"), agent("be"))
    graph = team(
        [user(), user("rv", review={"decisions": [{"id": "ok"}]}), n("pl", "pl"), n("be", "be")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            e("h1", "pl", "out", "rv", "review", "handoff"),
            e("h2", "rv", "ok", "be", "in", "handoff"),
        ],
    )
    handle = await stack.start(graph, "x")
    await stack.pending(handle.run_id)
    handle.cancel()
    run = await handle.wait()
    assert run.status == "cancelled"
    [closed] = stack.interactions(run)
    assert closed.status == "cancelled"
    assert stack.node_runs(run)["be"].status in {"skipped", "cancelled"}


async def test_three_custom_decisions_and_dead_ports() -> None:
    """결정 목록은 데이터: 3개, 임의 id, 선택하지 않은 포트의 하류는 skipped."""
    stack = make_stack(agent("pl", "초안"), agent("b1"), agent("b2"), agent("b3"))
    decisions = [{"id": "go_a", "label": "A로"}, {"id": "go_b"}, {"id": "보류-c", "feedback": True}]
    graph = team(
        [
            user(),
            user("rv", review={"decisions": decisions, "output_template": "[$decision] $content"}),
            n("pl", "pl"),
            n("b1", "b1"),
            n("b2", "b2"),
            n("b3", "b3"),
        ],
        [
            e("m", "you", "says", "pl", "in", "message"),
            e("h1", "pl", "out", "rv", "review", "handoff"),
            e("o1", "rv", "go_a", "b1", "in", "handoff"),
            e("o2", "rv", "go_b", "b2", "in", "handoff"),
            e("o3", "rv", "보류-c", "b3", "in", "handoff"),
        ],
    )
    handle = await stack.start(graph, "x")
    [pending] = await stack.pending(handle.run_id)
    await stack.runtime.respond(handle.run_id, pending.id, {"decision": "보류-c"})
    run = await handle.wait()
    runs = stack.node_runs(run)
    assert runs["b3"].status == "succeeded", run.error
    assert runs["b1"].status == "skipped"
    assert runs["b2"].status == "skipped"


async def test_review_with_other_kind_uses_that_kind() -> None:
    """kind를 바꾸면 그 id로 연다(응답 스키마는 결정 enum)."""
    stack = make_stack(agent("pl"), agent("be"))
    graph = team(
        [user(), user("rv", review={"kind": "review", "decisions": [{"id": "ok"}]}), n("pl", "pl")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            e("h1", "pl", "out", "rv", "review", "handoff"),
        ],
    )
    handle = await stack.start(graph, "x")
    [pending] = await stack.pending(handle.run_id)
    assert pending.response_schema["properties"]["decision"] == {"enum": ["ok"]}
    await stack.runtime.respond(handle.run_id, pending.id, {"decision": "ok"})
    run = await handle.wait()
    assert run.status == "completed", run.error
