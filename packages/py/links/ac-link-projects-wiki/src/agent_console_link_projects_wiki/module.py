"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-projects-wiki``).

프로젝트 공간(``mod-projects``)의 폴더를 위키 모듈(``mod-wiki``)의 위키 공간으로 준다
(design §7R.3·§7R.4, §PI.5).

- 필수: ``projects.spaces``. 없으면(``mod-projects`` 꺼짐) 이 연동도 꺼진다.
- 제공: ``wiki.spaces`` - 공간 이름(등록 id) → 그 폴더의 정의 저장소·페이지 폴더·쓰기 가능 여부·구성
  폴더·검색 색인 폴더(``ProjectWikiSpace``).
- 이 연동이 꺼지면: ``mod-wiki``가 ``?project=`` 요청에 409 ``wiki.spaces_unavailable``을 낸다.
  위키를 앱 workspace(단독 루트)에 대신 만들지 않는다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .ports import PROJECTS_SPACES, WIKI_SPACES
from .settings import SETTINGS_COMPAT, ProjectsWikiSettings
from .spaces import ProjectWikiSpaces

MODULE_ID = "link-projects-wiki"


def _version() -> str:
    try:
        return version("agent-console-link-projects-wiki")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ProjectsWikiLink:
    """프로젝트 ↔ 위키 공간 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="프로젝트 위키 연동",
        description="프로젝트 폴더 안에 그 프로젝트의 위키와 페이지를 둔다",
        provides=(WIKI_SPACES,),
        requires=(PROJECTS_SPACES,),
        settings_schema=ProjectsWikiSettings,
        settings_compat=SETTINGS_COMPAT,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ProjectsWikiSettings):
            cfg = ProjectsWikiSettings()
        ctx.provide(
            WIKI_SPACES,
            ProjectWikiSpaces(
                lambda: ctx.port(PROJECTS_SPACES),
                pages_dir=cfg.pages_dir,
                index_dir=cfg.index_dir,
                reserved=cfg.reserved_dirs,
            ),
        )
        return ModuleParts()


module = ProjectsWikiLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "ProjectsWikiLink", "module"]
