"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-resources``, design §3R.1.3).

- 필수: ``definitions.store``. 선택: ``definitions.usages``(목록 ``usage_count``, 없으면 null),
  ``definitions.checks``(여러 제공자 — 만들기·저장 때 error 422, warning·info는
  ``X-Console-Issues`` 헤더).
- 제공: ``resources.lookup``(정의·본문·여러 파일 조회), ``resources.types``(종류 레지스트리).
- 종류 레지스트리: 호스트 기본 서비스 ``registries``의 ``resource_types`` 확장(호스트가 플러그인 +
  선언형을 로드). 호스트가 주지 않으면(단독 실행) entry point와 워크스페이스 선언형 폴더를 읽는다.
- 본문 크기 한도는 정의 저장소가 건다(``mod-definitions``의 ``max_content_bytes``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .errors import ERROR_MAP
from .lookup import StoreResources, resource_types_of
from .ports import (
    DEFINITION_CHECKS,
    DEFINITION_USAGES,
    DEFINITIONS_STORE,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
)
from .routes import build_router
from .service import ResourceService
from .settings import ResourceModuleSettings

MODULE_ID = "mod-resources"
WEB_ROLES: tuple[str, ...] = ("definitions:resource",)
"""웹 라우트 역할(design §3R.1.3 표)."""


def _version() -> str:
    try:
        return version("agent-console-mod-resources")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ResourcesModule:
    """리소스 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="리소스",
        description="리소스 라이브러리 CRUD·본문·여러 파일, 리소스 종류·병합 전략 목록",
        provides=(RESOURCES_LOOKUP, RESOURCE_TYPES),
        requires=(DEFINITIONS_STORE,),
        optional=(DEFINITION_USAGES, DEFINITION_CHECKS),
        settings_schema=ResourceModuleSettings,
        contracts={"resources": CONTRACT_VERSIONS["resources"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ResourceModuleSettings):
            cfg = ResourceModuleSettings()
        store = ctx.port(DEFINITIONS_STORE)
        if store is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.store가 없습니다")
        declarative = ctx.paths.workspace / cfg.declarative_dir if ctx.paths is not None else None
        types = resource_types_of(ctx.registries, cfg.types_extension, declarative_dir=declarative)
        service = ResourceService(
            store,
            types,
            usages=lambda: ctx.port(DEFINITION_USAGES),
            content_files=cfg.content_files,
            default_content_file=cfg.default_content_file,
            reserved_file_names=cfg.reserved_file_names,
            checks=lambda: ctx.ports(DEFINITION_CHECKS),
        )
        ctx.provide(RESOURCES_LOOKUP, StoreResources(store))
        ctx.provide(RESOURCE_TYPES, types)
        return ModuleParts(routers=[build_router(lambda: service)], error_map=dict(ERROR_MAP))


module = ResourcesModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "ResourcesModule", "module"]
