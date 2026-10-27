"""agent-console-server: 조립 앱.

설정(`agent-console.yaml` + 환경변수) → 모듈 조립(`agent_console_modkit.assemble`, 설치자 설정
`modules`·`--enable-module`/`--disable-module`, 플러그인 레지스트리는 호스트가 한 번 로드) →
기능·연동 모듈(entry point `agent_console.server_modules` — 서버는 모듈 이름을 모른다, 3R.16) →
호스트 경로
(`/health`·`/bootstrap`·`/modules`·`/server-info`) +
FastAPI REST(`/api/v1`)·WebSocket(`/ws`), CORS. 웹은 별도 프로세스이거나,
`web.serve_static`(선택, 기본 꺼짐)을 켜면 같은 서버가 서빙한다(단일 실행, §2R.13a).
비즈니스 로직은 각 패키지에 있다. 설계: specs/agent-console/design.md §5.2, §5.3, §6.3, §9.1, §R7,
§R9.5.
"""

from agent_console_contracts import WS_CLOSE_FORBIDDEN, WS_CLOSE_UNAUTHORIZED
from agent_console_modkit.host import (
    SENSITIVE_QUERY_PARAMS,
    TOKEN_HEADER,
    TOKEN_QUERY,
    QueryRedactingFilter,
    SecurityPolicy,
    install_log_redaction,
)

from ._app import (
    WS_PATH,
    create_app,
    flag_overrides,
    installed_modules,
    main,
    merge_origins,
    serve,
    server_version,
)
from ._config import (
    CONFIG_FILENAME,
    ENV_PREFIX,
    SETTINGS_COMPAT_CONTEXT,
    SETTINGS_REMOVED_KEY,
    ConfigError,
    RemovedKey,
    ServerSettings,
    is_loopback_host,
    load_settings,
    settings_compat,
)
from ._launch import Opener, build_opener
from ._modules import apply_module_flags, module_info
from ._openapi import build_openapi
from ._restkit import API_PREFIX

__all__ = [
    "API_PREFIX",
    "CONFIG_FILENAME",
    "ENV_PREFIX",
    "SENSITIVE_QUERY_PARAMS",
    "SETTINGS_COMPAT_CONTEXT",
    "SETTINGS_REMOVED_KEY",
    "TOKEN_HEADER",
    "TOKEN_QUERY",
    "WS_CLOSE_FORBIDDEN",
    "WS_CLOSE_UNAUTHORIZED",
    "WS_PATH",
    "ConfigError",
    "Opener",
    "QueryRedactingFilter",
    "RemovedKey",
    "SecurityPolicy",
    "ServerSettings",
    "apply_module_flags",
    "build_openapi",
    "build_opener",
    "create_app",
    "flag_overrides",
    "install_log_redaction",
    "installed_modules",
    "is_loopback_host",
    "load_settings",
    "main",
    "merge_origins",
    "module_info",
    "serve",
    "server_version",
    "settings_compat",
]
