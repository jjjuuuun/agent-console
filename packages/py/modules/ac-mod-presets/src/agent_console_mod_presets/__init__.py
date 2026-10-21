"""agent-console-mod-presets: 프리셋 기능 모듈(design §3R.1.3, E-19).

``ac-presets``(프리셋 읽기·탐색·적용 라이브러리)를 서버에 꽂는다. 경로 ``GET /presets``,
``POST /presets/{id}/apply``, 시작 시 적용(``apply_on_start``).

공개 API:
    - ``module``(``PresetsModule``): entry point ``agent_console.server_modules``의 ``mod-presets``.
    - ``PresetService``·``list_presets``·``to_result``·``item_validator``·``item_dependencies``·
      ``PresetNotFoundError``: HTTP 없이 쓰는 로직.
    - 요약(5.2R.6): ``summarize``(``badges``·``featured``·``start_graph``), ``BackendBadge``·
      ``registry_backend_badge``(백엔드 디스크립터 ``ui_hints.badge``), ``BACKEND_KEY``,
      ``scan_preset``·``PresetScan``·``ScanCache``(항목 훑기와 파일 시각 기준 기억).
    - ``build_router``: FastAPI 라우터(접두 없음).
    - ``PresetModuleSettings``: 설치자 설정(``modules.options.mod-presets``).
    - 포트: ``DEFINITIONS_STORE``(필수)·``DEFINITION_CHECKS``(선택, multi)·
      ``DEFINITION_DEPENDENCIES``(선택), 프로토콜 ``DefinitionCheck``·``DocumentDependencies``·
      ``DependencyRef``.
    - ``testing.local_definitions_module``: 단독 실행·테스트용 ``definitions.store`` 제공 모듈.
"""

from __future__ import annotations

from .module import MODULE_ID, WEB_ROLES, PresetsModule, module
from .ports import (
    DEFINITION_CHECKS,
    DEFINITION_DEPENDENCIES,
    DEFINITIONS_STORE,
    DefinitionCheck,
    DependencyRef,
    DocumentDependencies,
)
from .routes import build_router
from .service import (
    BACKEND_KEY,
    BackendBadge,
    PresetNotFoundError,
    PresetScan,
    PresetService,
    ScanCache,
    item_dependencies,
    item_validator,
    list_presets,
    registry_backend_badge,
    scan_preset,
    scope_stamp,
    store_kinds,
    summarize,
    to_result,
)
from .settings import PresetModuleSettings

__all__ = [
    "BACKEND_KEY",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "DEFINITION_DEPENDENCIES",
    "MODULE_ID",
    "WEB_ROLES",
    "BackendBadge",
    "DefinitionCheck",
    "DependencyRef",
    "DocumentDependencies",
    "PresetModuleSettings",
    "PresetNotFoundError",
    "PresetScan",
    "PresetService",
    "PresetsModule",
    "ScanCache",
    "build_router",
    "item_dependencies",
    "item_validator",
    "list_presets",
    "module",
    "registry_backend_badge",
    "scan_preset",
    "scope_stamp",
    "store_kinds",
    "summarize",
    "to_result",
]
