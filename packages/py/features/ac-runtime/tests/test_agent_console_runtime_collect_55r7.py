"""5.5R.7 C7: 위임 도구 호출 id가 호출 NodeRun의 `node.*` payload `tool_use_id`로 실린다.

플랫폼 도구(`HostTool.call_handler`)는 `call_host_tool(tool_use_id=)`로 호출 id를 받는다.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent_console_runtime import (
    CancelToken,
    GraphRuntime,
    HostTool,
    HostToolResult,
    call_host_tool,
)
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness


@pytest.fixture
async def h() -> AsyncIterator[Harness]:
    harness = make_harness()
    made: list[GraphRuntime] = []
    make = harness.make

    def tracked(**kwargs: Any) -> GraphRuntime:
        runtime = make(**kwargs)
        made.append(runtime)
        return runtime

    harness.make = tracked
    yield harness
    for runtime in made:
        await asyncio.wait_for(runtime.shutdown(), 5)


@pytest.fixture
def b() -> Builders:
    return BUILDERS


async def test_invoked_node_events_carry_tool_use_id(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = b.graph(
        [
            b.node("lead", type="t.lead", calls=["A", "A"], tool_use_ids=["tu-1"]),
            b.node("A"),
        ],
        [b.edge("lead", "A", kind="t.invoke", sp="alt", tp="in2")],
        entries=["lead"],
    )
    run = await rt.run(g)

    assert run.status == "completed"
    events = h.recorder.events.list(run.id)
    by_call: dict[int, dict[str, Any]] = {}
    for e in events:
        if e.node_path == ["lead", "A"] and e.type in ("node.started", "node.completed"):
            by_call.setdefault(int(e.payload["call"]), {})[e.type] = e.payload.get("tool_use_id")
    # 첫 호출은 id를 받았고, 두 번째 호출은 id가 없다(모름 = null)
    assert by_call == {
        0: {"node.started": "tu-1", "node.completed": "tu-1"},
        1: {"node.started": None, "node.completed": None},
    }
    # 스케줄 실행은 호출이 아니므로 언제나 null
    lead = [e for e in events if e.node_path == ["lead"] and e.type.startswith("node.")]
    assert lead
    assert all(e.payload.get("tool_use_id") is None for e in lead)


async def test_call_host_tool_passes_tool_use_id_to_call_handler() -> None:
    seen: list[tuple[dict[str, Any], str | None]] = []

    async def handler(arguments: dict[str, Any]) -> HostToolResult:
        seen.append((arguments, "handler"))
        return HostToolResult(text="plain")

    async def call_handler(arguments: dict[str, Any], tool_use_id: str | None) -> HostToolResult:
        seen.append((arguments, tool_use_id))
        return HostToolResult(text=f"id={tool_use_id}")

    with_id = HostTool("t", "d", {"type": "object"}, handler, call_handler=call_handler)
    plain = HostTool("p", "d", {"type": "object"}, handler)

    assert (await call_host_tool(with_id, {"a": 1}, tool_use_id="tu-9")).text == "id=tu-9"
    assert (await call_host_tool(with_id, {"a": 2})).text == "id=None"
    assert (await call_host_tool(plain, {"a": 3}, tool_use_id="tu-10")).text == "plain"
    assert seen == [({"a": 1}, "tu-9"), ({"a": 2}, None), ({"a": 3}, "handler")]
    # 취소된 토큰이면 어느 핸들러도 부르지 않는다
    token = CancelToken()
    token.cancel()
    result = await call_host_tool(with_id, {}, cancel=token, tool_use_id="x")
    assert result.is_error
    assert len(seen) == 3
