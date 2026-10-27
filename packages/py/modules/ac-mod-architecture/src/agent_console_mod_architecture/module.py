"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-architecture``,
design §5.5R.3).

- 제공: ``architecture.catalog``(병합된 프로필·연산자·검사·투영), ``server.warnings``(저장된
  ``architecture`` 섹션 형식 문제). 필수 포트 없음(혼자 켜진다).
- 선택: ``workspace.settings``(사용자 설정 ``architecture`` 섹션). 없으면 기본 + 플러그인 프로필만.
- 경로: ``GET /architecture/profiles``, ``GET /architecture/profiles/{id}``,
  ``POST /architecture/profiles/check``, ``POST /architecture/project``.
- 프로필 플러그인(X23): 호스트 묶음의 ``architecture_profiles`` 확장(``plugins.load_plugins``가
  채운다). 묶음이 없으면(단독 실행) entry point에서 직접 읽는다.
- 조건 연산자(X22): 호스트 묶음의 ``condition_operators`` 확장. 비어 있으면(연산자를 읽는 다른
  로더가 없는 서버) 설치된 연산자를 읽어 채운다. 묶음이 없으면 새로 읽는다.
- 로그·실행을 모른다. 로그 범위 구조도는 연동 모듈(``link-logs-architecture``)이 이 모듈의
  ``architecture.catalog``로 그린다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_console_architecture import load_default_profiles, plugin_sources
from agent_console_conditions import (
    CONDITION_OPERATORS_EXTENSION,
    ConditionOperator,
    as_condition_operator,
    default_operators,
    load_condition_operators,
    operator_map,
)
from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_registry import Registry

from .catalog import ArchitectureCatalogService, section_of
from .errors import ERROR_MAP
from .plugins import profile_registry
from .ports import ARCHITECTURE_CATALOG, SERVER_WARNINGS, WORKSPACE_SETTINGS
from .routes import build_router
from .settings import ArchitectureModuleSettings

MODULE_ID = "mod-architecture"
WEB_ROLES: tuple[str, ...] = ("architecture",)
"""웹 라우트 역할. 웹 설정 화면의 "구조도" 섹션 데이터가 이 역할을 요구한다
(모듈이 없으면 섹션 없음)."""


def _version() -> str:
    try:
        return version("agent-console-mod-architecture")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def operators_of(registries: Any) -> Callable[[], Mapping[str, ConditionOperator]]:
    """조건 연산자를 돌려주는 함수.

    호스트 묶음이 있으면 그 ``condition_operators`` 확장을 쓴다(비어 있으면 설치된 연산자로
    채운다 — 실행 모듈이 설치되지 않은 서버). 묶음이 없으면(단독 실행) 설치된 연산자를 한 번
    읽는다.
    """
    extension = getattr(registries, "extension", None)
    if callable(extension):
        registry: Registry[ConditionOperator] = extension(
            CONDITION_OPERATORS_EXTENSION, validator=as_condition_operator
        )
        if not registry.list():
            load_condition_operators(registry)
        return lambda: operator_map(registry)
    found, _reports = default_operators()
    return lambda: found


class ArchitectureModule:
    """구조도 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="구조도",
        description="구조도 프로필 목록·검사·단독 투영(/architecture/*)",
        provides=(ARCHITECTURE_CATALOG, SERVER_WARNINGS),
        optional=(WORKSPACE_SETTINGS,),
        settings_schema=ArchitectureModuleSettings,
        contracts={"architecture": CONTRACT_VERSIONS["architecture"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ArchitectureModuleSettings):
            cfg = ArchitectureModuleSettings()
        registry = profile_registry(ctx.registries)
        reader = ctx.port(WORKSPACE_SETTINGS)

        def user_section() -> Any:
            return section_of(reader()) if reader is not None else None

        service = ArchitectureCatalogService(
            defaults=load_default_profiles,
            plugins=lambda: plugin_sources(registry),
            settings=user_section,
            operators=operators_of(ctx.registries),
            max_request_events=cfg.max_request_events,
            max_scope_events=cfg.max_scope_events,
        )
        ctx.provide(ARCHITECTURE_CATALOG, service)
        ctx.provide(SERVER_WARNINGS, service.warnings)
        return ModuleParts(routers=[build_router(lambda: service)], error_map=dict(ERROR_MAP))


module = ArchitectureModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "ArchitectureModule", "module", "operators_of"]
