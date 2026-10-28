"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-imports``, design §3R.1.3).

- 필수: ``definitions.store``. 선택: ``secrets.rules``.
- 출처 공장 레지스트리: 호스트 기본 서비스 ``registries``의 ``import_sources`` 확장. 호스트가
  레지스트리를 주지 않으면(단독 실행) entry point에서 직접 읽는다.
- 오류: ``ImportServiceError`` → 그 ``code``(출처 없음 404 등).
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_imports import (
    IMPORT_SOURCES_EXTENSION,
    ImportService,
    ImportServiceError,
    ImportSourceContext,
    ImportSourceFactory,
    as_import_source_factory,
    build_import_sources,
    load_import_source_factories,
    new_import_source_factories,
)
from agent_console_modkit import ErrorReply, ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_registry import Registry

from .ports import DEFINITIONS_STORE, SECRET_RULES
from .routes import build_router
from .settings import SETTINGS_COMPAT, ImportModuleSettings

MODULE_ID = "mod-imports"
WEB_ROLES: tuple[str, ...] = ("imports",)
"""웹 라우트 역할(design §3R.1.3 표)."""

_log = logging.getLogger("agent_console_mod_imports")


def _version() -> str:
    try:
        return version("agent-console-mod-imports")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def import_factories_of(registries: Any) -> Registry[ImportSourceFactory]:
    """호스트 레지스트리 묶음의 ``import_sources`` 확장.

    묶음이 없으면(단독 실행) entry point에서 새로 읽는다.
    """
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[ImportSourceFactory] = extension(
            IMPORT_SOURCES_EXTENSION, validator=as_import_source_factory
        )
        return found
    registry = new_import_source_factories()
    for report in load_import_source_factories(registry):
        if not report.ok:
            _log.warning("가져오기 출처 로드 실패: %s (%s)", report.source, report.error)
    return registry


def import_error_reply(exc: Exception) -> ErrorReply:
    """``ImportServiceError`` → 그 ``code``(메시지는 예외 문장 — 출처 id만 담는다)."""
    return ErrorReply(code=str(getattr(exc, "code", "bad_request")))


class ImportsModule:
    """가져오기 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="가져오기",
        description="외부 설정(.claude 등)에서 정의를 복사해 가져오기(/resources/import/*)",
        requires=(DEFINITIONS_STORE,),
        optional=(SECRET_RULES,),
        settings_schema=ImportModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"imports": CONTRACT_VERSIONS["imports"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ImportModuleSettings):
            cfg = ImportModuleSettings()
        store = ctx.port(DEFINITIONS_STORE)
        if store is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.store가 없습니다")
        base = ctx.paths.base_dir if ctx.paths is not None else None
        project = cfg.project_dir
        if project is not None and not project.is_absolute() and base is not None:
            project = base / project
        sources = build_import_sources(
            import_factories_of(ctx.registries),
            ImportSourceContext(
                project_dir=project if project is not None else base,
                options=cfg.options,
                secret_rules=ctx.port(SECRET_RULES),
            ),
        )
        service = ImportService(sources, store)
        return ModuleParts(
            routers=[build_router(lambda: service)],
            error_map={ImportServiceError: import_error_reply},
        )


module = ImportsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "MODULE_ID",
    "WEB_ROLES",
    "ImportsModule",
    "import_error_reply",
    "import_factories_of",
    "module",
]
