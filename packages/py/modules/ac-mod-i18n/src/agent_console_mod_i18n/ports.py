"""Ports mod-i18n provides (matched by name; other modules declare the same name, not this file).

- ``server.warnings`` (many providers): catalogs and entries skipped while loading (``i18n.*``
  issue codes, severity warning).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from agent_console_contracts import Issue
from agent_console_modkit import PortKey

type WarningSource = Callable[[], Sequence[Issue]]
"""Shape of the ``server.warnings`` port."""

SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)

__all__ = ["SERVER_WARNINGS", "WarningSource"]
