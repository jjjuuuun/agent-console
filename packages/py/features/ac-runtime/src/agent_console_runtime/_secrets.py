"""비밀 참조(`secret://name`) 해석과 마스킹(X10)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ._interfaces import SecretProvider

SECRET_REF_PREFIX = "secret://"
"""정의 데이터에 쓰는 비밀 참조 접두어(design §2.2 `attributes`)."""

_log = logging.getLogger(__name__)

DEFAULT_MIN_REDACT_CHARS = 4
"""이보다 짧은 비밀 값은 가리지 않는다(정상 텍스트 훼손 방지). 대신 경고를 남긴다."""

REDACTED = "[REDACTED]"
"""마스킹된 값 표시."""


class SecretNotFoundError(LookupError):
    """어떤 공급자도 그 이름의 비밀을 갖고 있지 않다. 메시지에 값은 들어가지 않는다."""

    def __init__(self, name: str) -> None:
        super().__init__(f"비밀 {name!r}를 찾을 수 없습니다")
        self.name = name


def is_secret_ref(value: object) -> bool:
    """`secret://…` 형식 문자열이면 참."""
    return isinstance(value, str) and value.startswith(SECRET_REF_PREFIX)


class SecretResolver:
    """공급자 목록을 순서대로 조회해 비밀 참조를 값으로 바꾼다.

    해석한 값을 기억해 두고 `redact`로 문자열에서 가린다(엔진은 저장 전 모든 기록에 적용한다).
    `min_redact_chars`(기본 4)보다 짧은 값은 정상 텍스트를 훼손하므로 가리지 않고, 그 이름으로
    경고 로그를 한 번 남긴다(값은 로그에 넣지 않는다). 공급자 순서는 앱이 정한다(예: env → keyring).

    `extra_redact`(선택)는 해석한 비밀을 가린 뒤 문자열마다 한 번 더 거는 함수다. 해석하지 않은
    평문 비밀(사용자가 프롬프트에 붙여 넣은 토큰 등)을 의심 규칙으로 가릴 때 앱이 넣는다
    (예: `ac-secret-rules`의 `SecretRules.redact_suspected`). 엔진은 규칙을 모른다.
    """

    def __init__(
        self,
        providers: Iterable[SecretProvider] = (),
        *,
        min_redact_chars: int = DEFAULT_MIN_REDACT_CHARS,
        extra_redact: Callable[[str], str] | None = None,
    ) -> None:
        self._providers = list(providers)
        self._seen: set[str] = set()
        self._min = max(1, min_redact_chars)
        self._warned: set[str] = set()
        self._extra = extra_redact

    def resolve(self, ref: str) -> str:
        """`secret://name` 또는 `name`을 값으로 바꾼다.

        Raises:
            SecretNotFoundError: 어떤 공급자에도 없을 때.
        """
        name = ref.removeprefix(SECRET_REF_PREFIX)
        for provider in self._providers:
            value = provider.get_secret(name)
            if value is not None:
                if len(value) >= self._min:
                    self._seen.add(value)
                elif value and name not in self._warned:
                    self._warned.add(name)
                    _log.warning(
                        "비밀 %r의 값이 %d자보다 짧아 기록에서 가리지 않습니다", name, self._min
                    )
                return value
        raise SecretNotFoundError(name)

    def has(self, ref: str) -> bool:
        """`secret://name` 또는 `name`이 어떤 공급자에 있는지만 본다.

        값을 돌려주지 않고 가림 목록에도 넣지 않는다(상태 점검용, ux-overhaul §15.8).
        """
        name = ref.removeprefix(SECRET_REF_PREFIX)
        return any(provider.get_secret(name) is not None for provider in self._providers)

    def resolve_refs(self, value: Any) -> Any:
        """dict·list 안의 모든 `secret://…` 문자열을 값으로 바꾼 사본(그 밖의 값은 그대로)."""
        if is_secret_ref(value):
            return self.resolve(value)
        if isinstance(value, Mapping):
            return {k: self.resolve_refs(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.resolve_refs(v) for v in value]
        return value

    @property
    def has_secrets(self) -> bool:
        """지금까지 해석한 비밀이 있으면 참."""
        return bool(self._seen)

    def redact(self, value: Any) -> Any:
        """해석한 적 있는 비밀 값을 `[REDACTED]`로 가리고 `extra_redact`를 건 사본
        (dict·list·str 재귀, 키는 그대로)."""
        if not self._seen and self._extra is None:
            return value
        return _redact(value, sorted(self._seen, key=len, reverse=True), self._extra)


def _redact(value: Any, secrets: list[str], extra: Callable[[str], str] | None) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, REDACTED)
        return extra(value) if extra is not None else value
    if isinstance(value, Mapping):
        return {k: _redact(v, secrets, extra) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v, secrets, extra) for v in value]
    return value


class EnvSecretProvider:
    """환경변수 공급자(X10 기본 구현 `env`). 환경은 주입받는다(전역 `os.environ`을 읽지 않음).

    `secret://anthropic_api_key` → `prefix + "anthropic_api_key"` 키, 없으면 대문자 키를 찾는다.
    """

    def __init__(self, environ: Mapping[str, str], *, prefix: str = "") -> None:
        self._environ = environ
        self._prefix = prefix

    def get_secret(self, name: str) -> str | None:
        """환경변수 값. 없으면 None."""
        for key in (self._prefix + name, (self._prefix + name).upper()):
            if key in self._environ:
                return self._environ[key]
        return None
