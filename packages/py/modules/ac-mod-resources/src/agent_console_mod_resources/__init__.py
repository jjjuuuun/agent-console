"""agent-console-mod-resources: 리소스 기능 모듈(design §3R.1.3, R12·R13.1).

리소스 라이브러리 경로(CRUD·본문·여러 파일)와 리소스 종류·병합 전략 목록을 서버에 꽂고, 다른
모듈이 쓰는 리소스 조회(``resources.lookup``)·종류 레지스트리(``resources.types``) 포트를 낸다.

공개 API:
    - ``module``(``ResourcesModule``): entry point ``agent_console.server_modules``의
      ``mod-resources``.
    - 포트(``ports``): ``DEFINITIONS_STORE``(필수)·``DEFINITION_USAGES``(선택)·
      ``RESOURCES_LOOKUP``·``RESOURCE_TYPES``(제공), 프로토콜 ``DefinitionUsages``·
      ``ResourceStore``.
    - HTTP 없이 쓰는 부품: ``ResourceService``, ``StoreResources``(저장소 위 ``ResourceLookup``),
      ``resource_types_of``, ``resource_issues``·``merge_strategies``.
    - ``build_router``: FastAPI 라우터(접두 없음). ``ERROR_MAP``: 모듈 오류 맵.
    - ``ResourceModuleSettings``: 설치자 설정(``modules.options.mod-resources``).
"""

from __future__ import annotations

from .errors import ERROR_MAP, NOT_MULTI_FILE, RESERVED_FILE_NAME, ResourceRejectedError
from .lookup import StoreResources, resource_types_of
from .module import MODULE_ID, WEB_ROLES, ResourcesModule, module
from .ports import (
    DEFINITION_USAGES,
    DEFINITIONS_STORE,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    DefinitionUsages,
    ResourceStore,
)
from .routes import build_router
from .service import ResourceService, merge_strategies, resource_document_path, resource_issues
from .settings import DEFAULT_CONTENT_FILES, DEFAULT_RESERVED_FILE_NAMES, ResourceModuleSettings

__all__ = [
    "DEFAULT_CONTENT_FILES",
    "DEFAULT_RESERVED_FILE_NAMES",
    "DEFINITIONS_STORE",
    "DEFINITION_USAGES",
    "ERROR_MAP",
    "MODULE_ID",
    "NOT_MULTI_FILE",
    "RESERVED_FILE_NAME",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "WEB_ROLES",
    "DefinitionUsages",
    "ResourceModuleSettings",
    "ResourceRejectedError",
    "ResourceService",
    "ResourceStore",
    "ResourcesModule",
    "StoreResources",
    "build_router",
    "merge_strategies",
    "module",
    "resource_document_path",
    "resource_issues",
    "resource_types_of",
]
