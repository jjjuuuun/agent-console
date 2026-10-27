"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-logs-architecture``).

로그 색인(``mod-logs``)과 구조도 프로필(``mod-architecture``)을 잇는다(design §5.5R.3).

- 필수: ``logs.query``·``architecture.catalog``.
- 제공: ``logs.filter_predicates``에 필터 ``arch``·``arch_group``·``arch_sources``(X28),
  ``architecture.profile_checks``에 목록 본문에 없는 조건 경로 경고(X32, M-4 — 접두는 설치자 옵션
  ``unlisted_paths``).
- 경로: ``GET /logs/architecture``, ``GET /logs/events/{uid}/architecture``.
- 웹 역할 ``logs:architecture``(세션 상세 흐름 패널의 [구조도]). 이 연동이 꺼지면 경로가 404이고
  ``arch`` 필터는 모르는 이름(422)이다. 로그·구조도 모듈은 그대로 동작한다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .checks import UnlistedPathCheck
from .errors import ERROR_MAP
from .filters import ArchitectureFilter
from .ports import ARCHITECTURE_CATALOG, LOG_FILTER_PREDICATES, LOGS_QUERY, PROFILE_CHECKS
from .routes import build_router
from .settings import LogsArchitectureSettings
from .views import LogArchitectureViews

MODULE_ID = "link-logs-architecture"
WEB_ROLES: tuple[str, ...] = ("logs:architecture",)
"""웹 연동 부분 역할(로그 세션 상세·실행 상세의 구조도)."""


def _version() -> str:
    try:
        return version("agent-console-link-logs-architecture")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class LogsArchitectureLink:
    """로그 ↔ 구조도 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="로그·구조도 연동",
        description="로그 범위 구조도(/logs/architecture)·이벤트 멤버십, 이벤트 표 필터 arch",
        provides=(LOG_FILTER_PREDICATES, PROFILE_CHECKS),
        requires=(LOGS_QUERY, ARCHITECTURE_CATALOG),
        settings_schema=LogsArchitectureSettings,
        contracts={
            "logs": CONTRACT_VERSIONS["logs"],
            "architecture": CONTRACT_VERSIONS["architecture"],
        },
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        query = ctx.port(LOGS_QUERY)
        catalog = ctx.port(ARCHITECTURE_CATALOG)
        if query is None or catalog is None:  # pragma: no cover - 조립기가 보장한다
            raise RuntimeError("logs.query·architecture.catalog가 없습니다")
        cfg = ctx.settings
        if not isinstance(cfg, LogsArchitectureSettings):
            cfg = LogsArchitectureSettings()
        views = LogArchitectureViews(
            query,
            catalog,
            source_kinds=cfg.source_kinds,
            cache_scopes=cfg.cache_scopes,
            cache_events=cfg.cache_events,
            cache_profiles=cfg.cache_profiles,
            page_size=cfg.page_size,
        )
        ctx.provide(LOG_FILTER_PREDICATES, ArchitectureFilter(catalog, views.cache))
        ctx.provide(PROFILE_CHECKS, UnlistedPathCheck(cfg.unlisted_paths))
        return ModuleParts(routers=[build_router(lambda: views)], error_map=dict(ERROR_MAP))


module = LogsArchitectureLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "LogsArchitectureLink", "module"]
