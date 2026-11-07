"""agent-console-mod-definitions: 정의 기능 모듈(design §3R.1.3, R1.2·R13.1).

에이전트·팀 구성·공통 설정의 저장소(워크스페이스 YAML + 버전 기록)와 CRUD 경로를 서버에 꽂고,
다른 모듈이 쓰는 포트(정의 저장소·읽기, 공통 설정, 비밀 의심 규칙)와 저장 알림 토픽을 낸다.

공개 API:
    - ``module``(``DefinitionsModule``): entry point ``agent_console.server_modules``의
      ``mod-definitions``.
    - 포트·토픽(``ports``): ``DEFINITIONS_STORE``·``DEFINITIONS_LOOKUP``·``WORKSPACE_SETTINGS``·
      ``SECRET_RULES``·``DEFINITION_CHECKS``(multi)·``SERVER_WARNINGS``(multi)·
      ``GRAPH_VALIDATION``·``GRAPH_ENTRY_LABELS``·``GRAPH_SESSION_SUMMARY``(세션 집계)·
      ``DEFINITIONS_SPACES``(선택, 공간 이름 → 저장소)·
      ``KIND_CONTRIBUTIONS``(선택 multi, 정의 종류 기여 X44)·
      ``DEFINITIONS_SAVED``(``SavedDefinition`` — ``space`` 포함).
    - HTTP 없이 쓰는 부품: ``build_store``(저장 알림·삭제 알림 붙은 파일 저장소),
      ``register_contributed_kinds``(종류 기여 → 라이브러리 저장소에 등록),
      ``WorkspaceState``(공통 설정·비밀 규칙 캐시), ``SecretRuleCheck``, ``PlainSecretScan``·
      ``scan_store``·``plain_secret_warnings``(평문 점검), ``DefinitionService``.
    - ``build_router``: FastAPI 라우터(접두 없음, ``service(space)`` 공장).
      ``ERROR_MAP``: 모듈 오류 맵.
    - ``DefinitionModuleSettings``: 설치자 설정(``modules.options.mod-definitions``).
"""

from __future__ import annotations

from .errors import ERROR_MAP, DefinitionRejectedError, IdMismatchError
from .module import MODULE_ID, VERSIONS_MEMORY, WEB_ROLES, DefinitionsModule, module
from .plain_scan import PlainSecretScan, plain_secret_warnings, scan_store
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    DEFINITIONS_SAVED,
    DEFINITIONS_SPACES,
    DEFINITIONS_STORE,
    GRAPH_ENTRY_LABELS,
    GRAPH_SESSION_SUMMARY,
    GRAPH_VALIDATION,
    KIND_CONTRIBUTIONS,
    SECRET_RULES,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
    DefinitionCheck,
    GraphEntryLabels,
    GraphSessionSummarySource,
    GraphValidationSource,
    SavedDefinition,
    SpaceGraphValidationSource,
)
from .routes import build_router
from .service import DefinitionService
from .settings import DEFAULT_PLAIN_SECRET_ISSUE_CODES, DefinitionModuleSettings
from .store import (
    DefinitionFileStore,
    LazyVersionRepository,
    build_store,
    definition_kinds,
    register_contributed_kinds,
)
from .workspace import (
    INVALID_RULE,
    SecretRuleCheck,
    WorkspaceState,
    build_rules,
    settings_rule_issues,
)

__all__ = [
    "DEFAULT_PLAIN_SECRET_ISSUE_CODES",
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_SPACES",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "ERROR_MAP",
    "GRAPH_ENTRY_LABELS",
    "GRAPH_SESSION_SUMMARY",
    "GRAPH_VALIDATION",
    "INVALID_RULE",
    "KIND_CONTRIBUTIONS",
    "MODULE_ID",
    "SECRET_RULES",
    "SERVER_WARNINGS",
    "VERSIONS_MEMORY",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "DefinitionCheck",
    "DefinitionFileStore",
    "DefinitionModuleSettings",
    "DefinitionRejectedError",
    "DefinitionService",
    "DefinitionsModule",
    "GraphEntryLabels",
    "GraphSessionSummarySource",
    "GraphValidationSource",
    "IdMismatchError",
    "LazyVersionRepository",
    "PlainSecretScan",
    "SavedDefinition",
    "SecretRuleCheck",
    "SpaceGraphValidationSource",
    "WorkspaceState",
    "build_router",
    "build_rules",
    "build_store",
    "definition_kinds",
    "module",
    "plain_secret_warnings",
    "register_contributed_kinds",
    "scan_store",
    "settings_rule_issues",
]
