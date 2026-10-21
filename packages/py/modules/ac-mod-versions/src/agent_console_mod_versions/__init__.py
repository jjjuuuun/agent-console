"""agent-console-mod-versions: 버전 기능 모듈(design §3R.1.3, R2.5, D3·E-16).

정의 버전 목록·비교·되돌리기 경로(컬렉션 표는 설정 데이터)와 보존 개수(``max_per_definition``)를
서버에 꽂는다. 버전 기록 자체는 정의 저장소(``ac-store``)가 한다.

공개 API:
    - ``module``(``VersionsModule``): entry point ``agent_console.server_modules``의
      ``mod-versions``.
    - ``VersionService``·``RestoreRejectedError``: HTTP 없이 쓰는 비교·되돌리기·보존 로직.
    - ``build_router``: FastAPI 라우터(접두 없음).
    - ``VersionModuleSettings``·``VersionedCollectionSetting``·``DEFAULT_COLLECTIONS``: 설치자 설정
      (``modules.options.mod-versions``).
    - 포트·토픽: ``DEFINITIONS_STORE``(필수)·``DEFINITION_CHECKS``(선택, multi)·``SECRET_RULES``
      (선택)·``DEFINITIONS_SAVED``(구독), 프로토콜 ``VersionStore``·``DefinitionCheck``·
      ``SavedDefinition``.
    - ``testing.local_definitions_module``: 단독 실행·테스트용 ``definitions.store`` 제공 모듈.
"""

from __future__ import annotations

from .errors import ERROR_MAP
from .module import MODULE_ID, WEB_ROLES, VersionsModule, module
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_SAVED,
    DEFINITIONS_STORE,
    SECRET_RULES,
    DefinitionCheck,
    SavedDefinition,
    SecretRulesReader,
    VersionStore,
)
from .routes import build_router
from .service import RESTORE_MESSAGE, SECRET_MASK, RestoreRejectedError, VersionService
from .settings import (
    DEFAULT_COLLECTIONS,
    DEFAULT_SECRET_ISSUE_CODES,
    VersionedCollectionSetting,
    VersionModuleSettings,
)

__all__ = [
    "DEFAULT_COLLECTIONS",
    "DEFAULT_SECRET_ISSUE_CODES",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "ERROR_MAP",
    "MODULE_ID",
    "RESTORE_MESSAGE",
    "SECRET_MASK",
    "SECRET_RULES",
    "WEB_ROLES",
    "DefinitionCheck",
    "RestoreRejectedError",
    "SavedDefinition",
    "SecretRulesReader",
    "VersionModuleSettings",
    "VersionService",
    "VersionStore",
    "VersionedCollectionSetting",
    "VersionsModule",
    "build_router",
    "module",
]
