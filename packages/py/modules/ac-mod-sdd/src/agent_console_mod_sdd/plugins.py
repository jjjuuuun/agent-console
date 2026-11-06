"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, X18): 검증 결과
출처(X42).

entry point 그룹 ``agent_console.sdd_verification_sources``의 항목을 호스트 레지스트리 묶음의
``sdd_verification_sources`` 확장에 로드한다. 항목 값은 ``VerificationSource`` 객체 또는 인자 없이
불러 그것을 만드는 함수(클래스)다. 설정 ``plugins.enabled``로 끈 항목은 읽지 않는다.

로드한 출처는 **사용자 설정** ``sdd.verification_sources``에 ``{id, enabled: true}``로 적어야 쓰인다
(설치만으로 추적 표에 결과가 들어가지 않는다). 연동 모듈이 포트로 주는 출처는 설정에 없어도 쓰이고,
설정에 ``enabled: false``로 적으면 끈다.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable
from typing import Any, Final

from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport, Registry, load_entry_points
from agent_console_sdd import VerificationSource

VERIFICATION_SOURCES_GROUP: Final = "agent_console.sdd_verification_sources"
"""검증 결과 출처 플러그인 entry point 그룹."""
VERIFICATION_SOURCES_EXTENSION: Final = "sdd_verification_sources"
"""호스트 레지스트리 묶음의 확장 이름(보고 그룹 이름도 같다)."""


def as_verification_source(obj: Any) -> VerificationSource:
    """레지스트리 검사기: ``VerificationSource``거나 인자 없이 불러 그것을 만드는 것.

    Raises:
        TypeError: 다른 모양일 때.
    """
    if isinstance(obj, VerificationSource) and not isinstance(obj, type):
        return obj
    if callable(obj):
        made = obj()
        if isinstance(made, VerificationSource):
            return made
    raise TypeError(
        "검증 결과 출처는 id와 collect(ctx)가 있는 객체(또는 그것을 만드는 함수)여야 합니다: "
        f"{type(obj).__name__}"
    )


def new_source_registry() -> Registry[VerificationSource]:
    """빈 검증 결과 출처 레지스트리(key = entry point 이름)."""
    return Registry(VERIFICATION_SOURCES_EXTENSION, validator=as_verification_source)


def load_source_plugins(
    registry: Registry[VerificationSource],
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point 그룹을 ``registry``에 로드한다(실패는 예외가 아니라 보고).

    Args:
        enabled: 주어지면 이 이름만 로드(나머지는 ``skipped``).
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다).
    """
    eps = (
        [ep for ep in entry_points if ep.group == VERIFICATION_SOURCES_GROUP]
        if entry_points is not None
        else None
    )
    return load_entry_points(
        VERIFICATION_SOURCES_GROUP,
        registry,
        enabled=enabled,
        validate=as_verification_source,
        entry_points=eps,
    )


def source_registry(registries: Any) -> Registry[VerificationSource]:
    """묶음의 검증 출처 레지스트리(없으면 만든다). 묶음이 없으면(단독 실행) 설치된 entry point로
    새로 읽은 레지스트리."""
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[VerificationSource] = extension(
            VERIFICATION_SOURCES_EXTENSION, validator=as_verification_source
        )
        return found
    registry = new_source_registry()
    load_source_plugins(registry)
    return registry


def plugin_sources(registry: Registry[VerificationSource]) -> list[VerificationSource]:
    """레지스트리의 출처(entry point 이름 순)."""
    return [e.item for e in sorted(registry.list(), key=lambda e: e.key)]


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """검증 결과 출처 entry point를 묶음의 확장에 로드한다."""
    registry = source_registry(ctx.registries)
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    return [
        (VERIFICATION_SOURCES_EXTENSION, r) for r in load_source_plugins(registry, enabled=enabled)
    ]


__all__ = [
    "VERIFICATION_SOURCES_EXTENSION",
    "VERIFICATION_SOURCES_GROUP",
    "as_verification_source",
    "load_plugins",
    "load_source_plugins",
    "new_source_registry",
    "plugin_sources",
    "source_registry",
]
