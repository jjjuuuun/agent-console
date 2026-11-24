"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-projects-runs``).

프로젝트(``mod-projects``)와 실행(``mod-runs``)을 잇는다(design §UX-P.5·§5.2R.6).

- 필수: ``projects.lookup``. 없으면(``mod-projects`` 꺼짐) 이 연동도 꺼진다.
- 선택: ``definitions.spaces``(Run의 정의 출처 = 프로젝트 공간), ``definitions.lookup``(라이브러리 —
  ``project.not_imported``의 ``in_library``만).
- 제공: ``runs.scopes``(실행의 ``project_id`` → 프로젝트 층·정의 출처·사전 점검, 5.7R.33g),
  ``settings.scope_layers``(유효 설정 ``?project=``).
- 사전 점검(§PI.4.5·§PI.5): ``project.required``(설정 ``require_project``)·``project.not_found``·
  ``project.folder_missing``·``project.manifest_invalid``·``project.not_imported``·
  ``project.records_unavailable``·``project.outside_folder``. 경로 지킴은 앱 workspace·상태 폴더를
  함께 허용한다.
- 프로젝트 층 = ``project_layer_value``(프로젝트 ``settings``의 지정한 필드 +
  ``working_directory`` = 프로젝트 ``folder``).
  위치는 공통 바로 아래(``ac-teams`` ``scope_layers``). 자식 Run은 부모(루트) Run의 층을 물려받는다.
- 이 연동이 꺼지면(5.7R.33t1, K33-10): 프로젝트 범위를 맡는 공급자(``accepts_project``)가 없어진다.
  ``mod-projects``가 켜진 조립이면 ``mod-runs``가 ``project_id``를 붙인 실행·대화 턴을 409
  ``feature_unavailable``(``details.port = "runs.scopes"``)로 막는다(설정
  ``mod-runs.unscoped_project_runs``). 프로젝트 없는 실행은 그대로다.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_teams import TeamCatalog, catalog_from_registries

from .ports import DEFINITIONS_LOOKUP, DEFINITIONS_SPACES, PROJECTS_LOOKUP, RUN_SCOPES, SCOPE_LAYERS
from .scope import ProjectScope
from .settings import ProjectsRunsSettings

MODULE_ID = "link-projects-runs"


def _version() -> str:
    try:
        return version("agent-console-link-projects-runs")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ProjectsRunsLink:
    """프로젝트 ↔ 실행 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="프로젝트·실행 연동",
        description="실행할 때 프로젝트의 작업 폴더·설정을 쓰고 실행 전에 점검한다",
        provides=(RUN_SCOPES, SCOPE_LAYERS),
        requires=(PROJECTS_LOOKUP,),
        optional=(DEFINITIONS_SPACES, DEFINITIONS_LOOKUP),
        settings_schema=ProjectsRunsSettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ProjectsRunsSettings):
            cfg = ProjectsRunsSettings()
        paths = ctx.paths
        # 앱이 만드는 폴더(workspace·상태 폴더)는 프로젝트 밖이어도 허용(§PI.5 (a))
        allowed = (
            [os.path.abspath(paths.workspace), os.path.abspath(paths.state)]
            if paths is not None
            else []
        )
        registries = ctx.registries

        def catalog() -> TeamCatalog:
            return catalog_from_registries(registries)

        scope = ProjectScope(
            lambda: ctx.port(PROJECTS_LOOKUP),
            layer_id=cfg.layer_id,
            layer_label=cfg.layer_label,
            unknown_message=cfg.unknown_message,
            spaces=lambda: ctx.port(DEFINITIONS_SPACES),
            library=lambda: ctx.port(DEFINITIONS_LOOKUP),
            catalog=catalog,
            allowed=allowed,
            environ=ctx.environ,
            require_project=cfg.require_project,
        )
        ctx.provide(RUN_SCOPES, scope)
        ctx.provide(SCOPE_LAYERS, scope)
        return ModuleParts()


module = ProjectsRunsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "ProjectsRunsLink", "module"]
