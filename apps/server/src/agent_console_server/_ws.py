"""WebSocket `/ws`(design §5.3, §R5.1, §R14.4): 토픽 구독(`since_seq` 재생 → 실시간).

연결 인증·메시지 크기·구독 수 한도·토픽 다중화는 `agent_console_modkit.host`가 맡는다(3R.8).
이 파일은 계약 메시지 코덱만 둔다. 토픽은 켜진 모듈이 `ModuleParts.ws_topics`로 알린다(호스트는
토픽 이름을 모른다). 모르는 토픽 구독은 호스트가 거절한다(`error`).

- 3R.16: 보낼 메시지가 없던 `graph:<id>` 토픽은 계약에서 뺐다(받던 통짜 모듈도 지웠다).
- 콘솔 메시지(`console.*`)는 2R.20에서 계약에서 삭제했다.
  모르는 메시지처럼 `error {code: bad_request}`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping

from fastapi import WebSocket
from pydantic import BaseModel, ValidationError

from agent_console_contracts import (
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_UNAUTHORIZED,
    ErrorCodes,
    ErrorInfo,
    ErrorMessage,
    SubscribeMessage,
    WsClientMessage,
)
from agent_console_modkit import WsReject, WsTopicHandler
from agent_console_modkit.host import (
    SecurityPolicy,
    WsCommand,
    WsInvalid,
    request_id_of,
)
from agent_console_modkit.host import (
    websocket_endpoint as host_websocket_endpoint,
)

from ._errors import issues_from_errors

_log = logging.getLogger("agent_console_server")


class ContractWsCodec:
    """계약(`WsClientMessage`·`ErrorMessage`) 메시지 코덱."""

    def decode(self, text: str) -> WsCommand | WsInvalid:
        try:
            message = WsClientMessage.model_validate_json(text).root
        except ValidationError as exc:
            issues = issues_from_errors(exc.errors(include_input=False, include_url=False))
            return WsInvalid(
                WsReject(
                    ErrorCodes.BAD_REQUEST,
                    "메시지 형식이 잘못됐습니다",
                    {"issues": [i.model_dump(mode="json", exclude_none=True) for i in issues]},
                ),
                request_id_of(text),
            )
        if isinstance(message, SubscribeMessage):
            return WsCommand(
                "subscribe", message.payload.topic, message.payload.since_seq or 0, message.id
            )
        return WsCommand("unsubscribe", message.payload.topic, 0, message.id)

    def encode(self, message: object) -> str:
        if not isinstance(message, BaseModel):
            raise TypeError(f"계약 메시지가 아닙니다: {type(message)!r}")
        return message.model_dump_json()

    def error(self, reject: WsReject, request_id: str | None) -> object:
        return ErrorMessage(
            type="error",
            id=request_id,
            payload=ErrorInfo(
                code=reject.code, message=reject.message, details=dict(reject.details)
            ),
        )


def websocket_endpoint(
    topics: Mapping[str, WsTopicHandler], policy: SecurityPolicy
) -> Callable[[WebSocket], Awaitable[None]]:
    """`/ws` 엔드포인트(modkit 호스트 다중화 + 켜진 모듈의 토픽 처리기·계약 코덱)."""
    return host_websocket_endpoint(
        topics,
        policy,
        codec=ContractWsCodec(),
        logger=_log,
        close_forbidden=WS_CLOSE_FORBIDDEN,
        close_unauthorized=WS_CLOSE_UNAUTHORIZED,
    )
