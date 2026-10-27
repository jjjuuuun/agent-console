"""테스트·예제용 부품(패키지 코드는 이 모듈을 쓰지 않는다).

``EchoToolProvider``: 에이전트 도구 공급자(X30)의 가장 작은 구현. 받은 입력 `text`를 앞말을 붙여
돌려주는 도구 하나를 주고, 호출마다 이벤트 하나를 낸다. 새 공급자를 만들 때 본보기로 쓴다.
"""

from __future__ import annotations

from typing import Any

from agent_console_runtime import HostTool, HostToolResult

from .tools import ToolProvision, ToolProvisionContext

__all__ = ["EchoToolProvider"]


class EchoToolProvider:
    """입력 `text`를 되돌려주는 도구 하나를 주는 공급자(X30 예제).

    Args:
        id: 공급자 id(경고 details `provider`).
        tool_name: 도구 이름.
        prefix: 결과 앞에 붙일 말.
        event_type: 호출마다 낼 RunEvent type(payload: `provider`·`tool`·`tool_use_id`·`chars`,
            입력 원문은 싣지 않는다). None이면 내지 않는다.
        slot: 주면 묶음에 이 칸이 있을 때만 도구를 주고 그 칸을 소비한다(칸 값의 `prefix` 키가
            있으면 앞말로 쓴다). None이면 늘 준다.

    Attributes:
        contexts: 받은 맥락(테스트 확인용, 호출 순서).
    """

    def __init__(
        self,
        id: str = "echo",
        *,
        tool_name: str = "echo",
        prefix: str = "",
        event_type: str | None = "echo.called",
        slot: str | None = None,
    ) -> None:
        self.id = id
        self.tool_name = tool_name
        self.prefix = prefix
        self.event_type = event_type
        self.slot = slot
        self.contexts: list[ToolProvisionContext] = []

    def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
        """도구 하나(또는 칸이 없으면 없음)."""
        self.contexts.append(ctx)
        prefix = self.prefix
        consumed: frozenset[str] = frozenset()
        if self.slot is not None:
            if self.slot not in ctx.bundle.slots:
                return ToolProvision()
            consumed = frozenset({self.slot})
            prefix = _prefix_of(ctx.bundle.slots[self.slot], prefix)

        async def call(arguments: dict[str, Any], tool_use_id: str | None) -> HostToolResult:
            text = arguments.get("text")
            if not isinstance(text, str):
                return HostToolResult(text="text(문자열)가 필요합니다", is_error=True)
            if self.event_type is not None:
                await ctx.emit(
                    self.event_type,
                    {
                        "provider": self.id,
                        "tool": self.tool_name,
                        "tool_use_id": tool_use_id,
                        "chars": len(text),
                    },
                )
            return HostToolResult(text=f"{prefix}{text}")

        async def handler(arguments: dict[str, Any]) -> HostToolResult:
            return await call(arguments, None)

        tool = HostTool(
            name=self.tool_name,
            description="받은 text를 그대로 돌려줍니다.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=handler,
            call_handler=call,
        )
        return ToolProvision(host_tools=(tool,), consumed_slots=consumed)


def _prefix_of(value: Any, default: str) -> str:
    """칸 값(객체 또는 객체 목록)에서 마지막 `prefix` 문자열."""
    items = value if isinstance(value, list) else [value]
    found = default
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("prefix"), str):
            found = item["prefix"]
    return found
