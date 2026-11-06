"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-projects-memory``).

프로젝트 공간(``mod-projects``)의 폴더에 메모리 DB(``<구성 폴더>/memory.sqlite3``)를 열어 메모리
모듈(``mod-memory``)에 준다(design §PI.4.3, K33-19).

- 필수: ``projects.spaces``. 없으면(``mod-projects`` 꺼짐) 이 연동도 꺼진다.
- 제공: ``memory.spaces`` - 공간 이름(등록 id) → 그 폴더의 메모리 저장소 + 맥락 바꾸기
  (``{project_id: 폴더 id}``). 처음 쓸 때 열고 켜진 모듈 중 ``migration_scope`` 범위(기본
  ``memory``)를 선언한 계보를 올린다.
- 이 연동이 꺼지면: 프로젝트 메모리가 없다. 메모리 화면은 라이브러리만(``?project=``는 409
  ``feature_unavailable``), 프로젝트 실행의 메모리 도구는 ``scope_unavailable``(라이브러리 메모리에
  조용히 쓰지 않는다).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .pool import PoolOptions, ProjectMemoryPool
from .ports import MEMORY_SPACES, PROJECTS_SPACES
from .settings import ProjectsMemorySettings

MODULE_ID = "link-projects-memory"


def _version() -> str:
    try:
        return version("agent-console-link-projects-memory")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def options_of(cfg: ProjectsMemorySettings) -> PoolOptions:
    """설정 → 묶음 옵션."""
    return PoolOptions(
        max_open=cfg.max_open_spaces,
        idle_close_seconds=cfg.idle_close_seconds,
        busy_timeout=cfg.busy_timeout_seconds,
        use_fts=cfg.full_text_search,
        journal=cfg.journal,
        context_field=cfg.context_field,
    )


class ProjectsMemoryLink:
    """프로젝트 ↔ 메모리 DB 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="프로젝트 메모리 연동",
        description="프로젝트 폴더 안에 그 프로젝트의 메모리를 둔다",
        provides=(MEMORY_SPACES,),
        requires=(PROJECTS_SPACES,),
        settings_schema=ProjectsMemorySettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ProjectsMemorySettings):
            cfg = ProjectsMemorySettings()
        scope = cfg.migration_scope
        pool = ProjectMemoryPool(
            lambda: ctx.port(PROJECTS_SPACES),
            lambda: ctx.active_migrations(scope),
            options=options_of(cfg),
        )
        ctx.provide(MEMORY_SPACES, pool)

        async def stop() -> None:
            pool.close_all()

        return ModuleParts(shutdown=[stop])


module = ProjectsMemoryLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "ProjectsMemoryLink", "module", "options_of"]
