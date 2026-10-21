"""색인 저장 직전의 비밀 의심 가리기(design §4R.4-4).

규칙은 ``secrets.rules`` 포트에서, 켜고 끄기는 워크스페이스 설정
``secrets.redact_suspected_in_logs``(기본 켬)에서 온다. 규칙 포트가 없으면 가리지 않는다
(모듈이 ``logs.redaction_unavailable`` 경고).
수집 한 번마다 ``refresh``로 포트 값을 다시 읽는다(설정 변경이 다음 수집부터 반영된다).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from agent_console_logs import JsonValue

from .ports import SecretRulesReader, SuspectedRules, WorkspaceSettingsReader


class LogRedaction:
    """지금 규칙·켜짐 상태로 JSON 값의 문자열 잎을 가린다(스레드 안전).

    Args:
        workspace: ``workspace.settings`` 포트(없으면 None)를 돌려주는 함수.
        rules: ``secrets.rules`` 포트(없으면 None)를 돌려주는 함수.
    """

    def __init__(
        self,
        workspace: Callable[[], WorkspaceSettingsReader | None] = lambda: None,
        rules: Callable[[], SecretRulesReader | None] = lambda: None,
    ) -> None:
        self._workspace = workspace
        self._rules_port = rules
        self._lock = threading.Lock()
        self._rules: SuspectedRules | None = None
        self._enabled = True

    @property
    def available(self) -> bool:
        """가림 규칙 포트가 있는가(없으면 경고 대상)."""
        return self._rules_port() is not None

    @property
    def enabled(self) -> bool:
        """설정상 가리기가 켜져 있는가(``refresh`` 시점 값)."""
        return self._enabled

    def wanted(self) -> bool:
        """지금 설정이 가리기를 원하는가(설정 포트가 없거나 읽지 못하면 켬 — 안전한 쪽)."""
        reader = self._workspace()
        if reader is None:
            return True
        try:
            return bool(reader().secrets.redact_suspected_in_logs)
        except Exception:
            return True

    def refresh(self) -> None:
        """포트에서 지금 규칙과 켜짐 상태를 읽는다. 설정을 읽지 못하면 켜진 쪽(안전)으로 둔다."""
        enabled = self.wanted()
        port = self._rules_port()
        rules = port() if port is not None else None
        with self._lock:
            self._enabled, self._rules = enabled, rules

    def __call__(self, value: JsonValue) -> JsonValue:
        with self._lock:
            rules, enabled = self._rules, self._enabled
        if not enabled or rules is None:
            return value
        redacted: JsonValue = rules.redact_value(value)
        return redacted


__all__ = ["LogRedaction"]
