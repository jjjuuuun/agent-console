"""X5(로그 출처)·X6(로그 분류기) 레지스트리와 entry point 로더."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import EntryPoint
from typing import Any

from agent_console_contracts.logs import (
    LogClassifierDescriptor,
    LogSourceDescriptor,
)
from agent_console_registry import LoadReport, Registry, load_entry_points, load_modules

from ._source import LogClassifier, LogSource

__all__ = [
    "LOG_CLASSIFIERS_EXTENSION",
    "LOG_CLASSIFIERS_GROUP",
    "LOG_SOURCES_EXTENSION",
    "LOG_SOURCES_GROUP",
    "LoadReport",
    "LogRegistries",
    "as_log_classifier",
    "as_log_source",
]

LOG_SOURCES_GROUP = "agent_console.log_sources"
"""X5 entry point 그룹. 이름 = 출처 id."""

LOG_CLASSIFIERS_GROUP = "agent_console.log_classifiers"
"""X6 entry point 그룹. 이름 = 분류기 id."""

LOG_SOURCES_EXTENSION = "log_sources"
"""레지스트리 이름(호스트 보고 그룹 이름과 같게 쓴다)."""

LOG_CLASSIFIERS_EXTENSION = "log_classifiers"
"""레지스트리 이름(호스트 보고 그룹 이름과 같게 쓴다)."""


def as_log_source(obj: Any) -> LogSource:
    """로드한 객체를 `LogSource`로 검사한다(클래스면 인자 없이 인스턴스화).

    Raises:
        TypeError: 프로토콜·디스크립터가 맞지 않을 때.
    """
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(item, LogSource) or not isinstance(
        getattr(item, "descriptor", None), LogSourceDescriptor
    ):
        raise TypeError(f"log_source가 아닙니다: {obj!r}")
    return item


def as_log_classifier(obj: Any) -> LogClassifier:
    """로드한 객체를 `LogClassifier`로 검사한다(클래스면 인자 없이 인스턴스화).

    Raises:
        TypeError: 프로토콜·디스크립터가 맞지 않을 때.
    """
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(item, LogClassifier) or not isinstance(
        getattr(item, "descriptor", None), LogClassifierDescriptor
    ):
        raise TypeError(f"log_classifier가 아닙니다: {obj!r}")
    return item


class LogRegistries:
    """출처·분류기 레지스트리 한 쌍. 앱이 만들어 주입한다(전역 없음).

    레지스트리 key(entry point 이름)가 id다. 디스크립터 id가 달라도 key를 따른다
    (`source_descriptors`·`classifier_descriptors`가 key로 맞춰 돌려준다).

    Args:
        sources: 기존 출처 레지스트리(없으면 새로 만든다).
        classifiers: 기존 분류기 레지스트리(없으면 새로 만든다).
    """

    def __init__(
        self,
        sources: Registry[LogSource] | None = None,
        classifiers: Registry[LogClassifier] | None = None,
    ) -> None:
        # 빈 레지스트리도 거짓이라 `or`가 아니라 None으로 가른다(주입한 빈 레지스트리를 쓴다).
        self.sources: Registry[LogSource] = (
            sources
            if sources is not None
            else Registry(LOG_SOURCES_EXTENSION, validator=as_log_source)
        )
        self.classifiers: Registry[LogClassifier] = (
            classifiers
            if classifiers is not None
            else Registry(LOG_CLASSIFIERS_EXTENSION, validator=as_log_classifier)
        )

    def load(
        self,
        *,
        enabled_sources: set[str] | None = None,
        enabled_classifiers: set[str] | None = None,
        source_modules: Iterable[str] = (),
        classifier_modules: Iterable[str] = (),
        entry_points: Iterable[EntryPoint] | None = None,
    ) -> dict[str, list[LoadReport]]:
        """entry point(X5·X6)와 명시 모듈 목록에서 등록한다. 실패는 예외 대신 보고서로.

        Args:
            enabled_sources: 주면 이 이름의 출처 entry point만 로드(나머지 `skipped`).
            enabled_classifiers: 분류기에 대해 같은 뜻.
            source_modules: 설치하지 않은 출처 모듈 경로(`"[key=]pkg.mod:attr"`).
            classifier_modules: 분류기 모듈 경로.
            entry_points: 테스트용 주입(주면 설치된 패키지를 훑지 않는다).

        Returns:
            `{"log_sources": [...], "log_classifiers": [...]}` 보고서.
        """
        eps = None if entry_points is None else list(entry_points)
        source_reports = load_entry_points(
            LOG_SOURCES_GROUP,
            self.sources,
            enabled=enabled_sources,
            validate=as_log_source,
            entry_points=None if eps is None else [e for e in eps if e.group == LOG_SOURCES_GROUP],
        )
        source_reports += load_modules(source_modules, self.sources, validate=as_log_source)
        classifier_reports = load_entry_points(
            LOG_CLASSIFIERS_GROUP,
            self.classifiers,
            enabled=enabled_classifiers,
            validate=as_log_classifier,
            entry_points=None
            if eps is None
            else [e for e in eps if e.group == LOG_CLASSIFIERS_GROUP],
        )
        classifier_reports += load_modules(
            classifier_modules, self.classifiers, validate=as_log_classifier
        )
        return {
            LOG_SOURCES_EXTENSION: source_reports,
            LOG_CLASSIFIERS_EXTENSION: classifier_reports,
        }

    def source_descriptors(self) -> list[LogSourceDescriptor]:
        """등록된 출처 디스크립터(key 순, id = key)."""
        return [e.item.descriptor.model_copy(update={"id": e.key}) for e in self.sources.list()]

    def classifier_descriptors(self) -> list[LogClassifierDescriptor]:
        """등록된 분류기 디스크립터(key 순, id = key)."""
        return [e.item.descriptor.model_copy(update={"id": e.key}) for e in self.classifiers.list()]
