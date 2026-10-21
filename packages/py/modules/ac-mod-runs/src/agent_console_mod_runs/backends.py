"""실행 백엔드 설정 적용과 비밀 해석기 조립(설치자 설정 ``backends``·``min_redact_chars``).

모듈은 백엔드 이름·키의 의미를 모른다(R0). 설정 값은 백엔드의 ``from_options`` 훅에 그대로 넘긴다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from agent_console_runtime import (
    BACKEND_OPTIONS_HOOK,
    ConfigurableBackend,
    EnvSecretProvider,
    Registries,
    SecretProvider,
    SecretResolver,
)

_log = logging.getLogger("agent_console_mod_runs")


class BackendOptionsError(ValueError):
    """백엔드 훅이 설치자 설정을 거부했다(메시지에 값은 없다)."""


def configure_backends(
    registries: Registries,
    options_by_id: Mapping[str, Mapping[str, Any]],
    *,
    secrets: SecretResolver,
    environ: Mapping[str, str],
) -> list[str]:
    """등록된 백엔드 중 ``ConfigurableBackend`` 훅이 있는 것을 설정 값으로 다시 만들어 교체한다.

    entry point는 인자 없이 만들어지므로 생성 인자(설정 ``backends.<id>``)와 공용 비밀 해석기·환경은
    백엔드의 ``from_options`` 훅으로 넘긴다. 훅이 없는 백엔드에 설정이 있거나, 등록되지 않은 id에
    설정이 있으면 경고만 남긴다.

    Returns:
        교체한 백엔드 id 목록.

    Raises:
        BackendOptionsError: 훅이 설정 값을 거부했을 때(``ValueError``, 메시지에 값은 없다).
    """
    replaced: list[str] = []
    for entry in registries.backends.list():
        options = options_by_id.get(entry.key, {})
        if not isinstance(entry.item, ConfigurableBackend):
            if entry.key in options_by_id:
                _log.warning(
                    "백엔드 %s는 설정 훅(%s)이 없어 설정을 무시합니다",
                    entry.key,
                    BACKEND_OPTIONS_HOOK,
                )
            continue
        try:
            hook = type(entry.item).from_options
            backend = hook(options, secrets=secrets, environ=environ)
        except ValueError as exc:
            raise BackendOptionsError(f"backends.{entry.key}: {exc}") from None
        registries.backends.register(
            entry.key, backend, version=entry.version, source=entry.source, replace=True
        )
        replaced.append(entry.key)
    for backend_id in options_by_id:
        if backend_id not in registries.backends:
            _log.warning(
                "설정의 백엔드 %s가 등록되어 있지 않습니다(비활성 또는 미설치)", backend_id
            )
    return replaced


class LookupSecretProvider:
    """``이름 → 값`` 함수(호스트 기본 서비스 ``secret_resolver``)를 엔진 비밀 공급자로 감싼다."""

    def __init__(self, lookup: Callable[[str], str | None]) -> None:
        self._lookup = lookup

    def get_secret(self, name: str) -> str | None:
        return self._lookup(name)


def build_secret_resolver(
    *,
    lookup: Callable[[str], str | None] | None,
    environ: Mapping[str, str],
    registries: Registries,
    min_redact_chars: int,
    extra_redact: Callable[[str], str] | None = None,
) -> SecretResolver:
    """엔진 비밀 해석기. 호스트가 해석 함수를 주면 그것만, 없으면 환경변수 → 등록된 비밀 공급자 순.

    Args:
        lookup: 호스트 기본 서비스 ``secret_resolver``(환경변수 접두·플러그인 공급자를 이미 합침).
        environ: ``lookup``이 없을 때 읽을 환경.
        registries: ``lookup``이 없을 때 비밀 공급자(``registries.secret_providers``)를 읽는다.
        min_redact_chars: 이보다 짧은 값은 기록에서 가리지 않는다.
        extra_redact: 해석한 비밀을 가린 뒤 한 번 더 거는 함수(의심 값 가리기).
    """
    providers: list[SecretProvider]
    if lookup is not None:
        providers = [LookupSecretProvider(lookup)]
    else:
        providers = [
            EnvSecretProvider(environ),
            *(e.item for e in registries.secret_providers.list()),
        ]
    return SecretResolver(providers, min_redact_chars=min_redact_chars, extra_redact=extra_redact)


__all__ = [
    "BackendOptionsError",
    "LookupSecretProvider",
    "build_secret_resolver",
    "configure_backends",
]
