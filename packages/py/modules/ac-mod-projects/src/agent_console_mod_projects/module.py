"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-projects``, design §PI.10).

- 등록부: 워크스페이스(``BaseServices.paths.workspace``)의 ``projects/<id>.yaml``을 자기
  ``FileDefinitionStore`` 인스턴스로 맡는다(정의 모듈 종류 목록은 그대로). 버전 기록은 호스트 DB
  핸들의 정의 버전 표(legacy 계보), 없으면 메모리 — 처음 쓸 때 연다.
- 프로젝트 공간: 등록 폴더의 ``<config_dir>/``(``ac-project-space``). 정의 종류는 라이브러리
  저장소의 종류 정보(``kind_info``)를 그대로 쓴다(해시가 같아 복사 계획의 identical 판정이 맞음).
- 제공: ``projects.lookup``·``projects.folders``·``projects.spaces``·``definitions.spaces``.
- 선택: ``definitions.lookup``·``definitions.store``·``definitions.references``·
  ``definitions.reference_rewriters``·``records.spaces``·``secrets.rules``·
  ``definitions.kind_contributions``(X44 — 공간 종류에 더하고 참조 추출을 복사 계획에 합친다).
  구독 ``definitions.saved``.
- 웹 역할 ``projects``. 이 모듈을 끄면 프로젝트 기능이 없고 각 기능은 단독 동작한다.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_local_folders import CommandRunner, FileSystem, LocalFileSystem, SubprocessRunner
from agent_console_modkit import DatabaseHandle, ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_modkit.host import is_loopback_host
from agent_console_project_space import SpaceLayout
from agent_console_projects import References, load_path_rules
from agent_console_secret_rules import SecretRules, default_rules
from agent_console_store import (
    DEFAULT_KINDS,
    DefinitionKind,
    FileDefinitionStore,
    KindContributionLike,
    LazyVersionRepository,
    ObservedVersionRepository,
    RecordsHandle,
    RecordsUnavailable,
    RecordsVersionRepository,
    StoreError,
    VersionRepository,
    contributed_kinds,
    versions_for,
)

from .copying import CopyService
from .definitions import DefinitionSnapshot, combine_references, contribution_references
from .errors import ERROR_MAP
from .folders import FolderDialogProvider, FolderPicker, FolderService, load_dialog_providers
from .ports import (
    DEFINITIONS_LOOKUP,
    DEFINITIONS_REFERENCES,
    DEFINITIONS_REWRITERS,
    DEFINITIONS_SAVED,
    DEFINITIONS_SPACES,
    DEFINITIONS_STORE,
    KIND_CONTRIBUTIONS,
    PROJECT_FOLDERS,
    PROJECTS_LOOKUP,
    PROJECTS_SPACES,
    RECORDS_SPACES,
    SECRET_RULES,
    DefinitionReader,
    SavedLike,
)
from .projects import ProjectManager
from .repository import PROJECT_KIND_NAME, ProjectRepository, project_kind
from .routes import Services, build_router
from .service import ScopeService
from .settings import SETTINGS_COMPAT, ProjectModuleSettings
from .spaces import DefinitionSpacesView, ProjectSpaceCache, VersionsFactory


@dataclass(frozen=True)
class SpaceSaved:
    """공간 저장 알림(``definitions.saved`` 항목 + 공간 이름 = 등록 id, 33x)."""

    kind: str
    id: str
    version_hash: str
    space: str | None = None


MODULE_ID = "mod-projects"
WEB_ROLES: tuple[str, ...] = ("projects",)
"""웹 라우트 역할(design §5.2R.6 표 1)."""

DEFAULT_WORKSPACE = Path(".agent-console")
"""호스트가 경로를 주지 않을 때(테스트 등) 쓰는 워크스페이스 폴더."""


def _version() -> str:
    try:
        return version("agent-console-mod-projects")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def open_versions(database: DatabaseHandle | None) -> VersionRepository:
    """등록부 버전 기록소를 연다(처음 쓸 때만). DB가 있으면 legacy 계보를 올리고(멱등) 그 DB의 정의
    버전 표를, 없으면 메모리를 쓴다. 프로젝트를 쓰지 않는 서버는 DB 파일을 만들지 않는다."""
    if database is not None:
        database.upgrade()
    return versions_for(database)


