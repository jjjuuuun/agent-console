"""리소스 종류 레지스트리와 entry point 로딩."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import EntryPoint
from typing import Any

from agent_console_contracts import ResourceTypeDescriptor
from agent_console_registry import LoadReport, Registry, load_entry_points, load_modules

from ._interfaces import ResourceType

__all__ = [
    "RESOURCE_TYPES_GROUP",
    "as_resource_type",
    "list_descriptors",
    "load_resource_types",
    "new_resource_types",
]

RESOURCE_TYPES_GROUP = "agent_console.resource_types"
"""X14 entry point 그룹."""


def new_resource_types() -> Registry[ResourceType]:
    """빈 리소스 종류 레지스트리(검사기 `as_resource_type` 부착). 앱이 만들어 주입한다."""
    return Registry("resource_types", validator=as_resource_type)


def as_resource_type(obj: Any) -> ResourceType:
    """로드한 객체를 `ResourceType`으로 검사한다(클래스면 인자 없이 인스턴스화).

    Raises:
        TypeError: 프로토콜을 만족하지 않거나 디스크립터가 아닐 때.
    """
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(item, ResourceType) or not isinstance(
        getattr(item, "descriptor", None), ResourceTypeDescriptor
    ):
        raise TypeError(f"resource_type이 아닙니다: {obj!r}")
    return item


def _version(item: ResourceType) -> int:
    return item.descriptor.version


def load_resource_types(
    registry: Registry[ResourceType],
    *,
    enabled: set[str] | None = None,
    modules: Iterable[str] = (),
    entry_points: Iterable[EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point(`agent_console.resource_types`)와 명시 모듈 목록에서 종류를 등록한다.

    Args:
        registry: 등록 대상.
        enabled: 주어지면 이 이름의 entry point만 로드(나머지는 `skipped`).
        modules: 설치하지 않은 로컬 모듈 경로(`"[key=]pkg.mod:attr"`).
        entry_points: 테스트용 주입(주면 설치된 패키지를 훑지 않는다).

    Returns:
        항목별 `LoadReport`. 실패는 예외 대신 보고서로. 레지스트리 key는 entry point 이름이며
        디스크립터 id와 같게 둔다(리소스 정의의 `type`이 이 key를 가리킨다).
    """

    def check(obj: Any) -> ResourceType:
        return as_resource_type(obj)

    reports = load_entry_points(
        RESOURCE_TYPES_GROUP,
        registry,
        enabled=enabled,
        validate=check,
        version_of=_version,
        entry_points=None
        if entry_points is None
        else [e for e in entry_points if e.group == RESOURCE_TYPES_GROUP],
    )
    reports += load_modules(modules, registry, validate=check, version_of=_version)
    return reports


def list_descriptors(registry: Registry[ResourceType]) -> list[ResourceTypeDescriptor]:
    """등록된 종류의 디스크립터(key 순, key별 최신). `GET /resource-types` 응답용."""
    return [entry.item.descriptor for entry in registry.list()]
