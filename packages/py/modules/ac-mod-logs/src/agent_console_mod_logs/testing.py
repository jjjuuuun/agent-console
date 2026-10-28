"""단독 실행·테스트용 모듈(공개).

- ``local_settings_module``: ``workspace.settings``를 워크스페이스 폴더의 ``settings.yaml``
  (정의 파일 저장소)로 주는 작은 모듈. 단독 실행 ``python -m agent_console_mod_logs``가 ``--with``
  없이 실행되면 이것을 붙인다(통합 서버에서는 ``mod-definitions``가 대신한다). 로그 출처
  켜기·루트는 그 파일의 ``logs.sources``에 적는다.
- ``static_settings_module``: 주어진 ``WorkspaceSettings``(또는 그것을 돌려주는 함수)를 주는 모듈.
- ``runtime_sources_module``: ``logs.sources``(런타임 출처)를 주는 모듈(연동 모듈 흉내).
- ``RuntimeSource``: ``logs.sources`` 항목 모양(출처 + 분류기)의 간단한 구현.
- ``query_extensions_module``: ``logs.scope_kinds``(X27)·``logs.filter_predicates``(X28)에
  범위 종류·필터 확장을 주는 모듈(연동 모듈 흉내, 가짜는 ``agent_console_logs.testing``의
  ``TableScopeKind``·``FieldFilter``).
- ``project_folders_module``: ``projects.folders``(등록된 프로젝트 폴더)를 주는 모듈
  (``mod-projects`` 흉내). 범위를 아는 출처(``claude-code-jsonl``)는 이 폴더의 기록만 읽는다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_console_contracts import WorkspaceSettings
from agent_console_logs import (
    LogClassifier,
    LogFilterExtension,
    LogScopeKind,
    LogSource,
    ProjectFolders,
)
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import SETTINGS_KIND, FileDefinitionStore, NotFound

from .ports import (
    LOG_FILTER_PREDICATES,
    LOG_SCOPE_KINDS,
    LOG_SOURCES,
    PROJECT_FOLDERS,
    WORKSPACE_SETTINGS,
)

LOCAL_SETTINGS_ID = "local-settings"
STATIC_SETTINGS_ID = "static-settings"
RUNTIME_SOURCES_ID = "runtime-log-sources"
QUERY_EXTENSIONS_ID = "log-query-extensions"
PROJECT_FOLDERS_ID = "project-folders"
DEFAULT_WORKSPACE = Path(".agent-console")


@dataclass(frozen=True)
class RuntimeSource:
    """``logs.sources`` 포트 항목: 출처 + 분류기."""

    source: LogSource
    classifier: LogClassifier


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


def static_settings_module(
    settings: WorkspaceSettings | Callable[[], WorkspaceSettings],
    module_id: str = STATIC_SETTINGS_ID,
) -> Module:
    """주어진 설정을 ``workspace.settings``로 주는 모듈(함수면 부를 때마다 읽는다)."""
    reader: Callable[[], WorkspaceSettings] = settings if callable(settings) else (lambda: settings)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(WORKSPACE_SETTINGS, reader)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WORKSPACE_SETTINGS], on_build=build)


def runtime_sources_module(
    sources: Sequence[RuntimeSource], module_id: str = RUNTIME_SOURCES_ID
) -> Module:
    """``logs.sources``(multi)에 런타임 출처들을 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        for item in sources:
            ctx.provide(LOG_SOURCES, item)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[LOG_SOURCES], on_build=build)


def query_extensions_module(
    scope_kinds: Sequence[LogScopeKind] = (),
    filters: Sequence[LogFilterExtension] = (),
    module_id: str = QUERY_EXTENSIONS_ID,
) -> Module:
    """``logs.scope_kinds``·``logs.filter_predicates``(multi)에 등록을 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        for kind in scope_kinds:
            ctx.provide(LOG_SCOPE_KINDS, kind)
        for ext in filters:
            ctx.provide(LOG_FILTER_PREDICATES, ext)
        return ModuleParts()

    return fake_module(
        module_id,
        kind="testing",
        provides=[LOG_SCOPE_KINDS, LOG_FILTER_PREDICATES],
        on_build=build,
    )


def project_folders_module(
    current: Sequence[Path] = (),
    registered: Sequence[Path] | None = None,
    module_id: str = PROJECT_FOLDERS_ID,
) -> Module:
    """``projects.folders`` 제공 모듈. ``registered``를 비우면 ``current``와 같다."""
    folders = ProjectFolders(
        current=tuple(current),
        registered=tuple(registered if registered is not None else current),
    )

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(PROJECT_FOLDERS, lambda: folders)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[PROJECT_FOLDERS], on_build=build)


__all__ = [
    "LOCAL_SETTINGS_ID",
    "PROJECT_FOLDERS_ID",
    "QUERY_EXTENSIONS_ID",
    "RUNTIME_SOURCES_ID",
    "STATIC_SETTINGS_ID",
    "RuntimeSource",
    "local_settings_module",
    "project_folders_module",
    "query_extensions_module",
    "runtime_sources_module",
    "static_settings_module",
]
