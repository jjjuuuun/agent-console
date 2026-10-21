"""형식 공장 로딩(entry point `agent_console.exporters` + 명시 모듈) → 형식 목록."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from importlib.metadata import EntryPoint
from typing import Any

from agent_console_registry import LoadReport, Registry, load_entry_points, load_modules

from ._interfaces import EXPORTERS_EXTENSION, EXPORTERS_GROUP, Exporter, ExporterFactory

__all__ = [
    "as_exporter",
    "as_exporter_factory",
    "build_exporters",
    "load_exporter_factories",
    "new_exporter_factories",
]

_log = logging.getLogger(__name__)


def as_exporter_factory(obj: Any) -> ExporterFactory:
    """로드한 객체가 호출 가능한지 검사한다(형식 공장).

    Raises:
        TypeError: 호출할 수 없을 때.
    """
    if not callable(obj):
        raise TypeError(f"내보내기 형식 공장은 호출 가능해야 합니다: {type(obj).__name__}")
    factory: ExporterFactory = obj
    return factory


def as_exporter(obj: Any) -> Exporter:
    """공장이 만든 객체가 형식(`descriptor`·`plan`)인지 검사한다.

    Raises:
        TypeError: `Exporter` 프로토콜을 만족하지 않을 때.
    """
    if not isinstance(obj, Exporter) or not callable(getattr(obj, "plan", None)):
        raise TypeError(f"내보내기 형식이 아닙니다: {type(obj).__name__}")
    return obj


def new_exporter_factories() -> Registry[ExporterFactory]:
    """빈 형식 공장 레지스트리(검사기 `as_exporter_factory` 부착, 전역 없음)."""
    return Registry(EXPORTERS_EXTENSION, validator=as_exporter_factory)


def load_exporter_factories(
    registry: Registry[ExporterFactory],
    *,
    enabled: set[str] | None = None,
    modules: Iterable[str] = (),
    entry_points: Iterable[EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point와 명시 모듈(`"[key=]pkg.mod:attr"`)에서 형식 공장을 등록한다."""
    reports = load_entry_points(
        EXPORTERS_GROUP,
        registry,
        enabled=enabled,
        validate=as_exporter_factory,
        entry_points=entry_points,
    )
    if modules:
        reports += load_modules(list(modules), registry, validate=as_exporter_factory)
    return reports


def build_exporters(
    registry: Registry[ExporterFactory],
    options: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Exporter]:
    """등록된 공장(key 순)으로 형식을 만든다. 공장 하나의 실패·디스크립터 id와 key 불일치는 경고로
    남기고 건너뛴다.

    Args:
        registry: 형식 공장 레지스트리.
        options: 형식 key → 설치자 옵션(공장에 넘긴다, 키는 공장이 정한다).
    """
    exporters: dict[str, Exporter] = {}
    for entry in registry.list():
        raw = (options or {}).get(entry.key)
        try:
            exporter = as_exporter(entry.item(raw if isinstance(raw, Mapping) else {}))
        except Exception as exc:
            _log.warning("내보내기 형식 %s를 만들지 못했습니다: %s", entry.key, type(exc).__name__)
            continue
        if exporter.descriptor.id != entry.key:
            _log.warning(
                "내보내기 형식 %s의 디스크립터 id(%s)가 등록 이름과 달라 건너뜁니다",
                entry.key,
                exporter.descriptor.id,
            )
            continue
        exporters[entry.key] = exporter
    return exporters
