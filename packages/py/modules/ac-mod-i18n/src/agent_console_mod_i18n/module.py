"""Server module definition (``mod-i18n`` in entry point group ``agent_console.server_modules``).

- No required ports; it runs alone. Provides ``server.warnings`` (catalog loading problems).
- Routes: ``GET /i18n``, ``GET /i18n/{lang}``.
- Package catalogs: the host bundle's ``message_catalogs`` extension (filled by
  ``plugins.load_plugins``, so ``plugins.enabled``/``plugins.disabled`` apply). Without a bundle (a
  standalone run) the installed entry points are read directly. The module setting
  ``disabled_catalogs`` is applied in both cases.
- User folders: ``catalog_dirs`` (relative to the settings file folder), merged after packages.
- When the module is off, the web uses only its own catalogs and server text stays as the original.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_i18n import package_catalogs
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .errors import ERROR_MAP
from .plugins import catalog_entry_points
from .ports import SERVER_WARNINGS
from .routes import build_router
from .service import I18nService
from .settings import I18nModuleSettings

MODULE_ID = "mod-i18n"
WEB_ROLES: tuple[str, ...] = ("i18n",)
"""Web route roles (the web reads server catalogs only when this role is present)."""

_log = logging.getLogger("agent_console_mod_i18n")


def _version() -> str:
    try:
        return version("agent-console-mod-i18n")
    except PackageNotFoundError:  # pragma: no cover - run from source without install
        return "0.0.0"


class I18nModule:
    """Message catalog module."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="화면 언어",
        description="설치된 패키지와 사용자 폴더의 화면 문구 번역을 모아 화면에 준다",
        provides=(SERVER_WARNINGS,),
        settings_schema=I18nModuleSettings,
        contracts={"i18n": CONTRACT_VERSIONS["i18n"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, I18nModuleSettings):
            cfg = I18nModuleSettings()
        service = build_service(cfg, ctx)
        ctx.provide(SERVER_WARNINGS, service.warnings)
        return ModuleParts(routers=[build_router(lambda: service)], error_map=dict(ERROR_MAP))


def build_service(cfg: I18nModuleSettings, ctx: ModuleContext) -> I18nService:
    """Read package catalogs (host bundle or installed entry points) and make the service."""
    entry_points = catalog_entry_points(ctx.registries)
    packages = package_catalogs(entry_points=entry_points, disabled=cfg.disabled_catalogs)
    seen = {*packages.skipped_sources, *(c.source for c in packages.catalogs)}
    seen.update(issue.source for issue in packages.issues if issue.source)
    for name in cfg.disabled_catalogs:
        if name not in seen:
            _log.warning(
                "modules.options.mod-i18n.disabled_catalogs: '%s' is not an installed catalog "
                "name (ignored)",
                name,
            )
    return I18nService(
        packages=packages,
        folders=cfg.catalog_dirs,
        base_dir=ctx.paths.base_dir if ctx.paths is not None else None,
        default_language=cfg.default_language,
        fallback_language=cfg.fallback_language,
        source_language=cfg.source_language,
    )


module = I18nModule()
"""Module instance the entry point names."""

__all__ = ["MODULE_ID", "WEB_ROLES", "I18nModule", "build_service", "module"]
