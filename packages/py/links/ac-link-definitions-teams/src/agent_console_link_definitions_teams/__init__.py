"""agent-console-link-definitions-teams: 정의 ↔ 팀 의미 연동 모듈(design §3R.1.4 L9, R2·R13.5).

정의 저장소(``definitions.lookup``)와 팀 의미 계산(``ac-teams``)을 이어 사용처·유효 설정·실행
계획·묶음 미리보기 경로를 붙이고, 목록이 쓰는 입구 이름(``graphs.entry_labels``)과 사용 수
(``definitions.usages``), 문서가 쓰는 정의(``definitions.dependencies``, 쓰는 정의 먼저 쓰기), 참조
추출(``definitions.references``, X25 — 여러 제공자 포트)을 제공한다.

공개 API:
    - ``module``(``DefinitionsTeamsLink``): entry point ``agent_console.server_modules``의
      ``link-definitions-teams``.
    - ``TeamDocumentDependencies``: 문서 → 쓰는 정의(HTTP·저장소 없이). ``references(kind, doc)``는
      ``definitions.references`` 모양(``[(kind, id)]``, 예외 없음).
    - ``TeamViews``: HTTP 없이 쓰는 계산 묶음(``references``·``entry_labels``·``node_effective``·
      ``node_bundle``·``agent_effective``·``plan_summary``), ``redact_values``.
    - ``build_router``: FastAPI 라우터(접두 없음). ``ERROR_MAP``.
    - ``WEB_ROLES``: 웹 연동 부분 역할 ``definitions:teams``.
    - 포트(``ports``): 받는 포트 7개(5.2R.34 ``settings.scope_layers`` — 유효 설정 ``?project=``의
      범위 층)와 제공 포트 4개, 소비자 쪽 프로토콜.
"""

from __future__ import annotations

from .dependencies import TeamDocumentDependencies
from .module import ERROR_MAP, MODULE_ID, WEB_ROLES, DefinitionsTeamsLink, module
from .ports import (
    DEFINITION_DEPENDENCIES,
    DEFINITION_REFERENCES,
    DEFINITION_USAGES,
    DEFINITIONS_LOOKUP,
    GRAPH_ENTRY_LABELS,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    SCOPE_LAYERS,
    SECRET_REDACT,
    SECRET_RULES,
    WORKSPACE_SETTINGS,
    DefinitionLookup,
    DefinitionUsages,
    DocumentDependencies,
    DocumentReferences,
    EntryLabels,
    ScopeLayersLike,
    ScopeLayersSource,
)
from .routes import build_router
from .views import NodeNotFoundError, TeamViews, redact_values

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITION_DEPENDENCIES",
    "DEFINITION_REFERENCES",
    "DEFINITION_USAGES",
    "ERROR_MAP",
    "GRAPH_ENTRY_LABELS",
    "MODULE_ID",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "SCOPE_LAYERS",
    "SECRET_REDACT",
    "SECRET_RULES",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "DefinitionLookup",
    "DefinitionUsages",
    "DefinitionsTeamsLink",
    "DocumentDependencies",
    "DocumentReferences",
    "EntryLabels",
    "NodeNotFoundError",
    "ScopeLayersLike",
    "ScopeLayersSource",
    "TeamDocumentDependencies",
    "TeamViews",
    "build_router",
    "module",
    "redact_values",
]
