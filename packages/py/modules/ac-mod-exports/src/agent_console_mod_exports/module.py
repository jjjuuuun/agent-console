"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-exports``, design §3R.1.3).

- 필수: ``definitions.lookup``. 선택: ``exports.dependencies``·``secrets.rules``.
- 형식 공장 레지스트리: 호스트 기본 서비스 ``registries``의 ``exporters`` 확장. 호스트가
  레지스트리를 주지 않으면(단독 실행) entry point에서 직접 읽는다.
- 오류: ``ExportError`` → 그 ``code``(+ ``details``·``issues``), 토큰 없음 → ``unauthorized``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from agent_console_contracts import CONTRACT_VERSIONS, ErrorCodes
from agent_console_exports import (
    EXPORTERS_EXTENSION,
    ExporterFactory,
    ExportError,
    ExportRoot,
    ExportService,
    FolderWriter,
    as_exporter_factory,
    build_exporters,
    load_exporter_factories,
    new_exporter_factories,
)
from agent_console_modkit import (
    ErrorMapping,
    ErrorReply,
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
)
from agent_console_registry import Registry

from .catalog import LookupExportCatalog
from .ports import DEFINITIONS_LOOKUP, EXPORT_DEPENDENCIES, SECRET_RULES
from .routes import TokenRequiredError, build_router
from .settings import SETTINGS_COMPAT, ExportModuleSettings

MODULE_ID = "mod-exports"
WEB_ROLES: tuple[str, ...] = ("exports",)
"""웹 라우트 역할(design §3R.1.3 표)."""

HOME_ENV_NAMES: tuple[str, ...] = ("HOME", "USERPROFILE")
"""``home``을 비웠을 때 사용자 홈을 찾는 환경변수(앞쪽 우선)."""

_log = logging.getLogger("agent_console_mod_exports")


def _version() -> str:
    try:
        return version("agent-console-mod-exports")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def exporter_factories_of(registries: Any) -> Registry[ExporterFactory]:
    """호스트 레지스트리 묶음의 ``exporters`` 확장.

    묶음이 없으면(단독 실행) entry point에서 새로 읽는다.
    """
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[ExporterFactory] = extension(
            EXPORTERS_EXTENSION, validator=as_exporter_factory
        )
        return found
    registry = new_exporter_factories()
    for report in load_exporter_factories(registry):
        if not report.ok:
            _log.warning("내보내기 형식 로드 실패: %s (%s)", report.source, report.error)
    return registry


def export_error_reply(exc: Exception) -> ErrorReply:
    """``ExportError`` → 계약 오류(422는 ``details.issues``, 그 밖은 ``details`` + 이슈)."""
    if not isinstance(exc, ExportError):  # pragma: no cover - 표에 ExportError만 건다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    issues = [i.model_dump(mode="json", exclude_none=True) for i in exc.issues]
    if exc.code == ErrorCodes.VALIDATION_FAILED:
        return ErrorReply(code=exc.code, details={"issues": issues})
    details: dict[str, Any] = dict(exc.details)
    if issues:
        details["issues"] = issues
    return ErrorReply(code=exc.code, details=details)


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    ExportError: export_error_reply,
    TokenRequiredError: ErrorCodes.UNAUTHORIZED,
}
"""모듈 ``error_map``."""


def _resolve(path: Path, base: Path | None) -> Path:
    return path if path.is_absolute() or base is None else base / path


def protected_paths(
    cfg: ExportModuleSettings, *, base: Path | None, environ: Mapping[str, str]
) -> list[Path]:
    """쓰기 금지 위치: 홈 기준 ``protected_in_home`` + ``protected``."""
    out = [_resolve(p, base) for p in cfg.protected]
    home = _resolve(cfg.home, base) if cfg.home is not None else None
    if home is None:
        home = next((Path(environ[n]) for n in HOME_ENV_NAMES if environ.get(n)), None)
    if home is not None:
        out += [home / name for name in cfg.protected_in_home]
    return out


class ExportsModule:
    """내보내기 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="내보내기",
        description="형식 목록·미리보기·보관 파일·허용 폴더 쓰기(/exporters, /exports/*)",
        requires=(DEFINITIONS_LOOKUP,),
        optional=(EXPORT_DEPENDENCIES, SECRET_RULES),
        settings_schema=ExportModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"exports": CONTRACT_VERSIONS["exports"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ExportModuleSettings):
            cfg = ExportModuleSettings()
        lookup = ctx.port(DEFINITIONS_LOOKUP)
        if lookup is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.lookup이 없습니다")
        base = ctx.paths.base_dir if ctx.paths is not None else None
        roots = [ExportRoot(r.id, _resolve(r.path, base), r.label) for r in cfg.roots]
        service = ExportService(
            build_exporters(exporter_factories_of(ctx.registries), cfg.options),
            LookupExportCatalog(lookup, ctx.port(EXPORT_DEPENDENCIES)),
            writer=FolderWriter(
                roots, protected=protected_paths(cfg, base=base, environ=ctx.environ)
            ),
            secret_rules=ctx.port(SECRET_RULES),
        )
        return ModuleParts(
            routers=[build_router(lambda: service, expose_paths=cfg.expose_paths)],
            error_map=dict(ERROR_MAP),
        )


module = ExportsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "ERROR_MAP",
    "HOME_ENV_NAMES",
    "MODULE_ID",
    "WEB_ROLES",
    "ExportsModule",
    "export_error_reply",
    "exporter_factories_of",
    "module",
    "protected_paths",
]
