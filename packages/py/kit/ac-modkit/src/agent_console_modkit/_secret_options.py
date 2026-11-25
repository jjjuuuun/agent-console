"""비밀 값 공급자 설정 훅(호스트 기본 서비스, X10 설정).

비밀 공급자는 entry point로 **인자 없이** 만들어진다. 설치자 설정(서버 설정
``secrets.providers.<key>``)이 필요한 공급자는 두 classmethod를 둔다(실행 백엔드의
``from_options`` 훅과 같은 모양):

- ``options_schema() -> dict``: 옵션 JSON Schema(기본값은 ``properties.*.default``). 호스트가 설정
  보기(서버 정보 ``plugin_options``)에 싣고 기본값을 채운다. 비밀 필드는 ``x-secret: true`` 또는
  ``format: password``, 경로 필드는 ``format: path``로 표시하면 보기에서 가린다.
- ``from_options(options, *, environ, base_dir) -> 공급자``: 설정 값으로 공급자를 새로 만든다.
  틀린 값이면 ``ValueError``(메시지에 값은 넣지 않는다) → 호스트가 시작을 거부한다.

호스트는 키의 의미를 모른다(R0). 설정이 있는 공급자만 다시 만든다 — 설정이 없으면 entry point가
만든 그대로다(코드로 직접 등록한 인스턴스를 덮지 않는다).

이 파일은 공급자 패키지(실행 엔진)에 의존하지 않는다. 이름으로만 맞춘다(duck typing).
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from ._hostext import secret_provider_registry

_log = logging.getLogger("agent_console_modkit.hostext")

SECRET_PROVIDER_OPTIONS_HOOK: Final = "from_options"
"""공급자 클래스의 설정 훅 이름(classmethod, ``ConfigurableSecretProvider``)."""

SECRET_PROVIDER_SCHEMA_HOOK: Final = "options_schema"
"""공급자 클래스의 옵션 스키마 훅 이름(classmethod, ``ConfigurableSecretProvider``)."""

SECRET_PROVIDERS_SETTINGS_KEY: Final = "secrets.providers"
"""설치자 설정에서 공급자 옵션을 두는 자리(``<이 키>.<공급자 key>``)."""


@runtime_checkable
class ConfigurableSecretProvider(Protocol):
    """설치자 설정으로 다시 만들 수 있는 비밀 값 공급자(설정 훅).

    ``get_secret``(X10 ``SecretProvider``)에 더해 두 classmethod를 둔다. 호스트는 등록된 공급자의
    클래스에서 이 이름을 찾는다(상속·import 불필요).
    """

    def get_secret(self, name: str) -> str | None:
        """이름의 값(없으면 None)."""
        ...

    @classmethod
    def options_schema(cls) -> Mapping[str, Any]:
        """옵션 JSON Schema(``type: object``, 기본값 ``properties.*.default``)."""
        ...

    @classmethod
    def from_options(
        cls,
        options: Mapping[str, Any],
        *,
        environ: Mapping[str, str],
        base_dir: Path | None,
    ) -> Any:
        """설정 값(``secrets.providers.<key>``)으로 공급자를 만든다.

        Args:
            options: 설정 값(설정 파일 원문, 기본값은 채우지 않은 것).
            environ: 호스트 환경(주입).
            base_dir: 설정 파일 폴더(상대 경로 기준). 모르면 None.

        Raises:
            ValueError: 모르는 키·틀린 값(메시지에 값은 넣지 않는다).
        """
        ...


class SecretProviderOptionsError(ValueError):
    """공급자 설정 훅이 설정 값을 거부했다(메시지 = 설정 자리 + 훅의 메시지, 값 없음)."""


@dataclass(frozen=True)
class SecretProviderOptions:
    """공급자 하나의 옵션(가리기 전 — 화면에 낼 때는 ``mask_values``로 가린다).

    Attributes:
        name: 공급자 key.
        schema: 옵션 JSON Schema(공급자가 선언). None = 선언 안 함.
        values: 지금 값(스키마 기본값 + 설정 값).
        configured: 설정 값이 있어 훅으로 다시 만들었는지.
    """

    name: str
    schema: dict[str, Any] | None
    values: dict[str, Any]
    configured: bool = False

    @property
    def settings_key(self) -> str:
        """설정 파일 자리(``secrets.providers.<name>``)."""
        return f"{SECRET_PROVIDERS_SETTINGS_KEY}.{self.name}"


@dataclass
class SecretProviderSetup:
    """``configure_secret_providers`` 결과.

    Attributes:
        configured: 설정 값으로 다시 만든 공급자 key(등록 순).
        options: 스키마나 설정이 있는 공급자의 옵션(등록 순).
        warnings: 사람이 읽는 설정 경고(모르는 key, 훅 없는 공급자에 설정). 값은 없다.
    """

    configured: list[str] = field(default_factory=list)
    options: list[SecretProviderOptions] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def schema_defaults(schema: Mapping[str, Any] | None, values: Mapping[str, Any]) -> dict[str, Any]:
    """스키마 ``properties.*.default``로 빠진 값을 채운 사본(객체 속성은 재귀). 검증은 하지 않는다.

    >>> schema_defaults({"properties": {"a": {"default": 1}, "b": {"default": 2}}}, {"b": 3})
    {'b': 3, 'a': 1}
    """
    out: dict[str, Any] = copy.deepcopy(dict(values))
    props = schema.get("properties") if schema else None
    if not isinstance(props, Mapping):
        return out
    for name, sub in props.items():
        if not isinstance(sub, Mapping):
            continue
        if name not in out and "default" in sub:
            out[name] = copy.deepcopy(sub["default"])
        elif isinstance(out.get(name), Mapping) and isinstance(sub.get("properties"), Mapping):
            out[name] = schema_defaults(sub, out[name])
    return out


def _schema_of(cls: type[Any], name: str) -> dict[str, Any] | None:
    hook = getattr(cls, SECRET_PROVIDER_SCHEMA_HOOK, None)
    if not callable(hook):
        return None
    try:
        schema = hook()
    except Exception as exc:  # 스키마를 못 내도 공급자는 쓴다(보기에만 빠진다)
        _log.warning("비밀 공급자 %s의 옵션 스키마를 읽지 못했습니다(%s)", name, type(exc).__name__)
        return None
    if not isinstance(schema, Mapping):
        _log.warning("비밀 공급자 %s의 옵션 스키마가 객체가 아닙니다", name)
        return None
    return copy.deepcopy(dict(schema))


def configure_secret_providers(
    registries: Any,
    options_by_id: Mapping[str, Mapping[str, Any]],
    *,
    environ: Mapping[str, str],
    base_dir: Path | None = None,
) -> SecretProviderSetup:
    """설정(``secrets.providers``)이 있는 공급자를 그 값으로 다시 만들어 레지스트리에서 바꾼다.

    호스트가 플러그인을 다 읽은 뒤(``load_host_plugins``) 비밀 조회 사슬(``secret_lookup``)을 만들기
    **전에** 부른다. 설정이 없는 공급자는 그대로 둔다. 훅이 없는 공급자에 설정이 있거나, 등록되지
    않은 key(미설치·``plugins.disabled``)에 설정이 있으면 경고만 남긴다.

    Args:
        registries: 레지스트리 묶음(``HostPlugins.registries``).
        options_by_id: 공급자 key → 설정 값.
        environ: 훅에 넘길 환경.
        base_dir: 훅에 넘길 설정 파일 폴더(상대 경로 기준).

    Returns:
        ``SecretProviderSetup``(바꾼 key, 옵션 보기 재료, 경고).

    Raises:
        SecretProviderOptionsError: 훅이 설정 값을 거부했거나(``ValueError``·``TypeError``),
            공급자가 아닌 것을 돌려줬을 때.
    """
    setup = SecretProviderSetup()
    registry = secret_provider_registry(registries)
    entries = registry.list() if registry is not None else []
    known = {e.key for e in entries}
    for entry in entries:
        cls = type(entry.item)
        schema = _schema_of(cls, entry.key)
        hook = getattr(cls, SECRET_PROVIDER_OPTIONS_HOOK, None)
        given = entry.key in options_by_id
        raw = dict(options_by_id.get(entry.key) or {})
        where = f"{SECRET_PROVIDERS_SETTINGS_KEY}.{entry.key}"
        if given and not callable(hook):
            message = (
                f"{where}: 비밀 공급자 {entry.key}는 설정 훅({SECRET_PROVIDER_OPTIONS_HOOK})이 "
                "없어 설정을 무시합니다"
            )
            setup.warnings.append(message)
            _log.warning("%s", message)
            given = False
        if given and callable(hook):
            try:
                made = hook(raw, environ=environ, base_dir=base_dir)
            except (ValueError, TypeError) as exc:
                raise SecretProviderOptionsError(f"{where}: {exc}") from None
            if not callable(getattr(made, "get_secret", None)):
                raise SecretProviderOptionsError(
                    f"{where}: 설정 훅이 비밀 공급자(get_secret)를 돌려주지 않았습니다"
                )
            assert registry is not None  # entries가 있으면 레지스트리가 있다
            registry.register(
                entry.key, made, version=entry.version, source=entry.source, replace=True
            )
            setup.configured.append(entry.key)
        if schema is not None or given:
            setup.options.append(
                SecretProviderOptions(entry.key, schema, schema_defaults(schema, raw), given)
            )
    for key in options_by_id:
        if key not in known:
            message = (
                f"{SECRET_PROVIDERS_SETTINGS_KEY}의 '{key}'은(는) 등록된 비밀 공급자가 아닙니다"
                "(미설치·꺼짐, 무시함)"
            )
            setup.warnings.append(message)
            _log.warning("%s", message)
    return setup


__all__ = [
    "SECRET_PROVIDERS_SETTINGS_KEY",
    "SECRET_PROVIDER_OPTIONS_HOOK",
    "SECRET_PROVIDER_SCHEMA_HOOK",
    "ConfigurableSecretProvider",
    "SecretProviderOptions",
    "SecretProviderOptionsError",
    "SecretProviderSetup",
    "configure_secret_providers",
    "schema_defaults",
]
