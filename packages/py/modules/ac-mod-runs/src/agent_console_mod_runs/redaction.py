"""실행 기록 저장 직전의 의심 값 가리기(``SecretResolver(extra_redact=)``, design §2R.4).

규칙은 ``secrets.rules`` 포트에서, 켜고 끄기는 공통 설정 ``secrets.redact_suspected_in_logs``
(``workspace.settings`` 포트)에서 온다. 두 포트가 없으면 의심 값은 가리지 않는다(해석한 비밀 값은
엔진이 항상 가린다).
"""

from __future__ import annotations

from collections.abc import Callable

from .ports import SecretRulesReader, SuspectedRules, WorkspaceSettingsReader


class SuspectedRedaction:
    """지금 규칙·켜짐 상태로 문자열의 의심 값을 가린다. ``refresh``로 포트 값을 다시 읽는다.

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
        self._rules: SuspectedRules | None = None
        self._enabled = True

    def refresh(self) -> None:
        """포트에서 지금 규칙과 켜짐 상태를 읽는다(실행 시작·검증 직전에 부른다)."""
        reader = self._workspace()
        self._enabled = reader().secrets.redact_suspected_in_logs if reader is not None else True
        rules = self._rules_port()
        self._rules = rules() if rules is not None else None

    @property
    def active(self) -> bool:
        return self._enabled and self._rules is not None

    def redact_text(self, text: str) -> str:
        rules = self._rules
        return rules.redact_suspected(text) if self._enabled and rules is not None else text


__all__ = ["SuspectedRedaction"]
