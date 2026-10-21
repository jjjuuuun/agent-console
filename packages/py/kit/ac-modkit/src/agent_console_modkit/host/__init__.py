"""modkit 호스트(extra ``[host]``): 보안 미들웨어·토큰·``/health``·WS 다중화·조립 결과 → FastAPI.

기능 로직은 없다. 통합 서버(``apps/server``)와 단독 실행(``standalone``)이 같은 코드를 쓴다.

공개 API:
    - ``SecurityPolicy``(``for_bind``·``from_settings``) / ``SecurityMiddleware`` /
      ``resolve_token`` / ``is_loopback_host`` / ``send_error`` / ``error_body`` /
      ``DEFAULT_ERROR_STATUS``
    - ``QueryRedactingFilter`` / ``install_log_redaction``: 로그에서 토큰·비밀성 쿼리 값 가리기
    - ``build_health_router``: ``GET <prefix>/health``
    - ``build_modules_router`` / ``default_modules_payload``: ``GET <prefix>/modules``
    - ``build_module_options_router`` / ``default_module_options_payload`` /
      ``options_yaml_snippet`` / ``OPTIONS_KEY_PATH`` / ``MASKED_LINE_NOTE``:
      ``GET <prefix>/modules/{id}/options``
      (모듈 옵션 읽기 전용 보기 + 설정 파일용 YAML 조각, 쓰기 없음)
    - ``websocket_endpoint`` / ``WsCodec`` / ``JsonWsCodec`` / ``WsCommand`` / ``WsInvalid``
    - ``create_host_app`` / ``install_error_map`` / ``install_feature_unavailable`` /
      ``include_routers``·``ROUTE_FIRST_KINDS``(모듈 라우터 붙이기 — 연동 모듈 먼저)
    - ``HostSettings`` / ``load_host_settings`` / ``read_config_file``
    - HTTP 도우미: ``IfMatchHeader`` / ``if_match_version`` / ``etag`` / ``json_with_etag`` /
      ``attachment_response``(버전 있는 자원·본문 파일 응답) / ``with_issues``·``ISSUES_HEADER``
      (성공 응답의 경고 이슈 헤더)
"""

from __future__ import annotations

from ._app import (
    ROUTE_FIRST_KINDS,
    create_host_app,
    include_routers,
    install_error_map,
    install_feature_unavailable,
)
from ._health import NOT_READY_MESSAGE, build_health_router
from ._http import (
    BINARY_FILE_MEDIA_TYPE,
    ISSUES_HEADER,
    TEXT_FILE_MEDIA_TYPE,
    TEXT_LIKE_MEDIA_TYPES,
    IfMatchHeader,
    attachment_response,
    etag,
    if_match_version,
    json_with_etag,
    with_issues,
)
from ._logging import (
    REDACTED,
    SENSITIVE_QUERY_PARAMS,
    UVICORN_LOGGERS,
    QueryRedactingFilter,
    install_log_redaction,
)
from ._modules import build_modules_router, default_modules_payload
from ._options import (
    MASKED_LINE_NOTE,
    OPTIONS_KEY_PATH,
    build_module_options_router,
    default_module_options_payload,
    options_yaml_snippet,
)
from ._security import (
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    CORS_EXPOSE_HEADERS,
    DEFAULT_ERROR_STATUS,
    LOOPBACK_HOSTS,
    SECURITY_HEADERS,
    TOKEN_HEADER,
    TOKEN_QUERY,
    UNSAFE_METHODS,
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_UNAUTHORIZED,
    BindSettings,
    SecurityMiddleware,
    SecurityOptions,
    SecurityPolicy,
    error_body,
    is_loopback_host,
    resolve_token,
    send_error,
)
from ._settings import HostSecuritySettings, HostSettings, load_host_settings, read_config_file
from ._ws import (
    JsonWsCodec,
    TopicsSource,
    WsCodec,
    WsCommand,
    WsConnection,
    WsInvalid,
    request_id_of,
    route_topic,
    websocket_endpoint,
)

__all__ = [
    "BINARY_FILE_MEDIA_TYPE",
    "CORS_ALLOW_HEADERS",
    "CORS_ALLOW_METHODS",
    "CORS_EXPOSE_HEADERS",
    "DEFAULT_ERROR_STATUS",
    "ISSUES_HEADER",
    "LOOPBACK_HOSTS",
    "MASKED_LINE_NOTE",
    "NOT_READY_MESSAGE",
    "OPTIONS_KEY_PATH",
    "REDACTED",
    "ROUTE_FIRST_KINDS",
    "SECURITY_HEADERS",
    "SENSITIVE_QUERY_PARAMS",
    "TEXT_FILE_MEDIA_TYPE",
    "TEXT_LIKE_MEDIA_TYPES",
    "TOKEN_HEADER",
    "TOKEN_QUERY",
    "UNSAFE_METHODS",
    "UVICORN_LOGGERS",
    "WS_CLOSE_FORBIDDEN",
    "WS_CLOSE_UNAUTHORIZED",
    "BindSettings",
    "HostSecuritySettings",
    "HostSettings",
    "IfMatchHeader",
    "JsonWsCodec",
    "QueryRedactingFilter",
    "SecurityMiddleware",
    "SecurityOptions",
    "SecurityPolicy",
    "TopicsSource",
    "WsCodec",
    "WsCommand",
    "WsConnection",
    "WsInvalid",
    "attachment_response",
    "build_health_router",
    "build_module_options_router",
    "build_modules_router",
    "create_host_app",
    "default_module_options_payload",
    "default_modules_payload",
    "error_body",
    "etag",
    "if_match_version",
    "include_routers",
    "install_error_map",
    "install_feature_unavailable",
    "install_log_redaction",
    "is_loopback_host",
    "json_with_etag",
    "load_host_settings",
    "options_yaml_snippet",
    "read_config_file",
    "request_id_of",
    "resolve_token",
    "route_topic",
    "send_error",
    "websocket_endpoint",
    "with_issues",
]
