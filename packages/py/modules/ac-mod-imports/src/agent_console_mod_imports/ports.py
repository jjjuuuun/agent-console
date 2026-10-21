"""mod-imports가 받는 포트(이름 = 포트, design §3R.1.2·§3R.1.3).

- 필수 ``definitions.store``: 가져온 정의를 쓸 저장소(``agent_console_imports.DefinitionWriter``).
- 선택 ``secrets.rules``: 지금 비밀 의심 규칙(``() -> SecretRules``). 없으면 출처가 기본 규칙을
  쓴다.
"""

from __future__ import annotations

from collections.abc import Callable

from agent_console_imports import DefinitionWriter
from agent_console_modkit import PortKey
from agent_console_secret_rules import SecretRules

type SecretRulesReader = Callable[[], SecretRules]
"""지금 비밀 의심 규칙을 돌려주는 함수(``secrets.rules`` 포트 모양)."""

DEFINITIONS_STORE: PortKey[DefinitionWriter] = PortKey("definitions.store", "정의 저장소(쓰기)")
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")

__all__ = ["DEFINITIONS_STORE", "SECRET_RULES", "SecretRulesReader"]
