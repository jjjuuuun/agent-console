"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-projects``, design §UX-P.5).

- 저장: 워크스페이스(``BaseServices.paths.workspace``)의 ``projects/<id>.yaml``을 자기
  ``FileDefinitionStore`` 인스턴스로 맡는다(정의 모듈 종류 목록은 그대로). 버전 기록은 호스트 DB
  핸들의 정의 버전 표(legacy 계보), 없으면 메모리. 기록소는 처음 쓸 때 연다(그때 멱등 upgrade —
  프로젝트를 쓰지 않는 서버는 DB 파일을 만들지 않는다).
- 제공: ``projects.lookup``, ``definitions.checks``(범위 경고, 정의 읽기 포트가 있을 때만
  이슈를 낸다).
- 선택: ``definitions.lookup``·``definitions.store``·``definitions.references``. 구독
  ``definitions.saved``(정의 스냅샷 캐시 버리기).
- 웹 역할 ``projects``. 이 모듈을 끄면 프로젝트 종류를 열지 않아 ``projects/`` 폴더는 무시되고,
  정의의 ``project`` 필드는 파일·요약에 남지만 아무도 거르지 않는다(지금과 같음).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from agent_console_contracts import CONTRACT_VERSIONS, Issue
from agent_console_modkit import DatabaseHandle, ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_projects import References
from agent_console_store import (
    FileDefinitionStore,
    LazyVersionRepository,
    VersionRepository,
    versions_for,
)

from .definitions import DefinitionSnapshot, combine_references
from .errors import ERROR_MAP
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    DEFINITIONS_REFERENCES,
    DEFINITIONS_SAVED,
    DEFINITIONS_STORE,
    PROJECTS_LOOKUP,
    DefinitionReader,
    SavedLike,
)
from .repository import PROJECT_KIND_NAME, ProjectRepository, project_kind
from .routes import build_router
from .service import ProjectService
from .settings import ProjectModuleSettings

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
    """정의 버전 기록소를 연다(처음 쓸 때만 부른다). DB가 있으면 legacy 계보를 올리고(멱등) 그
    DB의 정의 버전 표를, 없으면 메모리를 쓴다. 시작 때 열지 않으므로 프로젝트를 쓰지 않는 서버는
    DB 파일을 만들지 않는다."""
    if database is not None:
        database.upgrade()
    return versions_for(database)


class ProjectScopeCheck:
    """``definitions.checks`` 하나: 저장하려는 정의의 범위 경고(``ProjectService.check``)."""

    def __init__(self, service: Callable[[], ProjectService]) -> None:
        self._service = service

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        return self._service().check(kind, document)


class ProjectsModule:
    """프로젝트 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="프로젝트",
        description="프로젝트 만들기·고치기·지우기, 정의 범위(공용·프로젝트 전용) 검사와 옮기기",
        provides=(PROJECTS_LOOKUP, DEFINITION_CHECKS),
        optional=(DEFINITIONS_LOOKUP, DEFINITIONS_STORE, DEFINITIONS_REFERENCES),
        settings_schema=ProjectModuleSettings,
        contracts={"projects": CONTRACT_VERSIONS["projects"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ProjectModuleSettings):
            cfg = ProjectModuleSettings()
        root = ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE
        database = ctx.database
        store = FileDefinitionStore(
            root,
            [project_kind(cfg.directory)],
            versions=LazyVersionRepository(lambda: open_versions(database)),
        )
        repository = ProjectRepository(store)

        def reader() -> DefinitionReader | None:
            return ctx.port(DEFINITIONS_LOOKUP) or ctx.port(DEFINITIONS_STORE)

        def references() -> References | None:
            return combine_references(ctx.ports(DEFINITIONS_REFERENCES))

        snapshot = DefinitionSnapshot(
            reader, ttl=cfg.snapshot_ttl_seconds, skip_kinds=(PROJECT_KIND_NAME,)
        )
        service = ProjectService(
            repository,
            snapshot=snapshot,
            writer=lambda: ctx.port(DEFINITIONS_STORE),
            references=references,
            unavailable=lambda: ctx.unavailable(
                DEFINITIONS_STORE, "정의 기능이 꺼져 있어 정의를 옮기거나 지울 수 없습니다"
            ),
            messages=cfg.messages,
        )

        def on_saved(_item: SavedLike) -> None:
            snapshot.invalidate()

        ctx.subscribe(DEFINITIONS_SAVED, on_saved)
        ctx.provide(PROJECTS_LOOKUP, repository)
        ctx.provide(DEFINITION_CHECKS, ProjectScopeCheck(lambda: service))

        return ModuleParts(routers=[build_router(lambda: service)], error_map=dict(ERROR_MAP))


module = ProjectsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "DEFAULT_WORKSPACE",
    "MODULE_ID",
    "WEB_ROLES",
    "ProjectScopeCheck",
    "ProjectsModule",
    "module",
]
