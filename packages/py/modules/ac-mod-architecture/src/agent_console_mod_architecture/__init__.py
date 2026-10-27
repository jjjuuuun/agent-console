"""agent-console-mod-architecture: 구조도 기능 모듈(design §5.5R.3, 결정 K-1).

패키지 기본 → X23 플러그인 → 사용자 설정(워크스페이스 ``architecture`` 섹션) 프로필을 합쳐
목록·상세·검사·단독 투영 REST와 포트 ``architecture.catalog``로 낸다. 로그·실행을 모른다.

공개 API:
    - 모듈: ``module``(entry point ``mod-architecture``), ``ArchitectureModule``, ``MODULE_ID``,
      ``WEB_ROLES``
    - 서비스: ``ArchitectureCatalogService``(``state``·``catalog``·``operators``·``pick``·
      ``profile_list``·``profile_detail``·``check``·``project``·``project_request``·
      ``ensure_within``·``warnings``), ``CatalogState``, ``parse_user_settings``, ``section_of``
    - 포트: ``ARCHITECTURE_CATALOG``·``WORKSPACE_SETTINGS``·``SERVER_WARNINGS``,
      ``PROFILE_CHECKS``(선택 여러 제공자, X32), ``ArchitectureCatalog``·``ProfileCheck``(포트 모양)
    - 오류: ``ProfileNotFoundError``(404 ``architecture.profile_not_found``),
      ``ScopeTooLargeError``(422 ``architecture.scope_too_large``), ``ERROR_MAP``
    - 설정: ``ArchitectureModuleSettings``(``modules.options.mod-architecture``)
    - 라우터: ``build_router``
    - 플러그인 로더: ``plugins.load_plugins``(entry point ``agent_console.host_plugin_loaders``)
    - 테스트·단독 실행: ``testing``(``local_settings_module``·``static_settings_module``),
      ``standalone.main``
"""

from __future__ import annotations

from .catalog import (
    INLINE_PROFILE_ID,
    SECTION_KEY,
    SETTINGS_INVALID,
    ArchitectureCatalogService,
    CatalogState,
    parse_user_settings,
    section_of,
)
from .errors import ERROR_MAP, ProfileNotFoundError, ScopeTooLargeError
from .module import MODULE_ID, WEB_ROLES, ArchitectureModule, module
from .ports import (
    ARCHITECTURE_CATALOG,
    PROFILE_CHECKS,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
    ArchitectureCatalog,
    ProfileCheck,
)
from .routes import build_router
from .settings import ArchitectureModuleSettings

__all__ = [
    "ARCHITECTURE_CATALOG",
    "ERROR_MAP",
    "INLINE_PROFILE_ID",
    "MODULE_ID",
    "PROFILE_CHECKS",
    "SECTION_KEY",
    "SERVER_WARNINGS",
    "SETTINGS_INVALID",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "ArchitectureCatalog",
    "ArchitectureCatalogService",
    "ArchitectureModule",
    "ArchitectureModuleSettings",
    "CatalogState",
    "ProfileCheck",
    "ProfileNotFoundError",
    "ScopeTooLargeError",
    "build_router",
    "module",
    "parse_user_settings",
    "section_of",
]
