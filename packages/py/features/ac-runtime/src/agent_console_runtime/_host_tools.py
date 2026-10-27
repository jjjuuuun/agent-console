"""플랫폼 도구(`host_tools`, design §5R.3·§5R.6): 모델에게 주고 호출을 플랫폼으로 돌려받는 도구.

런타임 전용 타입이다(계약 아님). 위임 방식(X12, 예: `host`)이 `HostTool`을 만들어
`AgentRequest.host_tools`에 넣고, `capabilities.host_tools`를 선언한 백엔드(X3)가 모델의 호출마다
`handler`를 부른다. 백엔드는 도구 이름·용도를 모른다 — 받은 목록을 그대로 모델에게 준다.

백엔드 공용 부품:
    - ``call_host_tool``: 핸들러 한 번 실행(예외 → 오류 결과, 실행 취소 토큰 → 핸들러 취소)
    - ``duplicate_host_tool_names``: 한 요청 안에서 겹치는 도구 이름(혼합 위임 합치기 검사)
    - ``object_input_schema``: 입력 스키마를 최상위 object 스키마 모양으로 맞춘다
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ._cancel import CancelToken

DEFAULT_HOST_TOOL_ERROR_TEMPLATE = "도구 {tool} 실행 중 오류가 났습니다({error})"
"""핸들러가 예외를 던졌을 때 모델에게 돌려줄 문장(`{tool}` = 도구 이름, `{error}` = 예외 형식 이름).
예외 메시지는 싣지 않는다(비밀이 섞일 수 있다)."""

DEFAULT_HOST_TOOL_CANCELLED_TEXT = "실행이 취소되어 도구 {tool} 호출을 끝내지 못했습니다"
"""실행 취소로 핸들러를 멈췄을 때 돌려줄 문장(`{tool}`)."""


@dataclass(frozen=True, slots=True)
class HostToolResult:
    """플랫폼 도구 호출 하나의 결과(모델에게 돌아가는 도구 결과).

    Attributes:
        text: 결과 텍스트.
        is_error: 참이면 오류 결과(모델이 실패로 보고 판단한다). 실행은 계속된다.
    """

    text: str
    is_error: bool = False


type HostToolHandler = Callable[[dict[str, Any]], Awaitable[HostToolResult]]
"""모델이 준 입력(JSON 객체) → 결과. 백엔드가 호출마다 부른다(동시에 여러 번 불릴 수 있다)."""

type HostToolCallHandler = Callable[[dict[str, Any], str | None], Awaitable[HostToolResult]]
"""(모델이 준 입력, 백엔드가 아는 도구 호출 id 또는 None) → 결과. 호출 id가 필요한 도구(예: 위임
도구가 대상 실행과 호출을 잇는 경우, design §5.5R.1 C7)가 `HostTool.call_handler`로 준다."""


@dataclass(frozen=True, slots=True)
class HostTool:
    """모델에게 줄 플랫폼 도구 하나.

    Attributes:
        name: 도구 이름(요청 안에서 유일). 백엔드가 자기 이름 규칙(예: MCP 접두)을 덧붙일 수 있다.
        description: 모델에게 보이는 설명.
        input_schema: 입력 JSON Schema(최상위 object).
        handler: 호출마다 불리는 비동기 함수(`HostToolHandler`).
        call_handler: 선택. 호출 id까지 받는 핸들러(`HostToolCallHandler`). 있으면
            `call_host_tool`이 `handler` 대신 이것을 부르고 백엔드가 준 `tool_use_id`(모르면 None)를
            넘긴다.
    """

    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: HostToolHandler
    call_handler: HostToolCallHandler | None = None


def duplicate_host_tool_names(tools: Iterable[HostTool]) -> list[str]:
    """두 번 이상 나온 도구 이름(정렬). 비어 있으면 겹침 없음."""
    counts = Counter(tool.name for tool in tools)
    return sorted(name for name, count in counts.items() if count > 1)


def object_input_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """입력 스키마 복사본을 최상위 `{"type": "object", "properties": {...}}` 모양으로 맞춘다.

    `type`·`properties`가 없으면 채운다(일부 도구 서버는 둘이 있어야 JSON Schema로 읽는다).

    Raises:
        ValueError: 최상위 `type`이 object가 아니거나 `properties`가 객체가 아니다.
    """
    out = dict(schema)
    kind = out.setdefault("type", "object")
    if kind != "object":
        raise ValueError(f"플랫폼 도구 입력 스키마의 최상위 type은 object여야 합니다: {kind!r}")
    properties = out.setdefault("properties", {})
    if not isinstance(properties, Mapping):
        raise ValueError("플랫폼 도구 입력 스키마의 properties는 객체여야 합니다")
    return out


async def call_host_tool(
    tool: HostTool,
    arguments: Mapping[str, Any],
    *,
    cancel: CancelToken | None = None,
    tool_use_id: str | None = None,
    error_template: str = DEFAULT_HOST_TOOL_ERROR_TEMPLATE,
    cancelled_text: str = DEFAULT_HOST_TOOL_CANCELLED_TEXT,
) -> HostToolResult:
    """핸들러를 한 번 실행한다. 백엔드가 모델의 호출마다 쓰는 공용 경로.

    - 핸들러 예외(`Exception`)는 `is_error` 결과(`error_template`, 예외 메시지는 싣지 않음)로
      바꾼다.
    - `cancel`(실행 취소 토큰)이 핸들러 도중 취소되면 핸들러 태스크를 취소하고 `is_error` 결과
      (`cancelled_text`)를 돌려준다. 이미 취소됐으면 핸들러를 부르지 않는다.
    - 이 코루틴 자체가 취소되면(예: 도구 서버가 요청을 취소) 핸들러도 취소되고 `CancelledError`가
      그대로 올라간다.
    - 핸들러가 `HostToolResult`가 아닌 값을 돌려주면 오류 결과다.
    - `tool_use_id`: 백엔드가 아는 이 호출의 도구 호출 id. 도구에 `call_handler`가 있으면 그것을
      이 id와 함께 부른다(없으면 `handler`, id는 쓰지 않는다).

    Returns:
        모델에게 돌려줄 결과(예외 없음, 취소 전파 제외).
    """
    if cancel is not None and cancel.cancelled:
        return HostToolResult(text=cancelled_text.format(tool=tool.name), is_error=True)
    work = asyncio.ensure_future(
        tool.call_handler(dict(arguments), tool_use_id or None)
        if tool.call_handler is not None
        else tool.handler(dict(arguments))
    )
    stop = asyncio.ensure_future(cancel.wait()) if cancel is not None else None
    try:
        if stop is not None:
            await asyncio.wait({work, stop}, return_when=asyncio.FIRST_COMPLETED)
            if not work.done():
                work.cancel()
                with contextlib.suppress(BaseException):
                    await work
                return HostToolResult(text=cancelled_text.format(tool=tool.name), is_error=True)
        result = await work
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return HostToolResult(
            text=error_template.format(tool=tool.name, error=type(exc).__name__), is_error=True
        )
    finally:
        for task in (work, stop):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
    returned: object = result  # 핸들러는 타입을 어길 수 있다(사용자 플러그인)
    if not isinstance(returned, HostToolResult):
        return HostToolResult(
            text=error_template.format(tool=tool.name, error=type(returned).__name__),
            is_error=True,
        )
    return returned
