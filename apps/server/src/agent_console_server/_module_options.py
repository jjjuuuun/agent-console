"""모듈 옵션 읽기 전용 보기(`GET /modules/{id}/options`, 5.2R.29).

modkit 보기 → 계약 `ModuleOptionsView`.

서버는 모듈 이름을 모른다. 가리기 규칙:

- 스키마가 비밀로 표시한 필드(`SecretStr`·`x-secret`)는 modkit이 늘 가린다.
- 평문 비밀 의심 판정은 `secrets.rules` 포트(사용자 규칙을 더한 지금 규칙, 이름으로만
  맞춤)의 `find_suspected`를 쓴다. 포트가 없으면(정의 모듈 꺼짐) 기본 규칙
  (`agent_console_secret_rules`)이다.
- 설정 `security.expose_paths`가 꺼지면 경로 필드도 가린다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_console_contracts import ModuleOptionsView
from agent_console_modkit import Assembly, SecretPathFinder
from agent_console_modkit.host import default_module_options_payload
from agent_console_secret_rules import REDACTED, default_rules

from ._ports import SECRET_RULES


def secret_finder(assembly: Assembly) -> SecretPathFinder:
    """지금 비밀 규칙의 `find_suspected`(결과는 위치만, 값 없음)."""
    port = assembly.port(SECRET_RULES)
    rules = port() if port is not None else default_rules()

    def find(values: Any) -> list[str]:
        return [f.path for f in rules.find_suspected(values)]

    return find


def module_options_payload(
    assembly: Assembly, *, hide_paths: bool
) -> Callable[[str], ModuleOptionsView | None]:
    """모듈 id → `ModuleOptionsView`(모르는 id면 None).

    Args:
        assembly: 조립 결과(꺼진 모듈 옵션도 보인다).
        hide_paths: 참이면 경로 필드를 가린다(`not security.expose_paths`).
    """
    raw = default_module_options_payload(
        assembly,
        secret_paths=lambda: secret_finder(assembly),
        hide_paths=lambda: hide_paths,
        mask=REDACTED,  # 비밀 규칙의 가림 문자열과 맞춘다
    )

    def payload(module_id: str) -> ModuleOptionsView | None:
        body = raw(module_id)
        return None if body is None else ModuleOptionsView.model_validate(body)

    return payload


__all__ = ["module_options_payload", "secret_finder"]
