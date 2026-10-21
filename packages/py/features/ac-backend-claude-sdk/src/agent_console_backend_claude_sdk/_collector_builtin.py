"""기본 관측 수집기(X7의 첫 구현): `sdk-hooks`·`mcp-calls`(design §4R.3, payload 키 §8.3).

둘 다 entry point `agent_console.collectors`로 등록된다. 특별 취급은 없다 —
백엔드는 이 이름을 모른다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from claude_agent_sdk import (
    AssistantMessage,
    HookEventMessage,
    ServerToolResultBlock,
    ServerToolUseBlock,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import JsonObject, x_ui

from ._collector_api import BaseClaudeSdkCollector, CollectorContext
from ._options import CLAUDE_SDK_BACKEND_ID, DEFAULT_OBSERVED_HOOK_EVENTS
from ._translate import split_mcp_name

__all__ = ["McpCallsCollector", "McpCallsConfig", "SdkHooksCollector", "SdkHooksConfig"]


class SdkHooksConfig(BaseModel):
    """에이전트 실행 중 hook(도구 실행 전후에 도는 명령) 이벤트를 기록할 때의 설정입니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `sdk-hooks` 설정.

    model_config = ConfigDict(extra="forbid", title="SDK hook 관측")

    events: list[str] = Field(
        default_factory=lambda: list(DEFAULT_OBSERVED_HOOK_EVENTS),
        title="관측할 hook 이벤트",
        description=(
            "기록할 hook(도구 실행 전후에 도는 명령) 이벤트 이름입니다(예: PreToolUse, Stop)."
        ),
        json_schema_extra=x_ui(tier="basic", when="특정 hook 이벤트만 기록하고 싶을 때 바꾸세요."),
    )


class SdkHooksCollector(BaseClaudeSdkCollector):
    """SDK 관찰 훅 콜백(`hook.invoked`, hook_type `sdk-callback`) + CLI 설정 hook 실행 메시지
    (`HookEventMessage` → `hook.invoked`/`hook.completed`, hook_type `settings`)."""

    id: ClassVar[str] = "sdk-hooks"
    title: ClassVar[str] = "SDK hook 이벤트"
    description: ClassVar[str | None] = (
        "SDK 관찰 훅 콜백과 CLI 설정 hook 실행을 hook.* 이벤트로 기록한다."
    )
    emits: ClassVar[tuple[str, ...]] = ("hook.invoked", "hook.completed")
    config_model: ClassVar[type[BaseModel] | None] = SdkHooksConfig
    default_backend: ClassVar[str] = CLAUDE_SDK_BACKEND_ID

    def hook_events(self, config: JsonObject) -> Sequence[str]:
        parsed: SdkHooksConfig = self.parse_config(config)
        return list(parsed.events)

    def include_hook_events(self, config: JsonObject) -> bool:
        return True

    async def on_hook(
        self,
        event: str,
        data: Mapping[str, Any],
        tool_use_id: str | None,
        ctx: CollectorContext,
    ) -> None:
        payload: dict[str, Any] = {
            "event": data.get("hook_event_name"),
            "hook_type": "sdk-callback",
            "session_id": data.get("session_id"),
        }
        for key in ("tool_name", "agent_id", "agent_type"):
            if data.get(key) is not None:
                payload[key] = data[key]
        if tool_use_id is not None or data.get("tool_use_id") is not None:
            payload["tool_use_id"] = tool_use_id or data.get("tool_use_id")
        ctx.emit("hook.invoked", payload, raw=dict(data))

    def on_message(self, message: object, ctx: CollectorContext) -> None:
        if not isinstance(message, HookEventMessage):
            return
        kind = "hook.completed" if message.subtype == "hook_response" else "hook.invoked"
        data = message.data
        payload: dict[str, Any] = {
            "event": message.hook_event_name or data.get("hook_event"),
            "hook_type": "settings",
            "session_id": message.session_id,
        }
        for key in ("hook_id", "hook_name", "exit_code", "outcome"):
            if key in data:
                payload[key] = data[key]
        ctx.emit(kind, payload, raw=message)


class McpCallsConfig(BaseModel):
    """MCP(외부 도구 서버) 도구 호출을 기록합니다. 지금은 따로 정할 항목이 없습니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `mcp-calls` 설정(지금은 항목 없음).

    model_config = ConfigDict(extra="forbid", title="MCP 호출 관측")


_CALLS = "calls"
"""`ctx.state` 키: 열린 MCP 호출 `tool_use_id → (server, tool, 시작 시각)`."""


class McpCallsCollector(BaseClaudeSdkCollector):
    """MCP 서버 상태(init 메시지) + `mcp__<server>__<tool>` 도구 호출 시작·완료(소요 시간·오류)."""

    id: ClassVar[str] = "mcp-calls"
    title: ClassVar[str] = "MCP 호출"
    description: ClassVar[str | None] = (
        "MCP 서버 상태와 MCP 도구 호출 시작·완료(소요 시간·오류)를 mcp.* 이벤트로 기록한다."
    )
    emits: ClassVar[tuple[str, ...]] = (
        "mcp.server_status",
        "mcp.call_started",
        "mcp.call_completed",
    )
    config_model: ClassVar[type[BaseModel] | None] = McpCallsConfig
    default_backend: ClassVar[str] = CLAUDE_SDK_BACKEND_ID

    def on_message(self, message: object, ctx: CollectorContext) -> None:
        if isinstance(message, SystemMessage) and message.subtype == "init":
            servers = message.data.get("mcp_servers")
            if isinstance(servers, list):
                ctx.emit(
                    "mcp.server_status",
                    {
                        "servers": [
                            {"name": s.get("name"), "status": s.get("status")}
                            for s in servers
                            if isinstance(s, Mapping)
                        ]
                    },
                    raw=message,
                )
            return
        if isinstance(message, AssistantMessage):
            blocks: Sequence[Any] = message.content
        elif isinstance(message, UserMessage) and not isinstance(message.content, str):
            blocks = message.content
        else:
            return
        parent = message.parent_tool_use_id
        calls: dict[str, tuple[str, str, float]] = ctx.state.setdefault(_CALLS, {})
        for block in blocks:
            if isinstance(block, ToolUseBlock | ServerToolUseBlock):
                parts = split_mcp_name(block.name)
                if parts is None:
                    continue
                server, tool = parts
                calls[block.id] = (server, tool, ctx.clock())
                ctx.emit(
                    "mcp.call_started",
                    {"server": server, "tool": tool, "tool_use_id": block.id},
                    raw=message,
                    parent_tool_use_id=parent,
                )
            elif isinstance(block, ToolResultBlock | ServerToolResultBlock):
                call = calls.pop(block.tool_use_id, None)
                if call is None:
                    continue
                server, tool, started = call
                ctx.emit(
                    "mcp.call_completed",
                    {
                        "server": server,
                        "tool": tool,
                        "tool_use_id": block.tool_use_id,
                        "is_error": bool(getattr(block, "is_error", False)),
                        "duration_ms": max(0, round((ctx.clock() - started) * 1000)),
                    },
                    raw=message,
                    parent_tool_use_id=parent,
                )