def library_kinds(
    store: Any, contributions: Iterable[KindContributionLike] = ()
) -> list[DefinitionKind]:
    """프로젝트 공간에 쓸 종류 정보.

    라이브러리 저장소의 종류(``kind_info``가 없으면 ``ac-store`` 기본 종류에서 이름이 같은 것,
    저장소가 없으면 기본 종류) + 종류 기여(X44, ``library=False`` 포함) 중 이름이 없는 것.
    기여가 없으면 6R.5 전과 같다. 옮길 수 있는지(``is_portable``)는 공간이 거른다.
    """
    out = list(DEFAULT_KINDS) if store is None else _store_kinds(store)
    reserved = {k.name for k in out} | {PROJECT_KIND_NAME}
    out.extend(contributed_kinds(contributions, reserved=reserved))
    return out


def _store_kinds(store: Any) -> list[DefinitionKind]:
    info = getattr(store, "kind_info", None)
    defaults = {k.name: k for k in DEFAULT_KINDS}
    out: list[DefinitionKind] = []
    for name in store.kinds():
        if name == PROJECT_KIND_NAME:
            continue
        kind: Any = None
        if callable(info):
            try:
                kind = info(name)
            except StoreError:
                kind = None
        kind = kind if isinstance(kind, DefinitionKind) else defaults.get(name)
        if kind is not None:
            out.append(kind)
    return out


