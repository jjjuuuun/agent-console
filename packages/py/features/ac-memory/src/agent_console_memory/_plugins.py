"""범위 종류 플러그인(X29, entry point `agent_console.memory_scope_kinds`).

entry point 하나 = 인자 없는 함수(또는 값) → 범위 종류 목록. 받는 모양:

- `MemoryScopeKind` 목록(계산 범위는 `resolver`를 준다),
- `{범위 종류 id: 데이터(label·description·id 틀)}` 객체.

출처는 `plugin:<배포 이름>`이다. 로더는 실패를 예외 대신 `LoadReport`로 돌려준다(호스트 플러그인
로더가 서버 경고로 보인다).
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any, Final

from agent_console_contracts.memory import MemoryScopeKindSpec
from agent_console_registry import LoadReport, Registry, load_entry_points

from ._scope_kinds import MemoryScopeKind, ScopeKindOrigins

MEMORY_SCOPE_KINDS_GROUP: Final = "agent_console.memory_scope_kinds"
"""X29 entry point 그룹."""

MEMORY_SCOPE_KINDS_EXTENSION: Final = "memory_scope_kinds"
"""레지스트리 이름."""


def as_scope_kinds(obj: Any, *, origin: str) -> tuple[MemoryScopeKind, ...]:
    """로드한 객체 → 범위 종류 목록(출처를 `origin`으로 채운다).

    Raises:
        TypeError: 모양이 틀렸을 때.
        ValueError: 범위 종류 id·틀이 규칙에 맞지 않을 때.
    """
    data = obj() if callable(obj) and not isinstance(obj, Mapping) else obj
    out: list[MemoryScopeKind] = []
    if isinstance(data, Mapping):
        for kind_id, spec in data.items():
            if isinstance(spec, MemoryScopeKind):
                out.append(replace(spec, origin=origin, overrides=None))
                continue
            parsed = MemoryScopeKindSpec.model_validate(spec)
            out.append(MemoryScopeKind.from_spec(str(kind_id), parsed, origin=origin))
        return tuple(out)
    if isinstance(data, Iterable) and not isinstance(data, str | bytes):
        for item in data:
            if not isinstance(item, MemoryScopeKind):
                raise TypeError(
                    f"범위 종류 플러그인 항목은 MemoryScopeKind여야 한다: {type(item)!r}"
                )
            MemoryScopeKind.from_spec(
                item.id,
                MemoryScopeKindSpec(label=item.label, id=item.template or ""),
                origin=origin,
            )  # id·틀 검사
            out.append(replace(item, origin=origin, overrides=None))
        return tuple(out)
    raise TypeError(f"범위 종류 플러그인은 목록이나 {{id: 데이터}}를 내야 한다: {type(data)!r}")


def new_scope_kind_registry(
    name: str = MEMORY_SCOPE_KINDS_EXTENSION,
) -> Registry[tuple[MemoryScopeKind, ...]]:
    """빈 범위 종류 플러그인 레지스트리(key = entry point 이름)."""
    return Registry(name)


def _origin(ep: importlib.metadata.EntryPoint) -> str:
    dist = getattr(ep, "dist", None)
    name = dist.name if dist is not None else ep.name
    return f"{ScopeKindOrigins.PLUGIN_PREFIX}{name}"


def load_scope_kind_plugins(
    registry: Registry[tuple[MemoryScopeKind, ...]],
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point 그룹 `agent_console.memory_scope_kinds`를 `registry`에 로드한다.

    Args:
        registry: 대상(보통 `new_scope_kind_registry()`).
        enabled: 주어지면 이 이름만 로드(나머지는 `skipped`).
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다). None이면 설치된 패키지에서 찾는다.

    Returns:
        항목별 `LoadReport`(이름 순). 실패는 예외가 아니라 보고에 담긴다.
    """
    eps = (
        [ep for ep in entry_points if ep.group == MEMORY_SCOPE_KINDS_GROUP]
        if entry_points is not None
        else list(importlib.metadata.entry_points(group=MEMORY_SCOPE_KINDS_GROUP))
    )
    reports: list[LoadReport] = []
    for ep in sorted(eps, key=lambda e: (e.name, e.value)):
        origin = _origin(ep)

        def validate(obj: Any, origin: str = origin) -> tuple[MemoryScopeKind, ...]:
            return as_scope_kinds(obj, origin=origin)

        reports.extend(
            load_entry_points(
                MEMORY_SCOPE_KINDS_GROUP,
                registry,
                enabled=enabled,
                validate=validate,
                entry_points=[ep],
            )
        )
    return reports


def plugin_scope_kinds(registry: Registry[tuple[MemoryScopeKind, ...]]) -> list[MemoryScopeKind]:
    """레지스트리의 범위 종류(entry point 이름 순). `merge_scope_kinds(plugins=...)`에 넘긴다."""
    out: list[MemoryScopeKind] = []
    for entry in sorted(registry.list(), key=lambda e: e.key):
        out.extend(entry.item)
    return out
