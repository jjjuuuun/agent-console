"""폴더 선택 창 코드 제공자 플러그인 로더(entry point ``agent_console.host_plugin_loaders``).

호스트가 시작할 때 entry point ``agent_console.folder_dialogs``(X35)를 묶음의 이름 붙은 확장
``FOLDER_DIALOGS_EXTENSION``에 읽는다. 다른 플러그인 그룹과 같은 규칙으로 설정
``plugins.enabled``·``plugins.disabled``를 따르고, 결과는 ``server-info``의 플러그인 목록에 나온다.
모듈 ``build``는 이 확장의 제공자를 쓴다(묶음이 없으면 설치된 것을 직접 읽는다).
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable
from typing import Any

from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport, Registry, load_entry_points

from .folders import FOLDER_DIALOGS_GROUP, FolderDialogProvider, as_folder_dialog_provider

FOLDER_DIALOGS_EXTENSION = "folder_dialogs"
"""묶음의 확장 이름이자 보고 그룹 이름."""


def dialog_registry(registries: Any) -> Registry[FolderDialogProvider] | None:
    """묶음의 폴더 선택 창 제공자 레지스트리(묶음에 ``extension``이 없으면 None)."""
    extension = getattr(registries, "extension", None)
    if not callable(extension):
        return None
    registry: Registry[FolderDialogProvider] = extension(
        FOLDER_DIALOGS_EXTENSION, validator=as_folder_dialog_provider
    )
    return registry


def registered_providers(registry: Registry[FolderDialogProvider]) -> list[FolderDialogProvider]:
    """레지스트리의 제공자(entry point 이름 순)."""
    return [e.item for e in sorted(registry.list(), key=lambda e: e.key)]


def load_plugins(
    ctx: PluginLoadContext,
    *,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> list[tuple[str, LoadReport]]:
    """``agent_console.folder_dialogs``를 묶음에 읽는다(``ctx.enabled``로 거른다).

    Args:
        ctx: 플러그인 로더 맥락.
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다). None이면 설치된 것.
    """
    registry = dialog_registry(ctx.registries)
    if registry is None:
        return []
    eps = (
        [ep for ep in entry_points if ep.group == FOLDER_DIALOGS_GROUP]
        if entry_points is not None
        else None
    )
    return [
        (FOLDER_DIALOGS_EXTENSION, r)
        for r in load_entry_points(
            FOLDER_DIALOGS_GROUP,
            registry,
            enabled=ctx.enabled,
            validate=as_folder_dialog_provider,
            entry_points=eps,
        )
    ]


__all__ = [
    "FOLDER_DIALOGS_EXTENSION",
    "dialog_registry",
    "load_plugins",
    "registered_providers",
]
