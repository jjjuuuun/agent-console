"""agent-console-mod-usage: 사용량 기능 모듈(design §3R.1.3·§3R.5).

``ac-usage``(출처·수집·집계 라이브러리)를 서버에 꽂는다. 경로 ``GET /usage``(``parts`` 부분 조회),
``GET /usage/sources``. 실행 기록·저장소·워크스페이스 설정은 선택 포트로 받는다.

공개 API:
    - ``module``(``UsageModule``): entry point ``agent_console.server_modules``의 ``mod-usage``.
    - ``UsageReportService``·``parse_parts``·``local_timezone``: HTTP 없이 쓰는 보고 로직.
    - ``build_router``: FastAPI 라우터(접두 없음).
    - ``UsageModuleSettings``: 설치자 설정(``modules.options.mod-usage``).
    - ``agent_console_mod_usage.storage``: 관측값 저장소(``usage_observations``)·마이그레이션 계보.
    - 포트: ``USAGE_SERVICE``·``SERVER_WARNINGS``·``EVENT_QUERY``·``TOKEN_ROLLUPS``·
      ``USAGE_SOURCES``(multi)·``WORKSPACE_SETTINGS``, 프로토콜 ``TokenRollups``.
    - ``runtime_usage_sources``·``SOURCE_CONFLICT``: 런타임 출처 목록 → id 사전·겹침 경고.
    - ``resolve_command``: 연결 안내 조각에 넣을 ``agent-console`` 명령(주입된 PATH에서 절대 경로).
    - ``UsageSettingsCheck``(``DEFINITION_CHECKS``로 제공)·``usage_settings_of``: 공통 설정 저장 전
      출처 설정 검증(``usage.source_config_invalid``, 위치만·값 없음).
"""

from __future__ import annotations

from .checks import UsageSettingsCheck, usage_settings_of
from .module import (
    MODULE_ID,
    SOURCE_CONFLICT,
    WEB_ROLES,
    UsageModule,
    module,
    resolve_command,
    runtime_usage_sources,
    usage_sources_of,
)
from .ports import (
    DEFINITION_CHECKS,
    EVENT_QUERY,
    SERVER_WARNINGS,
    TOKEN_ROLLUPS,
    USAGE_SERVICE,
    USAGE_SOURCES,
    WORKSPACE_SETTINGS,
    DefinitionCheck,
    TokenRollups,
    WarningSource,
    WorkspaceSettingsReader,
)
from .routes import build_router
from .service import PART_TOKENS, PART_WINDOWS, UsageReportService, local_timezone, parse_parts
from .settings import UsageModuleSettings

__all__ = [
    "DEFINITION_CHECKS",
    "EVENT_QUERY",
    "MODULE_ID",
    "PART_TOKENS",
    "PART_WINDOWS",
    "SERVER_WARNINGS",
    "SOURCE_CONFLICT",
    "TOKEN_ROLLUPS",
    "USAGE_SERVICE",
    "USAGE_SOURCES",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "DefinitionCheck",
    "TokenRollups",
    "UsageModule",
    "UsageModuleSettings",
    "UsageReportService",
    "UsageSettingsCheck",
    "WarningSource",
    "WorkspaceSettingsReader",
    "build_router",
    "local_timezone",
    "module",
    "parse_parts",
    "resolve_command",
    "runtime_usage_sources",
    "usage_settings_of",
    "usage_sources_of",
]
