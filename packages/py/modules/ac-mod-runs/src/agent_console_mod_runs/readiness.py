"""실행 백엔드 준비 상태·연결 테스트·로그인 조립(ux-overhaul §15.8·§15.9).

모듈은 백엔드 id·상태 이름을 모른다. 엔진 패키지의 ``BackendReadinessService``에 레지스트리·비밀
존재 확인·가림 함수를 넣을 뿐이다.

가림(응답 글자 필드 전부, ``checks[].note``·``message``·``details`` 포함):
1. 환경변수 중 이름이 비밀로 의심되는 것(``secrets.rules`` 포트의 규칙, 없으면 기본 규칙)의 값
2. 엔진 비밀 해석기가 해석한 값(``secret://``)과 그 해석기의 의심 값 가림
3. 의심 값 패턴(규칙의 ``redact_suspected``) — 기록 설정 ``redact_suspected_in_logs``와 무관하게
   응답에는 항상 건다(화면에 보이는 글자이므로).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from agent_console_runtime import (
    REDACTED,
    BackendLoginService,
    BackendReadinessService,
    Registries,
    SecretResolver,
)
from agent_console_secret_rules import default_rules

from .ports import SecretRulesReader


@runtime_checkable
class _NameRules(Protocol):
    def name_suspected(self, name: str) -> bool: ...

    def redact_suspected(self, text: str) -> str: ...


def _rules(reader: Callable[[], SecretRulesReader | None]) -> _NameRules:
    port = reader()
    found = port() if port is not None else None
    return found if isinstance(found, _NameRules) else default_rules()


def build_check_redactor(
    secrets: SecretResolver,
    environ: Mapping[str, str],
    rules: Callable[[], SecretRulesReader | None] = lambda: None,
    *,
    min_chars: int = 4,
) -> Callable[[Any], Any]:
    """준비 상태·연결 테스트 응답의 비밀 가림 함수(JSON 값 → 가린 사본).

    Args:
        secrets: 엔진 비밀 해석기(해석한 값·의심 값 가림).
        environ: 환경변수(이름이 비밀로 의심되는 값을 가린다).
        rules: ``secrets.rules`` 포트(없으면 None) → 의심 규칙. 없으면 기본 규칙.
        min_chars: 이보다 짧은 환경 값은 가리지 않는다(정상 글자 훼손 방지).
    """

    def redact(value: Any) -> Any:
        current = _rules(rules)
        env_values = sorted(
            {v for k, v in environ.items() if len(v) >= min_chars and current.name_suspected(k)},
            key=len,
            reverse=True,
        )
        return _walk(secrets.redact(value), env_values, current.redact_suspected)

    return redact


def _walk(value: Any, values: list[str], suspected: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        for secret in values:
            if secret in value:
                value = value.replace(secret, REDACTED)
        return suspected(value)
    if isinstance(value, Mapping):
        return {k: _walk(v, values, suspected) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_walk(v, values, suspected) for v in value]
    return value


def build_readiness_service(
    registries: Registries,
    secrets: SecretResolver,
    environ: Mapping[str, str],
    *,
    rules: Callable[[], SecretRulesReader | None] = lambda: None,
    probe_timeout_max_s: float,
    min_chars: int = 4,
) -> BackendReadinessService:
    """레지스트리의 백엔드(호출마다 다시 읽음)로 준비 상태 서비스를 만든다."""
    return BackendReadinessService(
        lambda: {entry.key: entry.item for entry in registries.backends.list()},
        redact=build_check_redactor(secrets, environ, rules, min_chars=min_chars),
        has_secret=secrets.has,
        probe_timeout_max_s=probe_timeout_max_s,
    )


def build_login_service(
    registries: Registries,
    secrets: SecretResolver,
    environ: Mapping[str, str],
    *,
    rules: Callable[[], SecretRulesReader | None] = lambda: None,
    timeout_s: float,
    timeout_max_s: float,
    heartbeat_s: float,
    retain_s: float,
    screen_max_lines: int,
    min_chars: int = 4,
) -> BackendLoginService:
    """레지스트리의 백엔드(호출마다 다시 읽음)로 로그인 서비스를 만든다(ux-overhaul §15.9).

    가림은 준비 상태와 같은 함수(환경 비밀 값·비밀 해석기·의심 규칙)에
    서비스의 입력값 가림을 더한다.
    """
    return BackendLoginService(
        lambda: {entry.key: entry.item for entry in registries.backends.list()},
        redact=build_check_redactor(secrets, environ, rules, min_chars=min_chars),
        has_secret=secrets.has,
        environ=lambda: environ,
        timeout_default_s=min(timeout_s, timeout_max_s),
        timeout_max_s=timeout_max_s,
        heartbeat_s=heartbeat_s,
        retain_s=retain_s,
        screen_max_lines=screen_max_lines,
    )


__all__ = ["build_check_redactor", "build_login_service", "build_readiness_service"]
