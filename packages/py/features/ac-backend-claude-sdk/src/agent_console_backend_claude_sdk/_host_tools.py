"""플랫폼 도구(`AgentRequest.host_tools`) → in-process SDK MCP 서버.

`claude_agent_sdk.create_sdk_mcp_server`·`tool`로 같은 프로세스 안의 MCP 서버를 만들어
`ClaudeAgentOptions.mcp_servers`에 넣는다. 모델이 부르는 이름은 Claude Code MCP 규칙
`mcp__<서버>__<도구>`이고, 이 이름을 `allowed_tools`(사전 승인)에 넣는다. 서버 이름은 백엔드 옵션
`host_tool_server`(스키마 기본값)다. 호출은 `agent_console_runtime.call_host_tool`로 실행한다(예외 →
오류 결과, 실행 취소 → 핸들러 취소). I/O 없음 — 서버 객체만 만든다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool

from agent_console_contracts import LogWarningPayload
from agent_console_runtime import (
    CancelToken,
    HostTool,
    call_host_tool,
    duplicate_host_tool_names,
    object_input_schema,
)

from ._translate import MCP_TOOL_PREFIX

HOST_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
"""플랫폼 도구 이름 형식(MCP 도구 이름으로 쓸 수 있는 문자)."""

MODEL_TOOL_NAME_LIMIT = 64
"""모델 API 도구 이름 길이 한도(Anthropic Messages API `^[a-zA-Z0-9_-]{1,64}$`). 넘으면 경고만 한다
(CLI가 MCP 도구 이름을 어떻게 줄이는지는 미확인 — design §R3.7 미확인 SDK 동작)."""

type ToolServerFactory = Callable[[str, list[SdkMcpTool[Any]]], Any]
"""(서버 이름, SDK 도구 목록) → `mcp_servers` 값. 기본 `create_sdk_mcp_server`."""


def sdk_tool_server(name: str, tools: list[SdkMcpTool[Any]]) -> Any:
    """기본 `ToolServerFactory`: `create_sdk_mcp_server(name=, tools=)`(in-process MCP 서버)."""
    return create_sdk_mcp_server(name=name, tools=tools)


def host_tool_rule(server: str, tool_name: str) -> str:
    """모델이 부르는 이름 = `allowed_tools` 규칙: `mcp__<server>__<tool>`."""
    return f"{MCP_TOOL_PREFIX}{server}__{tool_name}"


@dataclass(frozen=True)
class HostToolMapping:
    """플랫폼 도구 → SDK 재료.

    Attributes:
        server: MCP 서버 이름.
        config: `mcp_servers[server]` 값(`McpSdkServerConfig`).
        rules: `allowed_tools`에 넣을 이름(`mcp__<server>__<tool>`, 입력 순서).
        warnings: 실행 전 경고(이름 길이 등).
    """

    server: str
    config: Any
    rules: list[str]
    warnings: list[LogWarningPayload] = field(default_factory=list)


def sdk_tool_handler(host: HostTool, cancel: CancelToken | None) -> Any:
    """`HostTool` → SDK 도구 핸들러(`dict` 입력 → `{"content": [...], "is_error": bool}`)."""

    async def handler(args: Any) -> dict[str, Any]:
        result = await call_host_tool(host, args if isinstance(args, dict) else {}, cancel=cancel)
        return {"content": [{"type": "text", "text": result.text}], "is_error": result.is_error}

    return handler


def build_host_tool_server(
    tools: Sequence[HostTool],
    *,
    server: str,
    cancel: CancelToken | None = None,
    reserved: Iterable[str] = (),
    factory: ToolServerFactory = sdk_tool_server,
) -> HostToolMapping | None:
    """플랫폼 도구를 in-process MCP 서버 하나로 묶는다. 도구가 없으면 None.

    Args:
        tools: `AgentRequest.host_tools`.
        server: 서버 이름(백엔드 옵션 `host_tool_server`).
        cancel: 실행 취소 토큰(취소되면 진행 중 핸들러를 멈춘다).
        reserved: 이미 쓰는 MCP 서버 이름(설정·묶음). 겹치면 오류.
        factory: 서버 생성기(테스트 주입).

    Raises:
        ValueError: 도구 이름 형식 위반·겹침, 서버 이름 충돌, 입력 스키마가 object가 아님
            (메시지에 이름만 싣는다).
    """
    if not tools:
        return None
    duplicates = duplicate_host_tool_names(tools)
    if duplicates:
        raise ValueError(f"플랫폼 도구 이름이 겹칩니다: {', '.join(duplicates)}")
    bad = [t.name for t in tools if not HOST_TOOL_NAME_PATTERN.fullmatch(t.name)]
    if bad:
        raise ValueError(
            f"플랫폼 도구 이름은 영문·숫자·_·-만 쓸 수 있습니다: {', '.join(map(repr, bad))}"
        )
    if server in set(reserved):
        raise ValueError(
            f"플랫폼 도구 서버 이름 {server!r}가 다른 MCP 서버 이름과 겹칩니다"
            "(backend_options.host_tool_server로 바꾸세요)"
        )
    sdk_tools = [
        tool(t.name, t.description, object_input_schema(t.input_schema))(
            sdk_tool_handler(t, cancel)
        )
        for t in tools
    ]
    rules = [host_tool_rule(server, t.name) for t in tools]
    long_names = [r for r in rules if len(r) > MODEL_TOOL_NAME_LIMIT]
    warnings = (
        [
            LogWarningPayload(
                message=f"플랫폼 도구 이름이 모델 도구 이름 한도({MODEL_TOOL_NAME_LIMIT}자)를 "
                "넘습니다. 서버나 도구 이름을 줄이세요",
                details={"option": "host_tool_server", "names": long_names},
            )
        ]
        if long_names
        else []
    )
    return HostToolMapping(
        server=server, config=factory(server, sdk_tools), rules=rules, warnings=warnings
    )
