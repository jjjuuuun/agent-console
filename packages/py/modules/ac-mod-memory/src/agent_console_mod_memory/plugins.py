"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, X18).

메모리 범위 종류(X29) 플러그인을 읽는다.

호스트 레지스트리 묶음의 ``memory_scope_kinds`` 확장에 검사기를 붙이고 entry point
``agent_console.memory_scope_kinds``를 로드한다. 설정 ``plugins.enabled``로 끈 항목은 읽지 않는다.
이 모듈이 설정으로 꺼져 있어도 설치되어 있으면 호스트가 부른다(보고에만 보인다).
"""

from __future__ import annotations

from typing import Any

from agent_console_memory import (
    MEMORY_SCOPE_KINDS_EXTENSION,
    MemoryScopeKind,
    load_scope_kind_plugins,
    new_scope_kind_registry,
    plugin_scope_kinds,
)
from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport, Registry

REPORT_GROUP = MEMORY_SCOPE_KINDS_EXTENSION
"""보고 그룹 이름."""


def ensure_scope_kinds(obj: Any) -> tuple[MemoryScopeKind, ...]:
    """레지스트리 검사기: 항목은 ``MemoryScopeKind`` 묶음(튜플)이어야 한다.

    entry point 로더(``load_scope_kind_plugins``)는 출처(``plugin:<배포 이름>``)를 채운 묶음으로
    바꿔 등록한다. ``register(registries)`` 플러그인도 같은 모양으로 등록한다.

    Raises:
        TypeError: 다른 모양일 때.
    """
    if isinstance(obj, tuple) and all(isinstance(item, MemoryScopeKind) for item in obj):
        return obj
    raise TypeError(
        "메모리 범위 종류 레지스트리 항목은 MemoryScopeKind 튜플이어야 합니다: "
        f"{type(obj).__name__}"
    )


def scope_kind_registry(registries: Any) -> Registry[tuple[MemoryScopeKind, ...]]:
    """묶음의 범위 종류 레지스트리(없으면 만든다). 묶음이 없으면(단독 실행) 설치된 entry point로
    새로 읽은 레지스트리."""
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[tuple[MemoryScopeKind, ...]] = extension(
            MEMORY_SCOPE_KINDS_EXTENSION, validator=ensure_scope_kinds
        )
        return found
    registry = new_scope_kind_registry()
    load_scope_kind_plugins(registry)
    return registry


def plugin_kinds(registry: Registry[tuple[MemoryScopeKind, ...]]) -> list[MemoryScopeKind]:
    """레지스트리의 범위 종류(entry point 이름 순)."""
    return plugin_scope_kinds(registry)


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """범위 종류 entry point를 묶음의 ``memory_scope_kinds`` 확장에 로드한다."""
    registry = scope_kind_registry(ctx.registries)
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    return [(REPORT_GROUP, r) for r in load_scope_kind_plugins(registry, enabled=enabled)]


__all__ = [
    "REPORT_GROUP",
    "ensure_scope_kinds",
    "load_plugins",
    "plugin_kinds",
    "scope_kind_registry",
]
