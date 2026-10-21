"""정의 저장소 위의 리소스 조회(``resources.lookup``)와 종류 레지스트리(``resources.types``)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import Resource
from agent_console_registry import Registry
from agent_console_resources import (
    Content,
    ContentFiles,
    ResourceType,
    as_resource_type,
    load_declarative_types,
    load_resource_types,
    new_resource_types,
)
from agent_console_store import (
    RESOURCE_KIND,
    DefinitionCorrupt,
    DefinitionStore,
    InvalidIdentifier,
    NotFound,
    StoreError,
)

_log = logging.getLogger("agent_console_mod_resources")


class StoreResources:
    """``ResourceLookup`` + ``FileContentLookup`` 구현(정의 저장소의 리소스 종류).

    읽을 수 없는 정의·본문은 "없음"(None)으로 본다(묶음 조립이 경고로 바꾼다).

    Args:
        store: 정의 저장소.
        kind: 리소스 정의 종류 이름.
    """

    def __init__(self, store: DefinitionStore, kind: str = RESOURCE_KIND.name) -> None:
        self._store = store
        self._kind = kind

    def get_resource(self, ref: str) -> Resource | None:
        try:
            return self._store.get(self._kind, ref).model(Resource)
        except (NotFound, InvalidIdentifier, DefinitionCorrupt, ValidationError):
            return None

    def read_content(self, resource: Resource) -> Content:
        try:
            return self._store.read_content(self._kind, resource.id)
        except (StoreError, OSError):
            return None

    def read_files(self, resource: Resource) -> ContentFiles | None:
        try:
            return {
                f.path: self._store.read_file(self._kind, resource.id, f.path)
                for f in self._store.list_files(self._kind, resource.id)
            }
        except (StoreError, OSError):
            return None


def resource_types_of(
    registries: Any, extension: str, *, declarative_dir: Path | None = None
) -> Registry[ResourceType]:
    """호스트 레지스트리 묶음의 리소스 종류 확장(호스트가 이미 로드했다).

    묶음이 없으면(단독 실행) entry point와 ``declarative_dir``의 선언형 종류를 새로 읽는다.
    """
    extension_of = getattr(registries, "extension", None)
    if callable(extension_of):
        found: Registry[ResourceType] = extension_of(extension, validator=as_resource_type)
        return found
    registry = new_resource_types()
    reports = list(load_resource_types(registry))
    if declarative_dir is not None:
        reports += load_declarative_types(declarative_dir, registry)
    for report in reports:
        if not report.ok:
            _log.warning("리소스 종류 로드 실패: %s (%s)", report.source, report.error)
    return registry


__all__ = ["StoreResources", "resource_types_of"]
