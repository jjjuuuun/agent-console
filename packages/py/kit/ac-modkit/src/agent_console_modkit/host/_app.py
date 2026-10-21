"""조립 결과(``Assembly``) → FastAPI 앱. 기능 로직 없음(design §3R.1.3 호스트).

붙이는 것: 켜진 모듈의 라우터(API 접두 아래), ``/health``, ``/modules``,
``/modules/{id}/options``(옵션 읽기 전용), ``/ws``(모듈 WS 토픽 합친 것),
모듈 ``error_map``의 오류 처리기와 ``FeatureUnavailableError``(409) 처리기, 보안
미들웨어, lifespan(``Assembly.start``/``stop``). 통합 서버는 같은 부품을 계약 모델로 붙인다.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response

from agent_console_modkit._assemble import Assembly
from agent_console_modkit._errors import (
    FEATURE_UNAVAILABLE,
    ErrorMapping,
    FeatureUnavailableError,
    error_reply,
)

from ._health import build_health_router
from ._modules import build_modules_router, default_modules_payload
from ._options import build_module_options_router, default_module_options_payload
from ._security import DEFAULT_ERROR_STATUS, SecurityMiddleware, SecurityPolicy, error_body
from ._ws import WsCodec, websocket_endpoint


def install_error_map(
    app: FastAPI,
    error_map: Mapping[type[Exception], ErrorMapping],
    *,
    error_status: Mapping[str, int] = DEFAULT_ERROR_STATUS,
    redact: Callable[[str], str] = lambda text: text,
) -> None:
    """예외 형식 → 오류 코드(또는 ``ErrorMapper``) 표를 FastAPI 예외 처리기로 붙인다.

    본문은 ``{"error": {"code", "message": redact(메시지), "details"[, "fix"]}}``, 상태는
    ``error_status[code]``(모르면 400). 코드 문자열이면 메시지 = ``str(exc)``·``details = {}``,
    ``ErrorMapper``면 그 결과(``ErrorReply``)의 값과 헤더를 쓴다.
    """
    for exc_type, mapping in error_map.items():

        def handler(_: Request, exc: Exception, mapping: ErrorMapping = mapping) -> Response:
            reply = error_reply(mapping, exc)
            message = reply.message if reply.message is not None else str(exc)
            return Response(
                content=error_body(reply.code, redact(message), reply.details or None, reply.fix),
                status_code=error_status.get(reply.code, 400),
                media_type="application/json",
                headers={**reply.headers, "cache-control": "no-store"},
            )

        app.add_exception_handler(exc_type, handler)


ROUTE_FIRST_KINDS: tuple[str, ...] = ("link",)
"""라우터를 먼저 붙일 모듈 종류. 연동 모듈은 기능 자원의 하위·고정 경로(예: ``/runs/handoffs``)를
더하므로 기능 모듈의 매개변수 경로(``/runs/{run_id}``)보다 먼저 맞춘다."""


def include_routers(
    app: FastAPI,
    assembly: Assembly,
    *,
    prefix: str = "",
    first_kinds: Iterable[str] = ROUTE_FIRST_KINDS,
) -> None:
    """켜진 모듈의 라우터를 ``prefix`` 아래 붙인다(``first_kinds`` 종류 모듈 먼저, 그다음 조립
    순서)."""
    for router in assembly.routers(first_kinds=first_kinds):
        app.include_router(router, prefix=prefix)


def install_feature_unavailable(
    app: FastAPI,
    *,
    error_status: Mapping[str, int] = DEFAULT_ERROR_STATUS,
    redact: Callable[[str], str] = lambda text: text,
) -> None:
    """``FeatureUnavailableError`` → ``feature_unavailable``(기본 409).

    본문 ``details = {module, port}``.
    """

    def handler(_: Request, exc: Exception) -> Response:
        details = exc.details if isinstance(exc, FeatureUnavailableError) else {}
        return Response(
            content=error_body(FEATURE_UNAVAILABLE, redact(str(exc)), details),
            status_code=error_status.get(FEATURE_UNAVAILABLE, 409),
            media_type="application/json",
            headers={"cache-control": "no-store"},
        )

    app.add_exception_handler(FeatureUnavailableError, handler)


def create_host_app(
    assembly: Assembly,
    *,
    policy: SecurityPolicy,
    title: str = "Agent Console module host",
    version: str = "0.0.0",
    api_prefix: str = "/api/v1",
    ws_path: str = "/ws",
    codec: WsCodec | None = None,
    health_payload: Callable[[], Any] | None = None,
    modules_payload: Callable[[], Any] | None = None,
    options_payload: Callable[[str], Any | None] | None = None,
    error_status: Mapping[str, int] = DEFAULT_ERROR_STATUS,
    redact: Callable[[str], str] = lambda text: text,
    access_logger: logging.Logger | None = None,
) -> FastAPI:
    """켜진 모듈을 붙인 FastAPI 앱을 만든다.

    Args:
        assembly: ``assemble`` 결과.
        policy: 보안 규칙(``SecurityPolicy.for_bind``·``from_settings``).
        title: OpenAPI 제목.
        version: OpenAPI 버전.
        api_prefix: 모듈 라우터·``/health`` 접두.
        ws_path: WS 경로.
        codec: WS 메시지 형식(기본 ``JsonWsCodec``).
        health_payload: ``/health`` 본문 함수. 기본 ``{"status": "ok", "modules": {id: 상태}}``.
            모듈 시작이 끝나기 전·종료 중에는 ``503 not_ready``다(``Assembly.running``).
        modules_payload: ``/modules`` 본문 함수. 기본 ``ModuleReport.to_dict()`` 목록.
        options_payload: ``/modules/{id}/options`` 본문 함수(모르는 id면 None → 404). 기본
            ``default_module_options_payload(assembly)``(스키마 표시 비밀만 가림).
        error_status: 오류 코드 → HTTP 상태.
        redact: 오류 메시지 가림 함수.
        access_logger: 접근 로그 로거.

    Returns:
        FastAPI 앱. ``app.state.assembly``·``app.state.policy``가 들어 있다.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await assembly.start()
        try:
            yield
        finally:
            await assembly.stop()

    app = FastAPI(
        title=title,
        version=version,
        lifespan=lifespan,
        docs_url=f"{api_prefix}/docs",
        redoc_url=None,
        openapi_url=f"{api_prefix}/openapi.json",
    )
    app.state.assembly = assembly
    app.state.policy = policy

    def default_health() -> dict[str, Any]:
        return {"status": "ok", "modules": {r.id: r.state.value for r in assembly.report}}

    app.include_router(
        build_health_router(
            prefix=api_prefix,
            payload=health_payload or default_health,
            ready=lambda: assembly.running,
            error_status=error_status,
        )
    )
    app.include_router(
        build_modules_router(
            prefix=api_prefix, payload=modules_payload or default_modules_payload(assembly)
        )
    )
    app.include_router(
        build_module_options_router(
            prefix=api_prefix,
            payload=options_payload or default_module_options_payload(assembly),
            error_status=error_status,
        )
    )
    include_routers(app, assembly, prefix=api_prefix)
    install_feature_unavailable(app, error_status=error_status, redact=redact)
    install_error_map(app, assembly.error_map(), error_status=error_status, redact=redact)
    app.add_api_websocket_route(
        ws_path, websocket_endpoint(assembly.ws_topics(), policy, codec=codec)
    )
    app.add_middleware(
        SecurityMiddleware,
        policy=policy,
        api_prefix=api_prefix,
        error_status=error_status,
        access_logger=access_logger,
    )
    return app


__all__ = [
    "ROUTE_FIRST_KINDS",
    "create_host_app",
    "include_routers",
    "install_error_map",
    "install_feature_unavailable",
]
