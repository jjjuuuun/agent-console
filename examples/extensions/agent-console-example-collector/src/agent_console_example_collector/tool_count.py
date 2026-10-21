"""관측 수집기 `example.tool_count`: 실행 하나의 도구 호출 수를 세어 끝에 이벤트 하나로 낸다.

claude-sdk 관측 수집기(X7)는 `BaseClaudeSdkCollector`를 상속해 필요한 메서드만 고친다.

- ``on_message`` — 번역 이벤트 뒤에 SDK 메시지를 받는다. 모델 응답(`AssistantMessage`)의 도구 호출
  블록을 세어 실행별 상태(`ctx.state`)에 쌓고, 결과 메시지(`ResultMessage`)에서
  `example.tool_count{total, by_tool}`를 한 번 낸다.
- ``config_model`` — pydantic 설정 모델. 디스크립터 `config_schema`가 이 스키마가 되고, 틀린 설정은
  검증 경고(`observe.collector_config_invalid`)로 보인다.

수집기는 실행에 개입하지 않는다. 예외는 백엔드가 삼키고 경고 이벤트 하나로 남긴다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any, ClassVar, Final

from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock
from pydantic import BaseModel, ConfigDict, Field

from agent_console_backend_claude_sdk.collectors import BaseClaudeSdkCollector, CollectorContext

COLLECTOR_ID: Final = "example.tool_count"
"""수집기 id(entry point 이름과 같다). 설정 `observe.collectors`의 키."""
EVENT_TYPE: Final = "example.tool_count"
"""내는 RunEvent type(일반형 이벤트, 로그 화면에서는 `platform-runs` 출처로 보인다)."""
DEFAULT_BACKEND: Final = "claude-agent-sdk"
"""이 수집기를 쓸 백엔드 id 기본값(`descriptor.backend`). 생성 인자 `backend=`로 바꾼다."""

_STATE_KEY: Final = "counts"
_ONLY_KEY: Final = "only"


class ToolCountConfig(BaseModel):
    """`example.tool_count` 설정."""

    model_config = ConfigDict(extra="forbid", title="도구 호출 수")

    only: list[str] = Field(
        default_factory=list,
        title="셀 도구",
        description="이 이름의 도구만 센다. 비우면 전부.",
    )


def count_tool_uses(message: object, only: Collection[str] = ()) -> dict[str, int]:
    """SDK 메시지 하나에 든 도구 호출 수(도구 이름별).

    Args:
        message: SDK 메시지. 모델 응답이 아니면 빈 결과.
        only: 비어 있지 않으면 이 이름만 센다.

    Returns:
        `{도구 이름: 호출 수}`.
    """
    out: dict[str, int] = {}
    if not isinstance(message, AssistantMessage):
        return out
    for block in message.content:
        if isinstance(block, ToolUseBlock) and (not only or block.name in only):
            out[block.name] = out.get(block.name, 0) + 1
    return out


def merge_counts(total: Mapping[str, int], more: Mapping[str, int]) -> dict[str, int]:
    """두 집계를 더한 새 사전(이름순)."""
    merged = dict(total)
    for name, n in more.items():
        merged[name] = merged.get(name, 0) + n
    return dict(sorted(merged.items()))


class ToolCountCollector(BaseClaudeSdkCollector):
    """관측 수집기 `example.tool_count`(X7 예제 구현)."""

    id: ClassVar[str] = COLLECTOR_ID
    title: ClassVar[str] = "도구 호출 수(예제)"
    description: ClassVar[str | None] = "실행이 끝날 때 도구 이름별 호출 수를 이벤트 하나로 낸다."
    emits: ClassVar[tuple[str, ...]] = (EVENT_TYPE,)
    config_model: ClassVar[type[BaseModel] | None] = ToolCountConfig
    default_backend: ClassVar[str] = DEFAULT_BACKEND

    def on_message(self, message: object, ctx: CollectorContext) -> None:
        """도구 호출을 세고, 결과 메시지에서 합계를 낸다."""
        state: dict[str, Any] = ctx.state
        if isinstance(message, ResultMessage):
            counts: dict[str, int] = state.get(_STATE_KEY, {})
            ctx.emit(EVENT_TYPE, {"total": sum(counts.values()), "by_tool": counts})
            return
        if _ONLY_KEY not in state:  # 실행마다 한 번 검증(틀리면 예외 → 백엔드가 경고 하나로 남김)
            state[_ONLY_KEY] = frozenset(self.parse_config(dict(ctx.config)).only)
        found = count_tool_uses(message, state[_ONLY_KEY])
        if found:
            state[_STATE_KEY] = merge_counts(state.get(_STATE_KEY, {}), found)
