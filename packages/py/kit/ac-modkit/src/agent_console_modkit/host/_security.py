"""로컬 서버 보안(agent_bench `server.py` 이식, design §9.1·§3R.1.3 호스트): Host·Origin·토큰 검사,
요청 크기 제한. 3R.8에서 서버 앱에서 옮겨 왔다(동작 불변).

- Host: 루프백 이름 + 바인딩 포트, 또는 `allowed_hosts`(DNS 리바인딩 차단).
- Origin: 있으면 같은 출처(`http(s)://<Host>`) 또는 `allowed_origins`만.
- 토큰: 변경 요청(POST/PUT/PATCH/DELETE)은 `X-Console-Token`, WS는 `?token=`. 상수 시간 비교.
- 크기: 본문을 한도까지만 읽고 넘으면 413(`Content-Length`가 없어도 센다).
- CORS: `allowed_origins`에 **명시된** 출처에만 `Access-Control-Allow-Origin`(그 출처), 노출 헤더
  `ETag`. preflight(`OPTIONS` + `Access-Control-Request-Method`)도 Host 검사를 먼저 통과해야 하고,
  허용 출처가 아니면 403. 허용 헤더 `X-Console-Token`·`If-Match`·`Content-Type`. 쿠키를 쓰지
  않으므로 credentials는 허용하지 않는다. `GET <api_prefix>/bootstrap`의
  `Sec-Fetch-Site: cross-site`도 명시 출처일 때만 허용한다.
- 오류 본문은 `{"error": {"code", "message", "details"}}`(계약 `ErrorResponse`와 같은 모양). 코드 →
  HTTP 상태는 `error_status`로 주입한다(기본 `DEFAULT_ERROR_STATUS`).
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import secrets
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol

from agent_console_modkit._errors import FEATURE_UNAVAILABLE, NOT_READY

TOKEN_HEADER = "x-console-token"
"""변경 요청의 토큰 헤더(소문자, ASGI 헤더 이름)."""
TOKEN_QUERY = "token"
"""WS 연결 쿼리 이름."""
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

LOOPBACK_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost", "::1")
"""항상 허용하는 Host 이름(바인딩 포트와 함께)."""

WS_CLOSE_UNAUTHORIZED = 4401
"""WS close 코드: 토큰 없음·불일치(계약 `WS_CLOSE_UNAUTHORIZED`와 같은 값)."""
WS_CLOSE_FORBIDDEN = 4403
"""WS close 코드: Host·Origin 검사 실패(계약 `WS_CLOSE_FORBIDDEN`과 같은 값)."""

BAD_REQUEST = "bad_request"
UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
PAYLOAD_TOO_LARGE = "payload_too_large"
INTERNAL = "internal"

DEFAULT_ERROR_STATUS: Mapping[str, int] = {
    BAD_REQUEST: 400,
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    "not_found": 404,
    PAYLOAD_TOO_LARGE: 413,
    "validation_failed": 422,
    FEATURE_UNAVAILABLE: 409,
    INTERNAL: 500,
    NOT_READY: 503,
}
"""호스트가 쓰는 오류 코드 → HTTP 상태(계약 `HTTP_STATUS_BY_ERROR_CODE`의 부분집합과 같은 값).
모르는 코드는 400."""

CORS_ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE"
CORS_ALLOW_HEADERS = "X-Console-Token, If-Match, Content-Type"
CORS_EXPOSE_HEADERS = "ETag, X-Console-Issues"
CORS_MAX_AGE = "600"

SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
)

_default_access = logging.getLogger("agent_console_modkit.host.access")

type Scope = MutableMapping[str, Any]
type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]
type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _header(scope: Scope, name: str) -> str | None:
    raw = name.encode("latin-1")
    for key, value in scope.get("headers", ()):
        if key == raw:
            return bytes(value).decode("latin-1")
    return None


def _split_host(host: str) -> tuple[str, int | None]:
    host = host.strip().lower()
    if host.startswith("["):  # [::1]:8765
        end = host.find("]")
        name, rest = host[1:end], host[end + 1 :]
        port = rest[1:] if rest.startswith(":") else ""
    elif host.count(":") == 1:
        name, port = host.split(":")
    else:
        name, port = host, ""
    try:
        return name, int(port) if port else None
    except ValueError:
        return name, -1


class SecurityOptions(Protocol):
    """``SecurityPolicy.from_settings``가 읽는 보안 설정 모양(구조적 타이핑)."""

    @property
    def allowed_hosts(self) -> Iterable[str]: ...
    @property
    def allowed_origins(self) -> Iterable[str]: ...
    @property
    def max_request_bytes(self) -> int: ...
    @property
    def max_ws_message_bytes(self) -> int: ...
    @property
    def max_ws_subscriptions(self) -> int: ...


class BindSettings(Protocol):
    """``SecurityPolicy.from_settings``가 읽는 설정 모양(서버 설정·``HostSettings`` 모두 맞는다)."""

    @property
    def host(self) -> str: ...
    @property
    def port(self) -> int: ...
    @property
    def security(self) -> SecurityOptions: ...


def is_loopback_host(host: str) -> bool:
    """루프백 주소(127.0.0.0/8, ::1, localhost)면 참. `0.0.0.0`·`::`는 거짓."""
    name = host.strip("[]").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def resolve_token(
    explicit: str | None = None,
    configured: str | None = None,
    *,
    generate: Callable[[], str] = lambda: secrets.token_urlsafe(32),
) -> str:
    """로컬 API 토큰: 명시 값 > 설정 값 > 무작위(``generate``). 빈 문자열은 없는 것으로 본다."""
    if explicit:
        return explicit
    if configured:
        return configured
    return generate()


@dataclass(frozen=True)
class SecurityPolicy:
    """요청 검사 규칙. ``for_bind`` 또는 ``from_settings``로 만든다."""

    token: str
    port: int
    host_names: frozenset[str]
    allowed_hosts: frozenset[str]
    allowed_origins: frozenset[str]
    max_request_bytes: int
    max_ws_message_bytes: int
    max_ws_subscriptions: int = 256

    @classmethod
    def for_bind(
        cls,
        host: str,
        port: int,
        *,
        token: str,
        allowed_hosts: Iterable[str] = (),
        allowed_origins: Iterable[str] = (),
        max_request_bytes: int = 1024 * 1024,
        max_ws_message_bytes: int = 1024 * 1024,
        max_ws_subscriptions: int = 256,
    ) -> SecurityPolicy:
        """바인딩 주소·포트와 허용 목록으로 만든다(포트 0 = 어떤 포트든 루프백 이름이면 허용)."""
        names = set(LOOPBACK_HOSTS)
        if host not in ("0.0.0.0", "::", ""):
            names.add(host.strip("[]").lower())
        return cls(
            token=token,
            port=port,
            host_names=frozenset(names),
            allowed_hosts=frozenset(h.lower() for h in allowed_hosts),
            allowed_origins=frozenset(o.rstrip("/").lower() for o in allowed_origins),
            max_request_bytes=max_request_bytes,
            max_ws_message_bytes=max_ws_message_bytes,
            max_ws_subscriptions=max_ws_subscriptions,
        )

    @classmethod
    def from_settings(cls, settings: BindSettings, token: str) -> SecurityPolicy:
        """``host``·``port``·``security.{allowed_hosts, allowed_origins, max_*}``가 있는 설정."""
        s = settings.security
        return cls.for_bind(
            settings.host,
            settings.port,
            token=token,
            allowed_hosts=s.allowed_hosts,
            allowed_origins=s.allowed_origins,
            max_request_bytes=s.max_request_bytes,
            max_ws_message_bytes=s.max_ws_message_bytes,
            max_ws_subscriptions=s.max_ws_subscriptions,
        )

    def host_ok(self, host: str | None) -> bool:
        if not host:
            return False
        value = host.strip().lower()
        if value in self.allowed_hosts:
            return True
        name, port = _split_host(value)
        if name in self.allowed_hosts:
            return True
        if name not in self.host_names:
            return False
        return self.port == 0 or (port if port is not None else 80) == self.port

    def origin_ok(self, origin: str | None, host: str | None) -> bool:
        if origin is None:
            return True  # 브라우저가 아닌 클라이언트(CLI·curl). 변경 요청은 토큰이 따로 막는다.
        value = origin.rstrip("/").lower()
        if value in self.allowed_origins:
            return True
        if not host:
            return False
        h = host.strip().lower()
        return value in (f"http://{h}", f"https://{h}")

    def cors_origin(self, origin: str | None) -> str | None:
        """CORS를 허용할 출처(설정에 명시된 것만). 같은 출처 요청에는 CORS 헤더가 필요 없다."""
        if origin is None:
            return None
        return origin if origin.rstrip("/").lower() in self.allowed_origins else None

    def token_ok(self, presented: str | None) -> bool:
        if not presented:
            return False
        return hmac.compare_digest(presented.encode("utf-8"), self.token.encode("utf-8"))


def error_body(
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    fix: Mapping[str, Any] | None = None,
) -> bytes:
    """오류 본문 바이트(`{"error": {"code", "message", "details"[, "fix"]}}`, UTF-8).

    `fix`(해결 버튼)는 주었을 때만 넣는다(없으면 이전 본문과 같은 모양).
    """
    error: dict[str, Any] = {"code": code, "message": message, "details": dict(details or {})}
    if fix is not None:
        error["fix"] = dict(fix)
    return json.dumps({"error": error}, ensure_ascii=False).encode("utf-8")


async def send_error(
    send: Send,
    code: str,
    message: str,
    *,
    error_status: Mapping[str, int] = DEFAULT_ERROR_STATUS,
) -> None:
    """ASGI로 오류 응답을 보낸다(보안 헤더·`cache-control: no-store` 포함)."""
    status = error_status.get(code, 400)
    body = error_body(code, message)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
                *SECURITY_HEADERS,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class SecurityMiddleware:
    """HTTP 요청의 Host·Origin·토큰·크기 검사와 보안 헤더, 쿼리 없는 접근 로그.

    WebSocket은 여기서 막지 않는다 — 엔드포인트가 연결을 받은 뒤 검사해 close 코드
    (`WS_CLOSE_FORBIDDEN`·`WS_CLOSE_UNAUTHORIZED`)로 닫는다(클라이언트가 이유를 알 수 있게).

    Args:
        app: 감쌀 ASGI 앱.
        policy: 검사 규칙.
        api_prefix: API 접두(이 아래 응답에 `cache-control: no-store`,
            `<접두>/bootstrap` 출처 검사).
        error_status: 오류 코드 → HTTP 상태.
        access_logger: 접근 로그 로거(쿼리 문자열은 남기지 않는다).
    """

    def __init__(
        self,
        app: ASGIApp,
        policy: SecurityPolicy,
        *,
        api_prefix: str,
        error_status: Mapping[str, int] = DEFAULT_ERROR_STATUS,
        access_logger: logging.Logger | None = None,
    ) -> None:
        self.app = app
        self.policy = policy
        self.api_prefix = api_prefix
        self.error_status = error_status
        self._access = access_logger or _default_access

    async def _error(self, send: Send, code: str, message: str) -> None:
        await send_error(send, code, message, error_status=self.error_status)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        status_box: list[int] = [0]
        cors = self.policy.cors_origin(_header(scope, "origin"))

        async def send_wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_box[0] = int(message["status"])
                headers = list(message.get("headers", ()))
                present = {bytes(k).lower() for k, _ in headers}
                headers += [(k, v) for k, v in SECURITY_HEADERS if k not in present]
                if cors is not None:
                    headers += [
                        (b"access-control-allow-origin", cors.encode("latin-1")),
                        (b"access-control-expose-headers", CORS_EXPOSE_HEADERS.encode()),
                        (b"vary", b"Origin"),
                    ]
                path = scope.get("path", "")
                if path.startswith(self.api_prefix) and b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        try:
            await self._handle(scope, receive, send_wrapped)
        finally:
            # 쿼리 문자열은 남기지 않는다(토큰이 쿼리로 올 수 있다).
            self._access.info(
                "%s %s %d %.1fms",
                scope.get("method", ""),
                scope.get("path", ""),
                status_box[0],
                (time.monotonic() - started) * 1000,
            )

    async def _handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        policy = self.policy
        host = _header(scope, "host")
        if not policy.host_ok(host):
            await self._error(send, FORBIDDEN, "허용되지 않은 Host입니다")
            return
        method = str(scope.get("method", "GET")).upper()
        origin = _header(scope, "origin")
        cors = policy.cors_origin(origin)
        if method == "OPTIONS" and _header(scope, "access-control-request-method") is not None:
            await self._preflight(send, allowed=cors is not None)
            return
        path = str(scope.get("path", ""))
        guarded_read = path == f"{self.api_prefix}/bootstrap"
        if (method in UNSAFE_METHODS or guarded_read) and not policy.origin_ok(origin, host):
            await self._error(send, FORBIDDEN, "같은 출처 요청만 허용합니다")
            return
        if guarded_read and _header(scope, "sec-fetch-site") == "cross-site" and cors is None:
            await self._error(send, FORBIDDEN, "같은 출처 요청만 허용합니다")
            return
        if method in UNSAFE_METHODS and not policy.token_ok(_header(scope, TOKEN_HEADER)):
            await self._error(send, UNAUTHORIZED, "토큰이 없거나 맞지 않습니다")
            return
        if method in UNSAFE_METHODS or _header(scope, "content-length") is not None:
            await self._with_limited_body(scope, receive, send)
            return
        await self.app(scope, receive, send)

    async def _preflight(self, send: Send, *, allowed: bool) -> None:
        """CORS preflight. 허용 출처면 204 + 허용 메서드·헤더(출처 헤더는 `send`가 붙인다)."""
        if not allowed:
            await self._error(send, FORBIDDEN, "허용되지 않은 출처입니다")
            return
        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-methods", CORS_ALLOW_METHODS.encode()),
                    (b"access-control-allow-headers", CORS_ALLOW_HEADERS.encode()),
                    (b"access-control-max-age", CORS_MAX_AGE.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    async def _with_limited_body(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self.policy.max_request_bytes
        declared = _header(scope, "content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await self._error(send, PAYLOAD_TOO_LARGE, "요청이 너무 큽니다")
                    return
            except ValueError:
                await self._error(send, BAD_REQUEST, "Content-Length가 잘못됐습니다")
                return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = bytes(message.get("body", b""))
            size += len(body)
            if size > limit:
                await self._error(send, PAYLOAD_TOO_LARGE, "요청이 너무 큽니다")
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


__all__ = [
    "BAD_REQUEST",
    "CORS_ALLOW_HEADERS",
    "CORS_ALLOW_METHODS",
    "CORS_EXPOSE_HEADERS",
    "DEFAULT_ERROR_STATUS",
    "FORBIDDEN",
    "INTERNAL",
    "LOOPBACK_HOSTS",
    "PAYLOAD_TOO_LARGE",
    "SECURITY_HEADERS",
    "TOKEN_HEADER",
    "TOKEN_QUERY",
    "UNAUTHORIZED",
    "UNSAFE_METHODS",
    "WS_CLOSE_FORBIDDEN",
    "WS_CLOSE_UNAUTHORIZED",
    "BindSettings",
    "SecurityMiddleware",
    "SecurityOptions",
    "SecurityPolicy",
    "error_body",
    "is_loopback_host",
    "resolve_token",
    "send_error",
]
