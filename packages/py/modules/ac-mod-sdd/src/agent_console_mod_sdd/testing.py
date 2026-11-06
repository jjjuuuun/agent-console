"""단독 실행·테스트용 모듈과 가짜(공개). 실제 연동이 아니다.

- ``local_settings_module``: ``workspace.settings``를 워크스페이스 폴더의 ``settings.yaml``로 주는
  작은 모듈. 단독 실행이 ``--with`` 없이 실행되면 붙는다(통합 서버에서는 ``mod-definitions``가
  대신한다).
- ``static_settings_module``: 주어진 설정(매핑 또는 그것을 돌려주는 함수)을 주는 모듈.
- ``spaces_module``: ``sdd.spaces``를 공간 이름 → ``SimpleSpace`` 표로 주는
  모듈(``link-projects-sdd``
  대신).
- ``integration_module``·``verification_module``: 작업 연동(X43)·검증 출처(X42)를 포트로 주는 모듈.
- ``library_module``: ``definitions.store``(라이브러리 저장소)를 주는 모듈(``mod-definitions``
  대신).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_contracts import WorkspaceSettings
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_sdd import SpecFiles, TaskIntegration, VerificationSource
from agent_console_store import SETTINGS_KIND, DefinitionStore, FileDefinitionStore, NotFound

from .ports import (
    DEFINITIONS_STORE,
    SDD_INTEGRATIONS,
    SDD_SPACES,
    SDD_VERIFICATION_SOURCES,
    WORKSPACE_SETTINGS,
    SddSpace,
)

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
    """``workspace.settings`` 제공 모듈(``<workspace>/settings.yaml``, 없으면 기본값)."""

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)
        store = FileDefinitionStore(root, (SETTINGS_KIND,))
        ctx.provide(WORKSPACE_SETTINGS, lambda: _read_settings(store))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WORKSPACE_SETTINGS], on_build=build)


def static_settings_module(settings: Any, module_id: str = STATIC_SETTINGS_ID) -> Module:
    """주어진 설정을 ``workspace.settings``로 주는 모듈(함수면 부를 때마다 읽는다)."""
    reader: Callable[[], Any] = settings if callable(settings) else (lambda: settings)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(WORKSPACE_SETTINGS, reader)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WORKSPACE_SETTINGS], on_build=build)


@dataclass
class SimpleSpace:
    """``SddSpace`` 예제 구현(테스트·다른 앱에서 그대로 쓴다).

    Attributes:
        store: 그 공간의 정의 저장소. files: 폴더 안 파일 접근(None = 가져오기·내보내기 꺼짐).
        config_writable: 쓸 수 있나. config_dir: 저장소 폴더(폴더 기준 상대 경로).
    """

    store: DefinitionStore
    files: SpecFiles | None = None
    config_writable: bool = True
    config_dir: str = ""


class SimpleSpaces:
    """``sdd.spaces`` 예제 구현: 이름 → 공간 표(없는 이름은 ``KeyError`` → 404)."""

    def __init__(self, spaces: Mapping[str, SddSpace]) -> None:
        self.spaces = dict(spaces)

    def open(self, space: str) -> SddSpace:
        return self.spaces[space]


def spaces_module(spaces: Mapping[str, SddSpace], module_id: str = "test-sdd-spaces") -> Module:
    """``sdd.spaces``를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(SDD_SPACES, SimpleSpaces(spaces))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[SDD_SPACES], on_build=build)


def integration_module(
    integration: TaskIntegration, module_id: str = "test-sdd-integration"
) -> Module:
    """``sdd.integrations``에 작업 연동 하나를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(SDD_INTEGRATIONS, integration)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[SDD_INTEGRATIONS], on_build=build)


def verification_module(
    source: VerificationSource, module_id: str = "test-sdd-verification"
) -> Module:
    """``sdd.verification_sources``에 검증 출처 하나를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(SDD_VERIFICATION_SOURCES, source)
        return ModuleParts()

    return fake_module(
        module_id, kind="testing", provides=[SDD_VERIFICATION_SOURCES], on_build=build
    )


def library_module(store: DefinitionStore, module_id: str = "test-library") -> Module:
    """``definitions.store``(라이브러리 저장소)를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(DEFINITIONS_STORE, store)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[DEFINITIONS_STORE], on_build=build)


__all__ = [
    "DEFAULT_WORKSPACE",
    "LOCAL_SETTINGS_ID",
    "STATIC_SETTINGS_ID",
    "SimpleSpace",
    "SimpleSpaces",
    "integration_module",
    "library_module",
    "local_settings_module",
    "spaces_module",
    "static_settings_module",
    "verification_module",
]
