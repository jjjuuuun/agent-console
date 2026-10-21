"""agent-console-mod-exports: 내보내기 기능 모듈(design §3R.1.3, §2R.7).

``ac-exports``(형식 플러그인·보관 파일·허용 폴더 쓰기 라이브러리)를 서버에 꽂는다. 경로
``GET /exporters``, ``POST /exports/plan``·``/exports/archive``·``/exports/write``,
``GET /exports/roots``(토큰 필수).

공개 API:
    - ``module``(``ExportsModule``): entry point ``agent_console.server_modules``의 ``mod-exports``.
    - ``LookupExportCatalog``: 정의 읽기 포트 → ``ExportCatalog`` 어댑터.
    - ``build_router``·``require_token``·``TokenRequiredError``: FastAPI 라우터(접두 없음).
    - ``ExportModuleSettings``·``ExportRootSetting``·``protected_paths``: 설치자 설정
      (``modules.options.mod-exports``).
    - ``ERROR_MAP``·``export_error_reply``·``exporter_factories_of``.
    - 포트: ``DEFINITIONS_LOOKUP``(필수)·``EXPORT_DEPENDENCIES``·``SECRET_RULES``(선택), 프로토콜
      ``DefinitionLookup``·``ExportDependencies``.
    - ``testing.local_definitions_module``: 단독 실행·테스트용 ``definitions.lookup`` 제공 모듈.
"""

from __future__ import annotations

from .catalog import LookupExportCatalog
from .module import (
    ERROR_MAP,
    HOME_ENV_NAMES,
    MODULE_ID,
    WEB_ROLES,
    ExportsModule,
    export_error_reply,
    exporter_factories_of,
    module,
    protected_paths,
)
from .ports import (
    DEFINITIONS_LOOKUP,
    EXPORT_DEPENDENCIES,
    SECRET_RULES,
    DefinitionLookup,
    ExportDependencies,
    SecretRulesReader,
)
from .routes import ZIP_MEDIA_TYPE, TokenRequiredError, build_router, require_token
from .settings import ExportModuleSettings, ExportRootSetting

__all__ = [
    "DEFINITIONS_LOOKUP",
    "ERROR_MAP",
    "EXPORT_DEPENDENCIES",
    "HOME_ENV_NAMES",
    "MODULE_ID",
    "SECRET_RULES",
    "WEB_ROLES",
    "ZIP_MEDIA_TYPE",
    "DefinitionLookup",
    "ExportDependencies",
    "ExportModuleSettings",
    "ExportRootSetting",
    "ExportsModule",
    "LookupExportCatalog",
    "SecretRulesReader",
    "TokenRequiredError",
    "build_router",
    "export_error_reply",
    "exporter_factories_of",
    "module",
    "protected_paths",
    "require_token",
]