class ProjectsModule:
    """프로젝트 기능 모듈.

    Args:
        runner: 선택 창 명령 실행기(기본 ``SubprocessRunner``). 테스트는 가짜를 넣는다.
        dialog_providers: 코드 선택 창 제공자(기본 entry point ``agent_console.folder_dialogs``).
        platform: 서버 플랫폼(기본 ``sys.platform``).
        which: 실행 파일 찾기(기본 ``shutil.which``).
        fs: 폴더 상태 읽기(기본 ``LocalFileSystem``).
        versions: 프로젝트 공간 버전 기록소 공장. 기본 = `records.spaces`가 있으면 그 폴더 기록 DB
            (`RecordsVersionRepository`, 저장마다 `definitions.saved`에 `space`), 없으면
            메모리(33x).
    """

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="프로젝트",
        description="프로젝트 폴더를 등록하고 프로젝트마다 구성을 따로 둔다",
        provides=(PROJECTS_LOOKUP, PROJECT_FOLDERS, PROJECTS_SPACES, DEFINITIONS_SPACES),
        optional=(
            DEFINITIONS_LOOKUP,
            DEFINITIONS_STORE,
            DEFINITIONS_REFERENCES,
            DEFINITIONS_REWRITERS,
            RECORDS_SPACES,
            SECRET_RULES,
            KIND_CONTRIBUTIONS,
        ),
        settings_schema=ProjectModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"projects": CONTRACT_VERSIONS["projects"]},
        web_roles=WEB_ROLES,
    )

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        dialog_providers: Sequence[FolderDialogProvider] | None = None,
        platform: str | None = None,
        which: Callable[[str], str | None] | None = None,
        fs: FileSystem | None = None,
        versions: VersionsFactory | None = None,
    ) -> None:
        self._runner = runner
        self._providers = dialog_providers
        self._platform = platform
        self._which = which
        self._fs = fs
        self._versions = versions

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ProjectModuleSettings):
            cfg = ProjectModuleSettings()
        root = ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE
        base_dir = (ctx.paths.base_dir if ctx.paths is not None else Path(".")).absolute()
        database = ctx.database
        store = FileDefinitionStore(
            root,
            [project_kind(cfg.directory)],
            versions=LazyVersionRepository(lambda: open_versions(database)),
        )
        repository = ProjectRepository(store)
        fs = self._fs or LocalFileSystem()
        environ: Mapping[str, str] = ctx.environ
        rules = load_path_rules({"case_insensitive": list(cfg.case_insensitive_paths)})
        layout = SpaceLayout(records_file=cfg.records_file) if cfg.records_file else SpaceLayout()

        def library() -> Any:
            return ctx.port(DEFINITIONS_STORE)

        def reader() -> DefinitionReader | None:
            return ctx.port(DEFINITIONS_LOOKUP) or ctx.port(DEFINITIONS_STORE)

        def secret_rules() -> SecretRules:
            port = ctx.port(SECRET_RULES)
            return port() if port is not None else default_rules()

        def space_options() -> dict[str, Any]:
            return {
                "kinds": library_kinds(reader(), ctx.ports(KIND_CONTRIBUTIONS)),
                "config_dir": cfg.config_dir,
                "layout": layout,
                "secret_rules": secret_rules(),
            }

        manager_ref: list[ProjectManager] = []

        def folder_of(project_id: str) -> str | None:
            return manager_ref[0].folder_of(project_id)

        def records_versions(project_id: str, _root: Path) -> VersionRepository | None:
            """기본 공간 버전 기록소(33x): 그 폴더 기록 DB(``records.spaces``), 없으면 메모리."""
            if ctx.port(RECORDS_SPACES) is None:
                return None
            name = cfg.records_space_prefix + project_id

            def handle() -> RecordsHandle:
                port = ctx.port(RECORDS_SPACES)
                if port is None:
                    raise RecordsUnavailable("link_disabled")
                return port.open(name)

            def saved(kind: str, item_id: str, version_hash: str) -> None:
                ctx.publish(DEFINITIONS_SAVED, SpaceSaved(kind, item_id, version_hash, project_id))

            return ObservedVersionRepository(RecordsVersionRepository(handle), saved)

        spaces = ProjectSpaceCache(
            folder_of,
            options=space_options,
            max_open=cfg.max_open_spaces,
            idle_seconds=cfg.idle_close_seconds,
            versions=self._versions or records_versions,
        )
        manager = ProjectManager(
            repository,
            fs=fs,
            spaces=spaces,
            space_options=space_options,
            base_dir=base_dir,
            rules=rules,
            records=lambda: ctx.port(RECORDS_SPACES),
            records_prefix=cfg.records_space_prefix,
            status_timeout=cfg.status_timeout_seconds,
            environ=environ,
            config_dir=cfg.config_dir,
        )
        manager_ref.append(manager)

        loopback = is_loopback_host(cfg.server_host or "127.0.0.1")
        folders = FolderService(
            fs=fs,
            registered=manager.registered,
            taken_ids=repository.ids,
            space_options=space_options,
            allowed=lambda: loopback or cfg.allow_remote_browse,
            environ=environ,
            roots=cfg.browse_roots,
            rules=rules,
            config_dir=cfg.config_dir,
        )
        picker = FolderPicker(
            settings=cfg.folder_dialog,
            runner=self._runner or SubprocessRunner(),
            providers=(self._providers if self._providers is not None else load_dialog_providers()),
            loopback=lambda: loopback,
            platform=self._platform or sys.platform,
            which=self._which or shutil.which,
            environ=environ,
            fs=fs,
            check=folders.check_path,
        )

        def references() -> References | None:
            return combine_references(
                [
                    *ctx.ports(DEFINITIONS_REFERENCES),
                    *contribution_references(ctx.ports(KIND_CONTRIBUTIONS)),
                ]
            )

        copies = CopyService(
            library=library,
            spaces=spaces,
            known=lambda pid: repository.find(pid) is not None,
            references=references,
            rewriters=lambda: ctx.ports(DEFINITIONS_REWRITERS),
            library_rules=secret_rules,
            unavailable=lambda: ctx.unavailable(
                DEFINITIONS_STORE, "정의 기능이 꺼져 있어 공용 구성을 복사할 수 없습니다"
            ),
            messages=cfg.messages,
        )
        snapshot = DefinitionSnapshot(
            reader, ttl=cfg.snapshot_ttl_seconds, skip_kinds=(PROJECT_KIND_NAME,)
        )
        scope = ScopeService(
            repository,
            snapshot=snapshot,
            writer=lambda: ctx.port(DEFINITIONS_STORE),
            references=references,
            unavailable=lambda: ctx.unavailable(
                DEFINITIONS_STORE, "정의 기능이 꺼져 있어 정의를 옮길 수 없습니다"
            ),
            messages=cfg.messages,
        )

        def on_saved(_item: SavedLike) -> None:
            snapshot.invalidate()

        ctx.subscribe(DEFINITIONS_SAVED, on_saved)
        ctx.provide(PROJECTS_LOOKUP, manager)
        ctx.provide(PROJECT_FOLDERS, manager.folder_set)
        ctx.provide(PROJECTS_SPACES, spaces)
        ctx.provide(DEFINITIONS_SPACES, DefinitionSpacesView(spaces))

        async def shutdown() -> None:
            manager.close()

        services = Services(
            projects=lambda: manager,
            folders=lambda: folders,
            picker=lambda: picker,
            copies=lambda: copies,
            scope=lambda: scope,
        )
        return ModuleParts(
            routers=[build_router(services)], error_map=dict(ERROR_MAP), shutdown=[shutdown]
        )


module = ProjectsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "DEFAULT_WORKSPACE",
    "MODULE_ID",
    "WEB_ROLES",
    "ProjectsModule",
    "library_kinds",
    "module",
    "open_versions",
]
