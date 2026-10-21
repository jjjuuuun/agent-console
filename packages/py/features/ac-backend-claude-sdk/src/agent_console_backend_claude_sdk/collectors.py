"""claude-sdk 관측 수집기(X7) 공개 하위 모듈(design §4R.3).

- 프로토콜·문맥: ``ClaudeSdkCollector``, ``CollectorContext``, ``CollectedEvent``, 베이스
  ``BaseClaudeSdkCollector``(기본 구현 + pydantic 설정 모델 검증)
- 기본 수집기(첫 구현, entry point로 등록): ``SdkHooksCollector``(`sdk-hooks`),
  ``McpCallsCollector``(`mcp-calls`)
- 로딩: ``COLLECTORS_GROUP``(entry point 그룹 `agent_console.collectors`), ``as_collector``(검사기),
  ``discover_collectors``(entry point → 백엔드 id로 거른 목록 + 보고서), ``default_collectors``,
  ``select_collectors``(백엔드 id로 거르기·id 중복 제거)
- 설정: ``resolve_collector_settings``(`observe.collectors` + 옛 키 `hooks`·`mcp`·`hook_events`),
  ``ResolvedCollector``, ``LEGACY_OBSERVE_KEYS``
- 실행 부품: ``CollectorRun``(켜진 수집기 디스패처, 예외 격리)
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import EntryPoint
from typing import Any

from agent_console_registry import LoadReport, Registry, load_entry_points

from ._collector_api import (
    LEGACY_OBSERVE_KEYS,
    BaseClaudeSdkCollector,
    ClaudeSdkCollector,
    CollectedEvent,
    CollectorContext,
    ResolvedCollector,
    resolve_collector_settings,
)
from ._collector_builtin import (
    McpCallsCollector,
    McpCallsConfig,
    SdkHooksCollector,
    SdkHooksConfig,
)
from ._collector_run import COLLECTOR_ERROR_MESSAGE, CollectorRun
from ._options import CLAUDE_SDK_BACKEND_ID

__all__ = [
    "COLLECTORS_GROUP",
    "COLLECTOR_ERROR_MESSAGE",
    "LEGACY_OBSERVE_KEYS",
    "BaseClaudeSdkCollector",
    "ClaudeSdkCollector",
    "CollectedEvent",
    "CollectorContext",
    "CollectorRun",
    "McpCallsCollector",
    "McpCallsConfig",
    "ResolvedCollector",
    "SdkHooksCollector",
    "SdkHooksConfig",
    "as_collector",
    "default_collectors",
    "discover_collectors",
    "resolve_collector_settings",
    "select_collectors",
]

COLLECTORS_GROUP = "agent_console.collectors"
"""관측 수집기 entry point 그룹(X7). 백엔드마다 `descriptor.backend`로 거른다."""


def as_collector(obj: Any) -> ClaudeSdkCollector:
    """로드한 객체 → 수집기(클래스면 인자 없이 만든다). 프로토콜 모양이 아니면 `TypeError`."""
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(item, ClaudeSdkCollector):
        raise TypeError(f"claude-sdk 수집기가 아니다: {obj!r}")
    return item


def default_collectors(backend: str = CLAUDE_SDK_BACKEND_ID) -> list[ClaudeSdkCollector]:
    """이 패키지의 기본 수집기(`backend`용 인스턴스). entry point 탐색 없이 쓸 때."""
    return [SdkHooksCollector(backend=backend), McpCallsCollector(backend=backend)]


def select_collectors(collectors: Iterable[Any], backend: str) -> list[ClaudeSdkCollector]:
    """`descriptor.backend == backend`인 수집기만 고른다. id가 겹치면 앞의 것이다
    (검사기 `as_collector` 적용)."""
    out: dict[str, ClaudeSdkCollector] = {}
    for obj in collectors:
        item = as_collector(obj)
        if item.descriptor.backend != backend:
            continue
        out.setdefault(item.descriptor.id, item)
    return list(out.values())


def discover_collectors(
    backend: str = CLAUDE_SDK_BACKEND_ID,
    *,
    entry_points: Iterable[EntryPoint] | None = None,
    include_defaults: bool = True,
) -> tuple[list[ClaudeSdkCollector], list[LoadReport]]:
    """entry point 그룹 `agent_console.collectors`에서 수집기를 읽어 `backend`로 거른다.

    Args:
        backend: 백엔드 id(`descriptor.backend`와 맞춘다).
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다). None이면 설치된 패키지에서 찾는다.
        include_defaults: 참이면 기본 수집기 중 entry point로 오지 않은 것을 뒤에 더한다
            (패키지 메타데이터 없이 소스로 쓸 때도 기본 수집기가 있게).

    Returns:
        (수집기 목록, 로딩 보고서). 로딩 실패는 예외가 아니라 보고서(`failed`)다.
    """
    registry: Registry[ClaudeSdkCollector] = Registry("collectors", validator=as_collector)
    eps = (
        None
        if entry_points is None
        else [ep for ep in entry_points if ep.group == COLLECTORS_GROUP]
    )
    reports = load_entry_points(COLLECTORS_GROUP, registry, entry_points=eps)
    found = [entry.item for entry in registry.list()]
    if include_defaults:
        found = [*found, *default_collectors(backend)]
    return select_collectors(found, backend), reports
