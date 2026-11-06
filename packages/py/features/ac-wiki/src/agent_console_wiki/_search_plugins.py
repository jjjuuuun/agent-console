"""검색 색인 플러그인(X48, entry point `agent_console.wiki_search_indexes`)과 기본 구현 등록.

entry point 하나 = 인자 없는 함수 → 색인 **공장** `(root, options) -> WikiSearchIndex`.
이름 = 백엔드 id.
`root`는 색인 파일 위치(파일을 쓰지 않는 구현은 무시; 위치는 호출자가 정한다). `options`는 설치자·
사용자 설정에서 온 값(`tokenizer`·`case_insensitive`·`redact`·`redact_signature`와
`SearchLimits` 필드).
로더는 실패를 예외 대신 `LoadReport`로 돌려준다.
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from agent_console_registry import LoadReport, Registry, load_entry_points

from ._search import ScanSearchIndex, SearchLimits, WikiSearchIndex

__all__ = [
    "SEARCH_INDEX_GROUP",
    "SearchIndexFactory",
    "builtin_search_factories",
    "load_search_plugins",
    "new_search_registry",
    "register_builtin_search",
]

SEARCH_INDEX_GROUP: Final = "agent_console.wiki_search_indexes"
"""X48 entry point 그룹."""

SearchIndexFactory = Callable[[Path | None, Mapping[str, Any]], WikiSearchIndex]
"""`(색인 파일 위치, 옵션) -> 색인`."""


def _limits(options: Mapping[str, Any]) -> SearchLimits:
    names = {f.name for f in dataclasses.fields(SearchLimits)}
    return SearchLimits(**{k: int(v) for k, v in options.items() if k in names and v is not None})


def _scan(root: Path | None, options: Mapping[str, Any]) -> WikiSearchIndex:
    return ScanSearchIndex(
        case_insensitive=bool(options.get("case_insensitive", True)),
        redact=options.get("redact"),
        limits=_limits(options),
    )


def _sqlite_fts(root: Path | None, options: Mapping[str, Any]) -> WikiSearchIndex:
    from .sqlite import SqliteFtsSearchIndex

    return SqliteFtsSearchIndex(
        root,
        tokenizer=str(options.get("tokenizer") or "trigram"),
        case_insensitive=bool(options.get("case_insensitive", True)),
        redact=options.get("redact"),
        redact_signature=str(options.get("redact_signature", "")),
        limits=_limits(options),
    )


def builtin_search_factories() -> dict[str, SearchIndexFactory]:
    """패키지 기본 공장: `scan`·`sqlite-fts`."""
    return {"scan": _scan, "sqlite-fts": _sqlite_fts}


def new_search_registry(name: str = "wiki_search_indexes") -> Registry[SearchIndexFactory]:
    """빈 검색 색인 레지스트리(key = 백엔드 id)."""
    return Registry(name)


def register_builtin_search(registry: Registry[SearchIndexFactory]) -> None:
    """기본 공장을 `registry`에 넣는다(출처 `builtin`)."""
    for key, factory in builtin_search_factories().items():
        registry.register(key, factory, source="builtin")


def _as_factory(obj: Any) -> SearchIndexFactory:
    factory = obj() if callable(obj) else obj
    if not callable(factory):
        raise TypeError(f"검색 색인 플러그인은 (root, options) 공장을 내야 한다: {type(factory)!r}")
    return factory  # type: ignore[no-any-return]


def load_search_plugins(
    registry: Registry[SearchIndexFactory],
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point 그룹 `agent_console.wiki_search_indexes`를 `registry`에 로드한다.

    Args:
        registry: 대상(보통 `new_search_registry()` + `register_builtin_search`).
        enabled: 주어지면 이 이름만 로드(나머지는 `skipped`).
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다). None이면 설치된 패키지에서 찾는다.

    Returns:
        항목별 `LoadReport`(이름 순). 실패(같은 id 겹침 포함)는 예외가 아니라 보고에 담긴다.
    """
    eps = None
    if entry_points is not None:
        eps = [ep for ep in entry_points if ep.group == SEARCH_INDEX_GROUP]
    return load_entry_points(
        SEARCH_INDEX_GROUP, registry, enabled=enabled, validate=_as_factory, entry_points=eps
    )
