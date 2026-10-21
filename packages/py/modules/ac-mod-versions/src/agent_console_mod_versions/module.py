"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-versions``, design §3R.1.3).

- 필수: ``definitions.store``. 선택: ``definitions.checks``(여러 제공자), ``secrets.rules``.
- 구독: ``definitions.saved`` → 보존 개수(``max_per_definition``, D3) 적용. 시작 때 한 번 전체 적용.
- 오류: 저장소 오류(``StoreError``)·되돌리기 거부(``RestoreRejectedError``) → 계약 오류 본문.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .errors import ERROR_MAP
from .ports import DEFINITION_CHECKS, DEFINITIONS_SAVED, DEFINITIONS_STORE, SECRET_RULES
from .routes import build_router
from .service import VersionService
from .settings import SETTINGS_COMPAT, VersionModuleSettings

MODULE_ID = "mod-versions"
WEB_ROLES: tuple[str, ...] = ("versions",)
"""웹 라우트 역할(design §3R.1.3 표)."""


def _version() -> str:
    try:
        return version("agent-console-mod-versions")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class VersionsModule:
    """버전 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="버전",
        description="정의 버전 목록·비교·되돌리기, 보존 개수",
        requires=(DEFINITIONS_STORE,),
        optional=(DEFINITION_CHECKS, SECRET_RULES),
        settings_schema=VersionModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"definitions": CONTRACT_VERSIONS["definitions"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, VersionModuleSettings):
            cfg = VersionModuleSettings()
        store = ctx.port(DEFINITIONS_STORE)
        if store is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.store가 없습니다")
        service = VersionService(
            store,
            checks=lambda: ctx.ports(DEFINITION_CHECKS),
            rules=ctx.port(SECRET_RULES),
            secret_issue_codes=cfg.secret_issue_codes,
            max_per_definition=cfg.max_per_definition,
        )
        startup: list[Callable[[], Awaitable[None]]] = []
        if cfg.max_per_definition is not None:
            ctx.subscribe(DEFINITIONS_SAVED, service.on_saved)

            async def retain_all() -> None:
                await asyncio.to_thread(service.retain_all)

            startup.append(retain_all)
        return ModuleParts(
            routers=[build_router(lambda: service, cfg.collections)],
            error_map=dict(ERROR_MAP),
            startup=startup,
        )


module = VersionsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "VersionsModule", "module"]
