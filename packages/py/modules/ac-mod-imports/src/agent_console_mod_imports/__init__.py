"""agent-console-mod-imports: 가져오기 기능 모듈(design §3R.1.3, §R11).

``ac-imports``(외부 설정 복사 라이브러리)를 서버에 꽂는다. 경로 ``GET /resources/import/sources``,
``POST /resources/import/preview``, ``POST /resources/import``. 원본은 읽기만 한다.

공개 API:
    - ``module``(``ImportsModule``): entry point ``agent_console.server_modules``의 ``mod-imports``.
    - ``build_router``: FastAPI 라우터(접두 없음).
    - ``ImportModuleSettings``: 설치자 설정(``modules.options.mod-imports``). 출처는 프로젝트
      폴더 안뿐이다(사용자 ``~/.claude`` 없음, 5.7R.30b).
    - ``import_factories_of``·``import_error_reply``: 출처 공장 레지스트리 찾기·오류 변환.
    - 포트: ``DEFINITIONS_STORE``(필수)·``SECRET_RULES``·``PROJECT_FOLDERS``·``DEFINITIONS_SPACES``
      (선택, 5.7R.33k — 출처 = 등록 프로젝트 폴더, 저장 위치 = 그 프로젝트 공간 또는 공용).
    - ``ProjectImports``·``ImportProjectError``·``ImportTarget``: 요청 ``project``·``target`` →
      가져오기 서비스(서버 없이도 쓴다).
    - ``testing.local_definitions_module``: 단독 실행·테스트용 ``definitions.store`` 제공 모듈.
"""

from __future__ import annotations

from .module import (
    MODULE_ID,
    WEB_ROLES,
    ImportsModule,
    import_error_reply,
    import_factories_of,
    module,
)
from .ports import (
    DEFINITIONS_SPACES,
    DEFINITIONS_STORE,
    PROJECT_FOLDERS,
    SECRET_RULES,
    SecretRulesReader,
)
from .projects import ImportProjectError, ImportScope, ImportTarget, ProjectImports
from .routes import build_router
from .settings import HOME_REMOVED_REASON, ImportModuleSettings

__all__ = [
    "DEFINITIONS_SPACES",
    "DEFINITIONS_STORE",
    "HOME_REMOVED_REASON",
    "MODULE_ID",
    "PROJECT_FOLDERS",
    "SECRET_RULES",
    "WEB_ROLES",
    "ImportModuleSettings",
    "ImportProjectError",
    "ImportScope",
    "ImportTarget",
    "ImportsModule",
    "ProjectImports",
    "SecretRulesReader",
    "build_router",
    "import_error_reply",
    "import_factories_of",
    "module",
]
