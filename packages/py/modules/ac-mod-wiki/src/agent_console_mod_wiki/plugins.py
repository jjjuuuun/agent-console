"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, X18).

위키 검색 색인(X48)과 쓰기 검사(X50).

- 검색 색인: entry point 그룹 ``agent_console.wiki_search_indexes``(``agent_console_wiki``가 정한
  그룹)를 호스트 묶음의 ``wiki_search_indexes`` 확장에 로드한다. 패키지 기본 색인(``scan``·
  ``sqlite-fts``)도 같은 레지스트리에 넣는다. 쓸 색인은 사용자 설정 ``wiki.search_backend`` →
  설치자 ``search.backend`` 순으로 고른다.
- 쓰기 검사: entry point 그룹 ``agent_console.wiki_write_checks``의 항목을 ``wiki_write_checks``
  확장에 로드한다. 항목 값은 ``WikiWriteCheck`` 객체이거나 옵션 매핑 하나를 받아 그것을 만드는 함수
  (클래스)다. 로드한 검사는 **사용자 설정** ``wiki.write_checks``에
  ``{id, enabled: true, options}``로 적어야 쓰인다(설치만으로 쓰기 판단이 바뀌지 않는다).
  ``id`` = entry point 이름.

설정 ``plugins.enabled``로 끈 항목은 읽지 않는다. 실패(모양 틀림·id 겹침)는 예외 대신 보고다.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport, Registry, load_entry_points
from agent_console_wiki import (
    SearchIndexFactory,
    WikiWriteCheck,
    builtin_search_factories,
    load_search_plugins,
    new_search_registry,
)

SEARCH_EXTENSION: Final = "wiki_search_indexes"
"""호스트 레지스트리 묶음의 검색 색인 확장 이름(보고 그룹 이름도 같다)."""
WRITE_CHECKS_GROUP: Final = "agent_console.wiki_write_checks"
"""쓰기 검사 플러그인 entry point 그룹(X50)."""
WRITE_CHECKS_EXTENSION: Final = "wiki_write_checks"
"""호스트 레지스트리 묶음의 쓰기 검사 확장 이름(보고 그룹 이름도 같다)."""

type WriteCheckFactory = Callable[[Mapping[str, Any]], WikiWriteCheck]
"""옵션(사용자 설정 ``wiki.write_checks[].options`` 사본) → 쓰기 검사."""


def _is_check(obj: Any) -> bool:
    return (
        not isinstance(obj, type)
        and callable(getattr(obj, "check", None))
        and isinstance(getattr(obj, "id", None), str)
    )


def as_write_check_factory(obj: Any) -> WriteCheckFactory:
    """레지스트리 검사기: ``WikiWriteCheck`` 객체(옵션을 받지 않음) 또는 옵션을 받는 함수·클래스.

    함수가 만든 값의 모양은 쓸 때 다시 본다(``make_write_check``).

    Raises:
        TypeError: 둘 다 아닐 때.

    >>> class Check:
    ...     id = "x"
    ...     def check(self, subject, text):
    ...         return []
    >>> as_write_check_factory(Check())({}).id
    'x'
    """
    if _is_check(obj):
        return lambda _options: obj
    if callable(obj):
        return obj  # type: ignore[no-any-return]
    raise TypeError(
        "쓰기 검사는 id와 check(subject, text)가 있는 객체 또는 옵션을 받아 그것을 만드는 함수"
        f"여야 합니다: {type(obj).__name__}"
    )


def make_write_check(factory: WriteCheckFactory, options: Mapping[str, Any]) -> WikiWriteCheck:
    """공장으로 검사 하나를 만든다.

    Raises:
        TypeError: 만든 값이 검사 모양이 아님. 공장의 예외는 그대로 전한다.
    """
    made = factory(dict(options))
    if not _is_check(made):
        raise TypeError(f"쓰기 검사 공장이 검사가 아닌 값을 냈습니다: {type(made).__name__}")
    return made


def new_write_check_registry() -> Registry[WriteCheckFactory]:
    """빈 쓰기 검사 레지스트리(key = entry point 이름 = 설정 ``id``)."""
    return Registry(WRITE_CHECKS_EXTENSION, validator=as_write_check_factory)


def load_write_check_plugins(
    registry: Registry[WriteCheckFactory],
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point 그룹 ``agent_console.wiki_write_checks``를 ``registry``에 로드한다.

    Args:
        enabled: 주어지면 이 이름만 로드(나머지는 ``skipped``).
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다).
    """
    eps = (
        [ep for ep in entry_points if ep.group == WRITE_CHECKS_GROUP]
        if entry_points is not None
        else None
    )
    return load_entry_points(
        WRITE_CHECKS_GROUP,
        registry,
        enabled=enabled,
        validate=as_write_check_factory,
        entry_points=eps,
    )


def _add_builtin_search(registry: Registry[SearchIndexFactory]) -> None:
    for key, factory in builtin_search_factories().items():
        if key not in registry:
            registry.register(key, factory, source="builtin")


def search_registry(registries: Any) -> Registry[SearchIndexFactory]:
    """묶음의 검색 색인 레지스트리(+ 패키지 기본 색인). 묶음이 없으면(단독 실행) 설치된 entry
    point로 새로 읽은 레지스트리."""
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[SearchIndexFactory] = extension(SEARCH_EXTENSION)
        _add_builtin_search(found)
        return found
    registry = new_search_registry(SEARCH_EXTENSION)
    _add_builtin_search(registry)
    load_search_plugins(registry)
    return registry


def write_check_registry(registries: Any) -> Registry[WriteCheckFactory]:
    """묶음의 쓰기 검사 레지스트리(없으면 만든다). 묶음이 없으면 설치된 entry point로 새로 읽은
    레지스트리."""
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[WriteCheckFactory] = extension(
            WRITE_CHECKS_EXTENSION, validator=as_write_check_factory
        )
        return found
    registry = new_write_check_registry()
    load_write_check_plugins(registry)
    return registry


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """검색 색인·쓰기 검사 entry point를 묶음의 확장에 로드한다."""
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    search = search_registry(ctx.registries)
    checks = write_check_registry(ctx.registries)
    out: list[tuple[str, LoadReport]] = [
        (SEARCH_EXTENSION, r) for r in load_search_plugins(search, enabled=enabled)
    ]
    out.extend(
        (WRITE_CHECKS_EXTENSION, r) for r in load_write_check_plugins(checks, enabled=enabled)
    )
    return out


__all__ = [
    "SEARCH_EXTENSION",
    "WRITE_CHECKS_EXTENSION",
    "WRITE_CHECKS_GROUP",
    "WriteCheckFactory",
    "as_write_check_factory",
    "load_plugins",
    "load_write_check_plugins",
    "make_write_check",
    "new_write_check_registry",
    "search_registry",
    "write_check_registry",
]
