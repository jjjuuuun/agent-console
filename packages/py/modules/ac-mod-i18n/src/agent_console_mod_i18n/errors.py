"""Module exceptions → error bodies (``ModuleParts.error_map``), same in the server and standalone.

- ``UnknownLanguageError`` → ``i18n.unknown_language`` (404), ``details.language`` = the requested
  code, ``details.available`` = languages that have a catalog.
"""

from __future__ import annotations

from agent_console_contracts import ErrorCodes
from agent_console_modkit import ErrorMapping, ErrorReply

from .service import UnknownLanguageError


def unknown_language_reply(exc: Exception) -> ErrorReply:
    """``UnknownLanguageError`` → error body."""
    language = exc.language if isinstance(exc, UnknownLanguageError) else ""
    available = list(exc.available) if isinstance(exc, UnknownLanguageError) else []
    return ErrorReply(
        code=ErrorCodes.I18N_UNKNOWN_LANGUAGE,
        message=str(exc),
        details={"language": language, "available": available},
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {UnknownLanguageError: unknown_language_reply}
"""Module ``error_map``."""

__all__ = ["ERROR_MAP", "unknown_language_reply"]
