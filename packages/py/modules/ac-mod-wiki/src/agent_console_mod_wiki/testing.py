"""단독 실행·테스트용 모듈과 가짜(공개). 실제 연동이 아니다.

- ``local_settings_module``: ``workspace.settings``를 워크스페이스 폴더의 ``settings.yaml``로 주는
  작은 모듈. 단독 실행이 ``--with`` 없이 실행되면 붙는다(통합 서버에서는 ``mod-definitions``가
  대신한다).
- ``static_settings_module``: 주어진 설정(매핑 또는 그것을 돌려주는 함수)을 주는 모듈.
- ``SimpleWikiSpace``·``spaces_module``: ``wiki.spaces``를 공간 이름 → 공간 표로 주는
  모듈(``link-projects-wiki`` 대신).
- ``integration_module``: ``wiki.integrations``에 능력 선언 하나를 주는 모듈(``link-wiki-runs``
  대신, 예: ``{"runs"}``).
- ``write_check_module``: ``wiki.write_checks``에 쓰기 검사 하나를 주는 모듈.
- ``FrontMatterKeyCheck``: 쓰기 검사(X50) 예제. 머리말 키 하나가 없으면 거부한다. import 가능한
  고정 경로라 entry point 값(``agent_console_mod_wiki.testing:FrontMatterKeyCheck``)으로도 쓴다.
- ``library_module``: ``definitions.store``(라이브러리 저장소)를 주는 모듈
  (``mod-definitions`` 대신).
- ``records_module``: ``records.spaces``를 주는 모듈(``link-projects-records`` 대신).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_console_contracts import WorkspaceSettings
from agent_console_contracts.wiki import WikiIssue
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import (
    SETTINGS_KIND,
    DefinitionStore,
    FileDefinitionStore,
    NotFound,
    RecordsSpaces,
)
from agent_console_wiki import WikiWriteCheck

from .ports import (
    DEFINITIONS_STORE,
    RECORDS_SPACES,
    WIKI_INTEGRATIONS,
    WIKI_SPACES,
    WIKI_WRITE_CHECKS,
    WORKSPACE_SETTINGS,
    WikiSpace,
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
class SimpleWikiSpace:
    """``WikiSpace`` 예제 구현(테스트·다른 앱에서 그대로 쓴다).

    Attributes:
        store: 그 공간의 정의 저장소. pages_root: 페이지 폴더의 부모(절대 경로).
        config_writable: 쓸 수 있나. config_dir: 저장소 폴더(폴더 기준 상대 경로).
        index_dir: 검색 색인 폴더(None = 메모리).
    """

    store: DefinitionStore
    pages_root: Path
    config_writable: bool = True
    config_dir: str = ""
    index_dir: Path | None = None


class SimpleWikiSpaces:
    """``wiki.spaces`` 예제 구현: 이름 → 공간 표(없는 이름은 ``KeyError`` → 404)."""

    def __init__(self, spaces: Mapping[str, WikiSpace]) -> None:
        self.spaces = dict(spaces)

    def open(self, space: str) -> WikiSpace:
        return self.spaces[space]


def spaces_module(spaces: Mapping[str, WikiSpace], module_id: str = "test-wiki-spaces") -> Module:
    """``wiki.spaces``를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(WIKI_SPACES, SimpleWikiSpaces(spaces))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WIKI_SPACES], on_build=build)


@dataclass(frozen=True)
class SimpleIntegration:
    """``WikiIntegration`` 예제 구현."""

    id: str
    capabilities: Collection[str] = field(default_factory=frozenset)


def integration_module(
    capabilities: Collection[str], module_id: str = "test-wiki-integration"
) -> Module:
    """``wiki.integrations``에 능력 선언 하나를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(WIKI_INTEGRATIONS, SimpleIntegration(module_id, frozenset(capabilities)))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WIKI_INTEGRATIONS], on_build=build)


class FrontMatterKeyCheck:
    """쓰기 검사(X50) 예제: 머리말 키 하나가 없으면 거부한다.

    키 이름은 옵션 ``key``, 검사 id는 ``needs-key``다.

    삭제 변경과 키가 비어 있는 경우는 통과시킨다.
    """

    def __init__(self, options: Mapping[str, Any] | None = None) -> None:
        self.key = str((options or {}).get("key") or "")
        self.id = "needs-key"

    def check(self, subject: Mapping[str, Any], text: str) -> Sequence[WikiIssue]:
        """``subject["page"]["front_matter"]``에 ``key``가 없으면 오류 하나를 돌려준다."""
        front = (subject.get("page") or {}).get("front_matter") or {}
        if not self.key or self.key in front or subject["change"]["op"] == "delete":
            return []
        return [WikiIssue(severity="error", code="x.needs_key", message=f"{self.key} 필요")]


def write_check_module(check: WikiWriteCheck, module_id: str = "test-wiki-check") -> Module:
    """``wiki.write_checks``에 쓰기 검사 하나를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(WIKI_WRITE_CHECKS, check)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[WIKI_WRITE_CHECKS], on_build=build)


def library_module(store: DefinitionStore, module_id: str = "test-library") -> Module:
    """``definitions.store``(라이브러리 저장소)를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(DEFINITIONS_STORE, store)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[DEFINITIONS_STORE], on_build=build)


def records_module(spaces: RecordsSpaces, module_id: str = "test-records") -> Module:
    """``records.spaces``(기록 DB)를 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RECORDS_SPACES, spaces)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[RECORDS_SPACES], on_build=build)


__all__ = [
    "DEFAULT_WORKSPACE",
    "LOCAL_SETTINGS_ID",
    "STATIC_SETTINGS_ID",
    "FrontMatterKeyCheck",
    "SimpleIntegration",
    "SimpleWikiSpace",
    "SimpleWikiSpaces",
    "integration_module",
    "library_module",
    "local_settings_module",
    "records_module",
    "spaces_module",
    "static_settings_module",
    "write_check_module",
]
