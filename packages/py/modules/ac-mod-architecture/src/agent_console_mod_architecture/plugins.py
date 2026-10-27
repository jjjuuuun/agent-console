"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, X18): 구조도 프로필(X23).

호스트 레지스트리 묶음의 ``architecture_profiles`` 확장에 검사기를 붙이고 entry point
``agent_console.architecture_profiles``를 로드한다. 설정 ``plugins.enabled``로 끈 항목은
읽지 않는다.
이 모듈이 설정으로 꺼져 있어도 설치되어 있으면 호스트가 부른다(보고에만 보인다).
"""

from __future__ import annotations

from typing import Any

from agent_console_architecture import (
    ARCHITECTURE_PROFILES_EXTENSION,
    ProfileSource,
    load_profile_plugins,
    new_profile_registry,
)
from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport, Registry

REPORT_GROUP = ARCHITECTURE_PROFILES_EXTENSION
"""보고 그룹 이름."""


def ensure_profile_source(obj: Any) -> ProfileSource:
    """레지스트리 검사기: 항목은 ``ProfileSource``여야 한다.

    entry point 로더(``load_profile_plugins``)는 출처 이름(``plugin:<배포 이름>``)을 붙여
    ``ProfileSource``로 바꿔 등록한다. ``register(registries)`` 플러그인도 ``ProfileSource``를 직접
    만들어 등록한다(출처 이름은 그 플러그인이 정한다).

    Raises:
        TypeError: 다른 모양일 때.
    """
    if isinstance(obj, ProfileSource):
        return obj
    raise TypeError(
        f"구조도 프로필 레지스트리 항목은 ProfileSource여야 합니다: {type(obj).__name__}"
    )


def profile_registry(registries: Any) -> Registry[ProfileSource]:
    """묶음의 프로필 레지스트리(없으면 만든다). 묶음이 없으면(단독 실행) 설치된 entry point로
    새로 읽은 레지스트리."""
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[ProfileSource] = extension(
            ARCHITECTURE_PROFILES_EXTENSION, validator=ensure_profile_source
        )
        return found
    registry = new_profile_registry()
    load_profile_plugins(registry)
    return registry


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """구조도 프로필 entry point를 묶음의 ``architecture_profiles`` 확장에 로드한다."""
    registry = profile_registry(ctx.registries)
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    return [(REPORT_GROUP, r) for r in load_profile_plugins(registry, enabled=enabled)]


__all__ = ["REPORT_GROUP", "ensure_profile_source", "load_plugins", "profile_registry"]
