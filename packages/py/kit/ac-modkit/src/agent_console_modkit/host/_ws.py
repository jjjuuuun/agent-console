"""WebSocket 다중화(`/ws`, design §5.3·§R5.1·§3R.1.3 호스트). 3R.8에서 서버 앱에서 옮겨 왔다.

- 인증: 연결을 받은 뒤 Host·Origin(``close_forbidden``, 기본 4403)·``?token=``
  (``close_unauthorized``, 기본 4401)을 검사하고 실패하면 아무것도 보내지 않고 닫는다.
- 메시지: 코덱(``WsCodec``)이 문자열 ↔ 명령·메시지를 바꾼다. 기본 ``JsonWsCodec``은
  ``{"type": "subscribe"|"unsubscribe", "id"?, "payload": {"topic", "since_seq"?}}``를 읽는다.
- 토픽: 처리기 표(``ModuleParts.ws_topics`` 합친 것)에서 정확히 일치하는 키, 아니면 ``"<종류>:"``
  접두 키(대상 필수)를 찾는다. 처리기는 거절(``WsReject``)·구독 시작(``WsForward``)·받아 두기
  (``None``) 중 하나를 돌려준다. 거절이 아닐 때만 같은 토픽의 이전 구독을 닫고 한도를 검사한다.
- 한도: 메시지 크기(``max_ws_message_bytes``), 연결당 구독 수(``max_ws_subscriptions``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_modkit._module import WsForward, WsReject, WsSubscribeRequest, WsTopicHandler

from ._security import (
    BAD_REQUEST,
    PAYLOAD_TOO_LARGE,
    TOKEN_QUERY,
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_UNAUTHORIZED,
    SecurityPolicy,
)

_default_log = logging.getLogger("agent_console_modkit.host.ws")


@dataclass(frozen=True)
class WsCommand:
    """클라이언트 명령(코덱이 해석한 결과)."""

    action: Literal["subscribe", "unsubscribe"]
    topic: str
    since_seq: int = 0
    request_id: str | None = None


@dataclass(frozen=True)
class WsInvalid:
    """해석 실패. ``reject``가 ``error`` 메시지로 간다."""

    reject: WsReject
    request_id: str | None = None


class WsCodec(Protocol):
    """WS 메시지 형식. 호스트는 형식을 모르고 이것만 부른다."""

    def decode(self, text: str) -> WsCommand | WsInvalid:
        """클라이언트 문자열 → 명령 또는 해석 실패."""
        ...

    def encode(self, message: object) -> str:
        """보낼 메시지(처리기가 넘긴 것·``error`` 메시지) → 문자열."""
        ...

    def error(self, reject: WsReject, request_id: str | None) -> object:
        """거절 → 보낼 ``error`` 메시지."""
        ...


class _SubscribePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    topic: str = Field(min_length=1)
    since_seq: int | None = Field(default=None, ge=0)


class _Command(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["subscribe", "unsubscribe"]
    id: str | None = None
    payload: _SubscribePayload


class JsonWsCodec:
    """기본 코덱. 메시지가 pydantic 모델이면 ``model_dump_json()``, 아니면 JSON(ensure_ascii 끔).

    ``error`` 메시지 모양: ``{"type": "error", "id": <요청 id>, "payload": {"code", "message",
    "details"}}``. 해석 실패의 ``details.issues``는 ``[{"path", "message"}]``.
    """

    def decode(self, text: str) -> WsCommand | WsInvalid:
        try:
            cmd = _Command.model_validate_json(text)
        except ValidationError as exc:
            issues = [
                {"path": ".".join(str(p) for p in e.get("loc", ())), "message": e.get("msg", "")}
                for e in exc.errors(include_input=False, include_url=False)
            ]
            return WsInvalid(
                WsReject(BAD_REQUEST, "메시지 형식이 잘못됐습니다", {"issues": issues}),
                request_id_of(text),
            )
        return WsCommand(cmd.type, cmd.payload.topic, cmd.payload.since_seq or 0, cmd.id)

    def encode(self, message: object) -> str:
        if isinstance(message, BaseModel):
            return message.model_dump_json()
        return json.dumps(message, ensure_ascii=False)

    def error(self, reject: WsReject, request_id: str | None) -> object:
        return {
            "type": "error",
            "id": request_id,
            "payload": {
                "code": reject.code,
                "message": reject.message,
                "details": dict(reject.details),
            },
        }


def request_id_of(text: str) -> str | None:
    """해석에 실패한 메시지에서 ``id``(문자열)만 꺼낸다."""
    try:
        data: Any = json.loads(text)
    except ValueError:
        return None
    value = data.get("id") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def route_topic(
    topics: Mapping[str, WsTopicHandler], topic: str
) -> tuple[WsTopicHandler, str] | None:
    """토픽 → (처리기, 대상). 정확히 일치하는 키(``":"``로 끝나지 않음)가 먼저, 아니면 접두 키."""
    exact = topics.get(topic)
    if exact is not None and not topic.endswith(":"):
        return exact, ""
    kind, sep, target = topic.partition(":")
    if sep and target:
        handler = topics.get(f"{kind}:")
        if handler is not None:
            return handler, target
    return None


class WsConnection:
    """소켓 하나의 구독 상태. 보내기는 잠금으로 직렬화한다."""

    def __init__(
        self,
        ws: WebSocket,
        topics: Mapping[str, WsTopicHandler],
        policy: SecurityPolicy,
        codec: WsCodec,
        logger: logging.Logger,
    ) -> None:
        self.ws = ws
        self.topics = topics
        self.policy = policy
        self.codec = codec
        self._log = logger
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._passive: set[str] = set()

    async def send(self, message: object) -> None:
        text = self.codec.encode(message)
        async with self._lock:
            await self.ws.send_text(text)

    async def reject(self, reject: WsReject, request_id: str | None) -> None:
        await self.send(self.codec.error(reject, request_id))

    async def handle_text(self, text: str) -> None:
        if len(text.encode("utf-8")) > self.policy.max_ws_message_bytes:
            await self.reject(WsReject(PAYLOAD_TOO_LARGE, "메시지가 너무 큽니다"), None)
            return
        decoded = self.codec.decode(text)
        if isinstance(decoded, WsInvalid):
            await self.reject(decoded.reject, decoded.request_id)
            return
        if decoded.action == "subscribe":
            await self.subscribe(decoded)
        else:
            await self.unsubscribe(decoded.topic)

    def topic_count(self) -> int:
        return len(self._tasks) + len(self._passive)

    async def _reserve(self, topic: str, request_id: str | None) -> bool:
        """같은 토픽의 이전 구독을 닫고, 한도를 넘으면 오류를 보낸다."""
        await self.unsubscribe(topic)
        if self.topic_count() >= self.policy.max_ws_subscriptions:
            await self.reject(
                WsReject(
                    BAD_REQUEST, "구독 수 한도를 넘었습니다", {"reason": "subscription_limit"}
                ),
                request_id,
            )
            return False
        return True

    async def subscribe(self, cmd: WsCommand) -> None:
        topic = cmd.topic
        routed = route_topic(self.topics, topic)
        if routed is None:
            await self.reject(
                WsReject(
                    BAD_REQUEST, f"알 수 없는 토픽입니다: {topic}", {"reason": "unknown_topic"}
                ),
                cmd.request_id,
            )
            return
        handler, target = routed
        result = await handler(WsSubscribeRequest(topic, target, cmd.since_seq, cmd.request_id))
        if isinstance(result, WsReject):
            await self.reject(result, cmd.request_id)
            return
        if not await self._reserve(topic, cmd.request_id):
            return
        if result is None:
            self._passive.add(topic)  # 보낼 메시지 없음
        else:
            self._spawn(topic, result)

    async def unsubscribe(self, topic: str) -> None:
        self._passive.discard(topic)
        task = self._tasks.pop(topic, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    def _spawn(self, topic: str, forward: WsForward) -> None:
        async def runner() -> None:
            try:
                await forward(self.send)
            except (WebSocketDisconnect, RuntimeError):
                pass  # 소켓이 닫힘
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log.exception("WS 중계 실패: %s", topic.partition(":")[0])
            finally:
                if self._tasks.get(topic) is task:
                    self._tasks.pop(topic, None)

        task = asyncio.ensure_future(runner())
        self._tasks[topic] = task

    async def close(self) -> None:
        for topic in list(self._tasks) + list(self._passive):
            await self.unsubscribe(topic)


type TopicsSource = (
    Mapping[str, WsTopicHandler] | Callable[[WebSocket], Mapping[str, WsTopicHandler]]
)


def websocket_endpoint(
    topics: TopicsSource,
    policy: SecurityPolicy,
    *,
    codec: WsCodec | None = None,
    logger: logging.Logger | None = None,
    close_forbidden: int = WS_CLOSE_FORBIDDEN,
    close_unauthorized: int = WS_CLOSE_UNAUTHORIZED,
) -> Callable[[WebSocket], Awaitable[None]]:
    """`/ws` 엔드포인트 함수(``app.add_api_websocket_route(path, ...)``로 붙인다).

    Args:
        topics: 토픽 키 → 처리기, 또는 연결마다 그 표를 돌려주는 함수(앱 상태에서 꺼낼 때).
        policy: Host·Origin·토큰·크기·구독 수 규칙.
        codec: 메시지 형식. 기본 ``JsonWsCodec``.
        logger: 중계 실패 로그.
        close_forbidden: Host·Origin 실패 close 코드.
        close_unauthorized: 토큰 실패 close 코드.
    """
    use_codec: WsCodec = codec or JsonWsCodec()
    log = logger or _default_log

    async def endpoint(ws: WebSocket) -> None:
        await ws.accept()
        host = ws.headers.get("host")
        if not policy.host_ok(host) or not policy.origin_ok(ws.headers.get("origin"), host):
            await ws.close(code=close_forbidden, reason="forbidden")
            return
        if not policy.token_ok(ws.query_params.get(TOKEN_QUERY)):
            await ws.close(code=close_unauthorized, reason="unauthorized")
            return
        table = topics(ws) if callable(topics) else topics
        conn = WsConnection(ws, table, policy, use_codec, log)
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if text is None and message.get("bytes") is not None:
                    try:
                        text = bytes(message["bytes"]).decode("utf-8")
                    except UnicodeDecodeError:
                        text = ""
                await conn.handle_text(text or "")
        except WebSocketDisconnect:
            pass
        finally:
            await conn.close()

    return endpoint


__all__ = [
    "JsonWsCodec",
    "TopicsSource",
    "WsCodec",
    "WsCommand",
    "WsConnection",
    "WsInvalid",
    "request_id_of",
    "route_topic",
    "websocket_endpoint",
]
