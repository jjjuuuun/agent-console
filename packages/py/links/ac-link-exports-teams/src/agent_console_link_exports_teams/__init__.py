"""agent-console-link-exports-teams: 내보내기 ↔ 팀 의미 연동 모듈(design §3R.1.4 L10, R1.2).

``exports.dependencies``(정의가 쓰는 정의 — 팀 구성 → 에이전트·리소스, 에이전트 → 리소스)를
제공해 내보내기가 의존을 함께 담게 한다.

공개 API:
    - ``module``(``ExportsTeamsLink``): entry point ``agent_console.server_modules``의
      ``link-exports-teams``.
    - ``TeamExportDependencies``: 서버 없이 쓰는 의존 계산.
    - 포트(``ports``): ``DEFINITIONS_LOOKUP``(필수)·``WORKSPACE_SETTINGS``(선택)·
      ``EXPORT_DEPENDENCIES``(제공), 소비자 쪽 프로토콜.
"""

from __future__ import annotations

from .dependencies import TeamExportDependencies
from .module import MODULE_ID, ExportsTeamsLink, module
from .ports import (
    DEFINITIONS_LOOKUP,
    EXPORT_DEPENDENCIES,
    WORKSPACE_SETTINGS,
    DefinitionLookup,
    ExportDependencies,
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "EXPORT_DEPENDENCIES",
    "MODULE_ID",
    "WORKSPACE_SETTINGS",
    "DefinitionLookup",
    "ExportDependencies",
    "ExportsTeamsLink",
    "TeamExportDependencies",
    "module",
]
