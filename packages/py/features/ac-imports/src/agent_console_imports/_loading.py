"""출처 공장 로딩(entry point `agent_console.import_sources` + 명시 모듈) → 출처 목록."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint
from typing import Any

from agent_console_registry import (
    LoadReport,
    Registry,
    load_entry_points,
    load_modules,
)

from ._interfaces import (
    IMPORT_SOURCES_EXTENSION,
    IMPORT_SOURCES_GROUP,
    ImportSource,
    ImportSourceContext,
    ImportSourceFactory,
)

_log = logging.getLogger(__name__)


def new_import_source_factories() -> Registry[ImportSourceFactory]:
    """빈 출처 공장 레지스트리(검사기 `as_import_source_factory` 부착, 전역 없음)."""
    return Registry(IMPORT_SOURCES_EXTENSION, validator=as_import_source_factory)


def as_import_source_factory(obj: Any) -> ImportSourceFactory:
    """로드한 객체가 호출 가능한지 검사한다.

    Raises:
        TypeError: 호출할 수 없을 때.
    """
    if not callable(obj):
        raise TypeError(f"출처 공장은 호출 가능해야 합니다: {type(obj).__name__}")
    factory: Callable[[ImportSourceContext], Iterable[ImportSource]] = obj
    return factory


def load_import_source_factories(
    registry: Registry[ImportSourceFactory],
    *,
    enabled: set[str] | None = None,
    modules: Iterable[str] = (),
    entry_points: Iterable[EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point와 명시 모듈(`"[key=]pkg.mod:attr"`)에서 출처 공장을 등록한다."""
    reports = load_entry_points(
        IMPORT_SOURCES_GROUP,
        registry,
        enabled=enabled,
        validate=as_import_source_factory,
        entry_points=entry_points,
    )
    if modules:
        reports += load_modules(list(modules), registry, validate=as_import_source_factory)
    return reports


def build_import_sources(
    registry: Registry[ImportSourceFactory], ctx: ImportSourceContext
) -> list[ImportSource]:
    """등록된 공장(key 순)으로 출처를 만든다. 공장 하나의 실패는 경고로 남기고 건너뛴다."""
    sources: list[ImportSource] = []
    for entry in registry.list():
        try:
            options = ctx.options.get(entry.key)
            local = ImportSourceContext(
                home=ctx.home,
                project_dir=ctx.project_dir,
                options=options if isinstance(options, dict) else {},
                secret_rules=ctx.secret_rules,
            )
            sources.extend(entry.item(local))
        except Exception as exc:
            _log.warning("가져오기 출처 공장 %s 실패: %s", entry.key, type(exc).__name__)
    return sources
