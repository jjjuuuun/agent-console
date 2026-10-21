"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-exports-teams``).

내보내기(``mod-exports``)와 팀 의미(``ac-teams``)를 잇는다(design §3R.1.4 L10).

- 필수: ``definitions.lookup``. 선택: ``workspace.settings``.
- 제공: ``exports.dependencies``(정의가 쓰는 정의). 경로 없음.
- 이 연동이 꺼지면: 내보내기는 의존 자동 포함 없이 고른 항목만 내보낸다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS, WorkspaceSettings
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_teams import catalog_from_registries

from .dependencies import TeamExportDependencies
from .ports import DEFINITIONS_LOOKUP, EXPORT_DEPENDENCIES, WORKSPACE_SETTINGS

MODULE_ID = "link-exports-teams"


def _version() -> str:
    try:
        return version("agent-console-link-exports-teams")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ExportsTeamsLink:
    """내보내기 ↔ 팀 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="내보내기·팀 연동",
        description="내보낼 정의가 쓰는 에이전트·리소스(의존 자동 포함)",
        provides=(EXPORT_DEPENDENCIES,),
        requires=(DEFINITIONS_LOOKUP,),
        optional=(WORKSPACE_SETTINGS,),
        contracts={"exports": CONTRACT_VERSIONS["exports"]},
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        lookup = ctx.port(DEFINITIONS_LOOKUP)
        if lookup is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.lookup이 없습니다")

        def workspace() -> WorkspaceSettings | None:
            reader = ctx.port(WORKSPACE_SETTINGS)
            return reader() if reader is not None else None

        ctx.provide(
            EXPORT_DEPENDENCIES,
            TeamExportDependencies(
                lookup, catalog=lambda: catalog_from_registries(ctx.registries), workspace=workspace
            ),
        )
        return ModuleParts()


module = ExportsTeamsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "ExportsTeamsLink", "module"]
