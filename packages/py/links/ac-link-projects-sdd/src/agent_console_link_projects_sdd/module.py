"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-projects-sdd``).

프로젝트 공간(``mod-projects``)의 폴더를 SDD 모듈(``mod-sdd``)의 스펙 공간으로 준다
(design §6R.3·§6R.4, §PI.5).

- 필수: ``projects.spaces``. 없으면(``mod-projects`` 꺼짐) 이 연동도 꺼진다.
- 제공: ``sdd.spaces`` - 공간 이름(등록 id) → 그 폴더의 정의 저장소·폴더 안 파일 접근·쓰기 가능
  여부·구성 폴더 경로(``ProjectSddSpace``).
- 이 연동이 꺼지면: ``mod-sdd``가 ``?project=`` 요청에 409 ``sdd.spaces_unavailable``을 낸다. 스펙을
  앱 workspace(단독 루트)에 대신 만들지 않는다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .ports import PROJECTS_SPACES, SDD_SPACES
from .settings import ProjectsSddSettings
from .spaces import ProjectSddSpaces

MODULE_ID = "link-projects-sdd"


def _version() -> str:
    try:
        return version("agent-console-link-projects-sdd")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ProjectsSddLink:
    """프로젝트 ↔ SDD 스펙 공간 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="프로젝트 스펙 연동",
        description="프로젝트 폴더 안에 그 프로젝트의 스펙과 문서 틀을 둔다",
        provides=(SDD_SPACES,),
        requires=(PROJECTS_SPACES,),
        settings_schema=ProjectsSddSettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ProjectsSddSettings):
            cfg = ProjectsSddSettings()
        ctx.provide(
            SDD_SPACES,
            ProjectSddSpaces(lambda: ctx.port(PROJECTS_SPACES), reserved=cfg.reserved_dirs),
        )
        return ModuleParts()


module = ProjectsSddLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "ProjectsSddLink", "module"]
