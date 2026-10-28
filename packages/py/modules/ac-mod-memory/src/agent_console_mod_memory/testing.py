"""단독 실행·테스트용 모듈(공개).

- ``local_settings_module``: ``workspace.settings``를 워크스페이스 폴더의
  ``settings.yaml``(정의 파일 저장소)로 주는 작은 모듈. 단독 실행
  ``python -m agent_console_mod_memory``가 ``--with`` 없이 실행되면 이것을 붙인다(통합
  서버에서는 ``mod-definitions``가 대신한다). 사용자 설정은 그 파일의 ``memory`` 섹션에 적는다.
- ``static_settings_module``: 주어진 설정(``WorkspaceSettings``·매핑, 또는 그것을 돌려주는 함수)을
  주는 모듈.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_console_contracts import WorkspaceSettings
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import SETTINGS_KIND, FileDefinitionStore, NotFound

from .ports import WORKSPACE_SETTINGS

LOCAL_SETTINGS_ID = "local-settings"
STATIC_SETTINGS_ID = "static-settings"
DEFAULT_WORKSPACE = Path(".agent-console")


def _read_settings(store: FileDefinitionStore) -> WorkspaceSettings:
    try:
        stored = store.get(SETTINGS_KIND.name, SETTINGS_KIND.name)
    except NotFound:
        return WorkspaceSettings()
    return stored.model(WorkspaceSettings)


def local_settings_module(
    module_id: str = LOCAL_SETTINGS_ID, *, workspace: Path | None = None
) -> Module:
    """``workspace.settings`` 제공 모듈(``<workspace>/settings.yaml``, 없으면 기본값).

    Args:
        module_id: 모듈 id.
        workspace: 워크스페이스 폴더(없으면 호스트 경로 ``workspace``).
    """

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)
        store = FileDefinitionStore(root, (SETTINGS_KIND,))
        ctx.provide(WORKSPACE_SETTINGS, lambda: _read_settings(store))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WORKSPACE_SETTINGS], on_build=build)


def static_settings_module(settings: Any, module_id: str = STATIC_SETTINGS_ID) -> Module:
    """주어진 설정을 ``workspace.settings``로 주는 모듈(함수면 부를 때마다 읽는다).

    Args:
        settings: ``WorkspaceSettings``, 설정 문서 매핑, 또는 그것을 돌려주는 인자 없는 함수.
        module_id: 모듈 id.
    """
    reader: Callable[[], Any] = settings if callable(settings) else (lambda: settings)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(WORKSPACE_SETTINGS, reader)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WORKSPACE_SETTINGS], on_build=build)


__all__ = [
    "DEFAULT_WORKSPACE",
    "LOCAL_SETTINGS_ID",
    "STATIC_SETTINGS_ID",
    "local_settings_module",
    "static_settings_module",
]
