"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-presets``, design §3R.1.3).

- 필수: ``definitions.store``. 선택: ``definitions.checks``(여러 제공자),
  ``definitions.dependencies``(적용 순서 — 쓰는 정의 먼저).
- 요약 배지: 호스트 레지스트리 묶음의 ``backends`` 디스크립터 ``ui_hints.badge``(없으면 배지 없음).
- 시작 훅: 설정 ``apply_on_start``의 프리셋을 적용한다(없는 id면 시작 실패 — 설치자 설정 오류).
- 오류: ``PresetNotFoundError`` → ``not_found``(404).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS, ErrorCodes
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .ports import DEFINITION_CHECKS, DEFINITION_DEPENDENCIES, DEFINITIONS_STORE
from .routes import build_router
from .service import PresetNotFoundError, PresetService, registry_backend_badge
from .settings import SETTINGS_COMPAT, PresetModuleSettings

MODULE_ID = "mod-presets"
WEB_ROLES: tuple[str, ...] = ("presets",)
"""웹 라우트 역할(design §3R.1.3 표)."""


def _version() -> str:
    try:
        return version("agent-console-mod-presets")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class PresetsModule:
    """프리셋 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="프리셋",
        description="프리셋 목록·적용(/presets), 시작 시 적용",
        requires=(DEFINITIONS_STORE,),
        optional=(DEFINITION_CHECKS, DEFINITION_DEPENDENCIES),
        settings_schema=PresetModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"definitions": CONTRACT_VERSIONS["definitions"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, PresetModuleSettings):
            cfg = PresetModuleSettings()
        store = ctx.port(DEFINITIONS_STORE)
        if store is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.store가 없습니다")
        base = ctx.paths.base_dir if ctx.paths is not None else None
        paths = [p if p.is_absolute() or base is None else base / p for p in cfg.directories]
        service = PresetService(
            store,
            paths,
            checks=lambda: ctx.ports(DEFINITION_CHECKS),
            on_conflict=cfg.on_conflict,
            dependencies=lambda: ctx.port(DEFINITION_DEPENDENCIES),
            backend_badge=registry_backend_badge(lambda: ctx.registries),
        )
        startup: list[Callable[[], Awaitable[None]]] = []
        if cfg.apply_on_start:
            ids = list(cfg.apply_on_start)

            async def apply_on_start() -> None:
                service.apply(ids)

            startup.append(apply_on_start)
        return ModuleParts(
            routers=[build_router(lambda: service)],
            error_map={PresetNotFoundError: ErrorCodes.NOT_FOUND},
            startup=startup,
        )


module = PresetsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "PresetsModule", "module"]
