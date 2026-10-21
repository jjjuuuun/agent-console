"""사용량 출처 레지스트리와 entry point 로딩."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import EntryPoint
from typing import Any

from agent_console_contracts import UsageSourceDescriptor
from agent_console_registry import LoadReport, Registry, load_entry_points, load_modules

from ._interfaces import UsageSource

__all__ = [
    "USAGE_SOURCES_EXTENSION",
    "USAGE_SOURCES_GROUP",
    "as_usage_source",
    "list_descriptors",
    "load_usage_sources",
    "new_usage_sources",
]

USAGE_SOURCES_GROUP = "agent_console.usage_sources"
"""X13 entry point 그룹."""

USAGE_SOURCES_EXTENSION = "usage_sources"
"""레지스트리 묶음(`Registries.extension(name)`)에서 쓰는 이름이자 `new_usage_sources()`의 이름.

앱이 `new_usage_sources()`로 만든 레지스트리를 이 이름으로 묶음에 넣으면, `plugins.modules`의
`register(registries)` 플러그인도 `registries.extension(USAGE_SOURCES_EXTENSION)`로
출처를 등록할 수 있다.
"""


def new_usage_sources() -> Registry[UsageSource]:
    """빈 사용량 출처 레지스트리(검사기 `as_usage_source` 부착). 앱이 만들어 주입한다(전역 없음)."""
    return Registry(USAGE_SOURCES_EXTENSION, validator=as_usage_source)


def as_usage_source(obj: Any) -> UsageSource:
    """로드한 객체를 `UsageSource`로 검사한다(클래스면 인자 없이 인스턴스화).

    Raises:
        TypeError: 프로토콜을 만족하지 않거나 디스크립터가 아닐 때.
    """
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(item, UsageSource) or not isinstance(
        getattr(item, "descriptor", None), UsageSourceDescriptor
    ):
        raise TypeError(f"usage_source가 아닙니다: {obj!r}")
    return item


def load_usage_sources(
    registry: Registry[UsageSource],
    *,
    enabled: set[str] | None = None,
    modules: Iterable[str] = (),
    entry_points: Iterable[EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point(`agent_console.usage_sources`)와 명시 모듈 목록에서 출처를 등록한다.

    Args:
        registry: 등록 대상.
        enabled: 주어지면 이 이름의 entry point만 로드(나머지는 `skipped`).
        modules: 설치하지 않은 로컬 모듈 경로(`"[key=]pkg.mod:attr"`).
        entry_points: 테스트용 주입(주면 설치된 패키지를 훑지 않는다).

    Returns:
        항목별 `LoadReport`. 실패는 예외 대신 보고서로. 레지스트리 key(entry point 이름)가
        출처 id이며 스냅샷의 `source`·설정 `usage.sources[].id`가 이 key를 가리킨다.
    """
    reports = load_entry_points(
        USAGE_SOURCES_GROUP,
        registry,
        enabled=enabled,
        validate=as_usage_source,
        entry_points=None
        if entry_points is None
        else [e for e in entry_points if e.group == USAGE_SOURCES_GROUP],
    )
    reports += load_modules(modules, registry, validate=as_usage_source)
    return reports


def list_descriptors(registry: Registry[UsageSource]) -> list[UsageSourceDescriptor]:
    """등록된 출처의 디스크립터(key 순). id는 레지스트리 key로 맞춘다."""
    return [entry.item.descriptor.model_copy(update={"id": entry.key}) for entry in registry.list()]
