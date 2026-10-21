"""설치된 모듈 찾기: entry point 그룹 ``MODULES_GROUP``(ac-registry 로더 재사용)."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable
from typing import Any

from agent_console_registry import LoadReport, Registry, load_entry_points

from ._module import Module

MODULES_GROUP = "agent_console.server_modules"
"""기능·연동 모듈 공통 entry point 그룹(기본값, 호출자가 바꿀 수 있다)."""


def as_module(obj: Any) -> Module:
    """entry point가 가리키는 값을 ``Module``로 검사한다. 클래스면 인자 없이 만든다.

    Raises:
        TypeError: ``descriptor``·``build``가 없다.
    """
    candidate = obj() if isinstance(obj, type) else obj
    if not isinstance(candidate, Module):
        raise TypeError(f"Module이 아닙니다(descriptor·build 필요): {obj!r}")
    return candidate


def load_installed_modules(
    group: str = MODULES_GROUP,
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> tuple[list[Module], list[LoadReport]]:
    """entry point 그룹에서 모듈을 읽는다(실패는 예외가 아니라 보고).

    Args:
        group: entry point 그룹.
        enabled: 주어지면 이 entry point 이름만 읽는다.
        entry_points: 테스트용 주입.

    Returns:
        (모듈 목록(entry point 이름 순), 로딩 보고).
    """
    registry: Registry[Module] = Registry("server_modules", validator=as_module)
    reports = load_entry_points(group, registry, enabled=enabled, entry_points=entry_points)
    return [entry.item for entry in registry.list()], reports


__all__ = ["MODULES_GROUP", "as_module", "load_installed_modules"]
