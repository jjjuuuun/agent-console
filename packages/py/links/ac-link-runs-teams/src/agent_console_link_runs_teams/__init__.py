"""agent-console-link-runs-teams: 실행·팀 연동 모듈(design §3R.1.4 L4, R4.4·R8.6).

공개 API:
    - ``module``(``RunsTeamsLink``): entry point ``agent_console.server_modules``의
      ``link-runs-teams``.
    - 포트(``ports``): 받음 ``RUNS_STARTER``·``DEFINITIONS_LOOKUP``·``WORKSPACE_SETTINGS``·
      ``RESOURCES_LOOKUP``·``RESOURCE_TYPES``·``DEFINITION_CHECKS``(선택), 제공
      ``RUN_PREPARERS``·``RUN_SERVICES``·``GRAPH_VALIDATION``, 구독 ``DEFINITIONS_SAVED``.
    - HTTP 없이 쓰는 부품: ``TeamRules``(팀 규칙 검사·사전 점검 ``preflight``·실행 준비·노드
      서비스, 노드 서비스 ``SCOPE_LAYERS``(실행 범위 층)를 설정 계산에 넣는다), 준비 결과
      ``TeamRunPreparation``(+ Run 맥락 ``run_context`` — 유효 작업 폴더 ``RUN_CONTEXT_CWD``),
      사전 점검 오류 ``backend_unresolved_error``(문구·해결 버튼 데이터 ``BackendFixTexts``),
      검증 이슈·노드 실패 해결 버튼 표 ``IssueFixes``(기본 데이터 ``DEFAULT_ISSUE_FIXES``,
      ``load_issue_fixes``, 설치자 옵션 ``RunsTeamsLinkSettings.issue_fixes_file``·
      ``issue_fixes_of``),
      ``ValidationSummaries``(목록 검증 요약), ``GraphValidationCache``·``workspace_revision``.
    - ``build_router``: ``POST /graphs/{id}/validate``(엔진 + 팀 규칙 + 저장 전 정의 검사의
      경고·정보 — ``definition_check_issues``·``with_definition_checks``).
"""

from __future__ import annotations

from .cache import GraphValidationCache, workspace_revision
from .definition_checks import (
    DEFAULT_CHECK_SEVERITIES,
    definition_check_issues,
    with_definition_checks,
)
from .fixes import DEFAULT_ISSUE_FIXES, IssueFixes, load_issue_fixes
from .module import MODULE_ID, WEB_ROLES, RunsTeamsLink, module
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    DEFINITIONS_SAVED,
    GRAPH_VALIDATION,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    RUN_PREPARERS,
    RUN_SERVICES,
    RUNS_STARTER,
    WORKSPACE_SETTINGS,
    DefinitionCheck,
    DefinitionLookup,
    RunChecker,
)
from .preflight import DEFAULT_BACKEND_FIX_TEXTS, BackendFixTexts, backend_unresolved_error
from .routes import build_router
from .rules import RUN_CONTEXT_CWD, TeamRules, TeamRunPreparation, ValidationSummaries
from .settings import RunsTeamsLinkSettings, issue_fixes_of

__all__ = [
    "DEFAULT_BACKEND_FIX_TEXTS",
    "DEFAULT_CHECK_SEVERITIES",
    "DEFAULT_ISSUE_FIXES",
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SAVED",
    "DEFINITION_CHECKS",
    "GRAPH_VALIDATION",
    "MODULE_ID",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "RUNS_STARTER",
    "RUN_CONTEXT_CWD",
    "RUN_PREPARERS",
    "RUN_SERVICES",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "BackendFixTexts",
    "DefinitionCheck",
    "DefinitionLookup",
    "GraphValidationCache",
    "IssueFixes",
    "RunChecker",
    "RunsTeamsLink",
    "RunsTeamsLinkSettings",
    "TeamRules",
    "TeamRunPreparation",
    "ValidationSummaries",
    "backend_unresolved_error",
    "build_router",
    "definition_check_issues",
    "issue_fixes_of",
    "load_issue_fixes",
    "module",
    "with_definition_checks",
    "workspace_revision",
]
