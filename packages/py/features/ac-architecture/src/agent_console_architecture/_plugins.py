"""구조도 프로필 플러그인(X23, entry point `agent_console.architecture_profiles`).

entry point 하나 = 인자 없는 함수(또는 객체) → `{프로필 id: 프로필 데이터}`. 로그 출처 플러그인이
자기 형식용 프로필을 함께 낼 때 쓴다. 출처 이름은 `plugin:<배포 이름>`이다.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from agent_console_contracts.architecture import KnownArchitectureOrigins
from agent_console_registry import LoadReport, Registry, load_entry_points

from ._catalog import ProfileSource
from ._document import profiles_from_mapping

ARCHITECTURE_PROFILES_GROUP: Final = "agent_console.architecture_profiles"
"""X23 entry point 그룹."""

ARCHITECTURE_PROFILES_EXTENSION: Final = "architecture_profiles"
"""레지스트리 이름."""


def as_profile_source(obj: Any, *, origin: str) -> ProfileSource:
    """로드한 객체 → `ProfileSource`.

    받는 모양: 인자 없는 함수(호출 결과를 쓴다), `{id: 프로필 데이터}`, `{"profiles": {...}}`.
    값이 이미 `ArchitectureProfile`이어도 된다.

    Raises:
        TypeError: 객체 모양이 아닐 때.
        ValueError: 프로필 형식이 틀렸을 때(`ProfileDocumentError`).
    """
    data = obj() if callable(obj) and not isinstance(obj, Mapping) else obj
    if not isinstance(data, Mapping):
        raise TypeError(f"구조도 프로필 플러그인은 {{id: 프로필}}을 내야 한다: {type(data)!r}")
    if "profiles" in data and isinstance(data["profiles"], Mapping):
        data = data["profiles"]
    return ProfileSource(origin=origin, profiles=profiles_from_mapping({"profiles": data}))


def new_profile_registry(name: str = ARCHITECTURE_PROFILES_EXTENSION) -> Registry[ProfileSource]:
    """빈 프로필 플러그인 레지스트리(key = entry point 이름)."""
    return Registry(name)


def _origin(ep: importlib.metadata.EntryPoint) -> str:
    dist = getattr(ep, "dist", None)
    name = dist.name if dist is not None else ep.name
    return f"{KnownArchitectureOrigins.PLUGIN_PREFIX}{name}"


def load_profile_plugins(
    registry: Registry[ProfileSource],
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point 그룹 `agent_console.architecture_profiles`를 `registry`에 로드한다.

    Args:
        registry: 대상(보통 `new_profile_registry()`).
        enabled: 주어지면 이 이름만 로드(나머지는 `skipped`).
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다). None이면 설치된 패키지에서 찾는다.

    Returns:
        항목별 `LoadReport`(이름 순). 실패는 예외가 아니라 보고에 담긴다.
    """
    eps = (
        [ep for ep in entry_points if ep.group == ARCHITECTURE_PROFILES_GROUP]
        if entry_points is not None
        else list(importlib.metadata.entry_points(group=ARCHITECTURE_PROFILES_GROUP))
    )
    reports: list[LoadReport] = []
    for ep in sorted(eps, key=lambda e: (e.name, e.value)):
        origin = _origin(ep)

        def validate(obj: Any, origin: str = origin) -> ProfileSource:
            return as_profile_source(obj, origin=origin)

        validator: Callable[[Any], ProfileSource] = validate
        reports.extend(
            load_entry_points(
                ARCHITECTURE_PROFILES_GROUP,
                registry,
                enabled=enabled,
                validate=validator,
                entry_points=[ep],
            )
        )
    return reports


def plugin_sources(registry: Registry[ProfileSource]) -> list[ProfileSource]:
    """레지스트리의 프로필 묶음(key 순). `merge_profiles(plugins=...)`에 넘긴다."""
    return [entry.item for entry in sorted(registry.list(), key=lambda e: e.key)]
