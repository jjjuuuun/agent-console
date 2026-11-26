"""Agent Console message catalog module (``mod-i18n``, design §I18N.7·§I18N.8).

Collects message catalogs from installed packages (entry point group
``agent_console.message_catalogs``) and user folders, and serves them:

- ``GET /api/v1/i18n`` → ``I18nInfo`` (languages, sources, completeness, default and fallback).
- ``GET /api/v1/i18n/{lang}`` → ``MessageCatalog`` (``ETag``; unknown language → 404
  ``i18n.unknown_language``).

Public API: ``module``, ``I18nModule``, ``I18nModuleSettings``, ``I18nService``,
``UnknownLanguageError``, ``SERVER_WARNINGS``, and the plugin loader helpers in ``plugins``.
"""

from __future__ import annotations

from .errors import ERROR_MAP, unknown_language_reply
from .module import MODULE_ID, WEB_ROLES, I18nModule, build_service, module
from .plugins import (
    MESSAGE_CATALOGS_EXTENSION,
    catalog_entry_points,
    load_plugins,
    register_catalog_entry_points,
)
from .ports import SERVER_WARNINGS
from .routes import build_router
from .service import CatalogBody, I18nService, UnknownLanguageError, issue_of
from .settings import DEFAULT_LANGUAGE, I18nModuleSettings

__all__ = [
    "DEFAULT_LANGUAGE",
    "ERROR_MAP",
    "MESSAGE_CATALOGS_EXTENSION",
    "MODULE_ID",
    "SERVER_WARNINGS",
    "WEB_ROLES",
    "CatalogBody",
    "I18nModule",
    "I18nModuleSettings",
    "I18nService",
    "UnknownLanguageError",
    "build_router",
    "build_service",
    "catalog_entry_points",
    "issue_of",
    "load_plugins",
    "module",
    "register_catalog_entry_points",
    "unknown_language_reply",
]
