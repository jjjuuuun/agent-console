"""테스트 도우미(공개, 운영 코드에서 쓰지 않는다).

- `ValidatingSink`·`ListeningSink`·`InteractiveSink`: 공용 테스트 sink
  (`agent_console_runtime.testing_sink`를 다시 내보낸다)
- `FakeSdkClient`: 가짜 SDK 클라이언트. 스크립트의 `PermissionCall`은 `can_use_tool` 호출로,
  `SdkToolCall`은 in-process SDK MCP 서버 도구 호출(CLI가 하는 JSON-RPC)로 흉내 낸다
- `call_sdk_mcp_tool`: `mcp_servers`의 in-process 서버(`create_sdk_mcp_server` 결과)에 CLI처럼
  `initialize` → `tools/call`을 보내 결과(JSON-RPC `result`)를 돌려준다. SDK 내부 모듈
  `claude_agent_sdk._internal.sdk_mcp_bridge`(실제 CLI 경로와 같은 다리)를 쓴다 — 설치 SDK
  0.2.166에서 확인했다. SDK가 바뀌어 없어지면 이 도우미만 고친다
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_console_runtime.testing_sink import InteractiveSink, ListeningSink, ValidatingSink

__all__ = [
    "FakeSdkClient",
    "InteractiveSink",
    "ListeningSink",
    "PermissionCall",
    "SdkToolCall",
    "ValidatingSink",
    "call_sdk_mcp_tool",
]

MCP_TEST_PROTOCOL_VERSION = "2025-06-18"
"""`call_sdk_mcp_tool`이 `initialize`에 싣는 MCP 프로토콜 버전(테스트용)."""


async def call_sdk_mcp_tool(
    config: Any, tool: str, arguments: dict[str, Any], *, request_id: int = 1
) -> dict[str, Any]:
    """in-process SDK MCP 서버 설정(`{"type": "sdk", "name", "instance"}`)의 도구를 부른다.

    Returns:
        JSON-RPC `result`(`content`·`isError`). 오류 응답이면 `{"error": ...}`.
    """
    from claude_agent_sdk._internal.sdk_mcp_bridge import SdkMcpBridge

    bridge = SdkMcpBridge(str(config["name"]), config["instance"])
    try:
        await bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_TEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "agent-console-test", "version": "0"},
                },
            }
        )
        await bridge.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        response = await bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        )
    finally:
        await bridge.aclose()
    if response is None:
        return {"error": "no response"}
    if "result" in response:
        result: dict[str, Any] = response["result"]
        return result
    return {"error": response.get("error")}


@dataclass
class SdkToolCall:
    """`FakeSdkClient` 스크립트 항목: 이 자리에서 `options.mcp_servers[server]`의 도구를 부른다
    (CLI가 in-process MCP 서버를 부르는 것과 같은 JSON-RPC, `call_sdk_mcp_tool`).

    결과(JSON-RPC `result`)는 `results`에 쌓인다. 서버가 없으면 `{"error": "no server"}`.
    """

    server: str
    tool: str
    arguments: dict[str, Any]
    results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PermissionCall:
    """`FakeSdkClient` 스크립트 항목: 이 자리에서 `options.can_use_tool`을 부른다.

    콜백 결과는 `results`에 쌓인다(콜백이 없으면 None).
    """

    tool_name: str
    input: dict[str, Any]
    context: Any = None
    results: list[Any] = field(default_factory=list)


class FakeSdkClient:
    """`SdkClient` 가짜. 정해 둔 메시지를 내고, 원하면 훅 콜백을 먼저 호출한다.

    `block=True`면 메시지를 다 낸 뒤 `interrupt()`까지 기다렸다가(무시 모드가 아니면)
    오류 결과를 낸다.
    """

    def __init__(
        self,
        options: Any,
        script: list[Any],
        *,
        hook_calls: list[tuple[str, dict[str, Any]]] | None = None,
        block: bool = False,
        ignore_interrupt: bool = False,
        connect_error: Exception | None = None,
    ) -> None:
        import asyncio

        self.options = options
        self.script = script
        self.hook_calls = hook_calls or []
        self.hook_outputs: list[Any] = []
        self.block = block
        self.ignore_interrupt = ignore_interrupt
        self.connect_error = connect_error
        self.prompts: list[str] = []
        self.interrupted = asyncio.Event()
        self.disconnected = False

    async def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error

    async def query(self, prompt: str) -> None:
        self.prompts.append(prompt)

    async def receive_response(self) -> Any:
        import asyncio

        from claude_agent_sdk import ResultMessage

        for event, data in self.hook_calls:
            for matcher in (self.options.hooks or {}).get(event, []):
                for hook in matcher.hooks:
                    out = await hook(data, data.get("tool_use_id"), {"signal": None})
                    self.hook_outputs.append(out)
        for msg in self.script:
            if isinstance(msg, SdkToolCall):
                config = (self.options.mcp_servers or {}).get(msg.server)
                if config is None:
                    msg.results.append({"error": "no server"})
                else:
                    msg.results.append(await call_sdk_mcp_tool(config, msg.tool, msg.arguments))
                continue
            if isinstance(msg, PermissionCall):
                callback = self.options.can_use_tool
                if callback is None:
                    msg.results.append(None)
                else:
                    msg.results.append(await callback(msg.tool_name, msg.input, msg.context))
                continue
            yield msg
        if self.block:
            if self.ignore_interrupt:
                await asyncio.Event().wait()
            await self.interrupted.wait()
            yield ResultMessage(
                subtype="error_during_execution",
                duration_ms=1,
                duration_api_ms=1,
                is_error=True,
                num_turns=1,
                session_id="sess-1",
            )

    async def interrupt(self) -> None:
        self.interrupted.set()

    async def disconnect(self) -> None:
        self.disconnected = True
