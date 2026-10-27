"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-runs-teams``).

실행(``mod-runs``)과 팀 의미(``ac-teams``)를 잇는다(design §3R.1.4 L4).

- 필수: ``runs.starter``·``definitions.lookup``. 선택: ``workspace.settings``·``resources.lookup``·
  ``resources.types``·``definitions.checks``(검증 경로에 저장 전 검사의 경고·정보를 붙인다 — 예:
  ``mod-projects``의 범위 경고. 제공자가 없으면 엔진 검증 + 팀 규칙만).
- 제공: ``runs.preparers``(팀 규칙 검사·실행 준비), ``runs.services``(노드 서비스),
  ``graphs.validation``(목록 검증 요약). 경로: ``POST /graphs/{id}/validate``.
- 구독: ``definitions.saved`` → 검증 요약 캐시 버리기.
- 디스크립터: 호스트 기본 서비스 ``registries``(노드·엣지·위임 방식·백엔드)를 요청마다 읽는다.
- 중첩 팀(design §5R.7): 노드 서비스 ``TEAM_LOOKUP``(팀 구성 읽기 = ``runs.starter``의
  ``load_graph``, 고정 버전 포함)과 팀 규칙의 중첩 검사(자기·순환 참조, 깊이, 자식 없음·입구 없음).
- 설치자 옵션(``RunsTeamsLinkSettings``): ``issue_fixes_file``(해결 버튼 표 교체·끄기).
- 이 연동이 꺼지면: 실행은 엔진 검증만으로 하고(``mod-runs``가 ``team.rules_unavailable`` 경고),
  목록 검증 요약은 null, 검증 경로는 404, 중첩 팀 노드는 ``team.lookup_unavailable``로 실패한다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_teams import catalog_from_registries

from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    DEFINITIONS_SAVED,
    GRAPH_VALIDATION,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    RUN_PREPARERS,
    RUN_SERVICES,
    RUNS_STARTER,
    WORKSPACE_SETTINGS,
)
from .routes import build_router
from .rules import TeamRules, ValidationSummaries
from .settings import RunsTeamsLinkSettings, issue_fixes_of

MODULE_ID = "link-runs-teams"
WEB_ROLES: tuple[str, ...] = ("runs:team-rules",)
"""웹 연동 부분 역할(팀 구성 목록 검증 열 등)."""


def _version() -> str:
    try:
        return version("agent-console-link-runs-teams")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class RunsTeamsLink:
    """실행 ↔ 팀 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="실행·팀 연동",
        description="팀 규칙 검증·실행 준비·노드 서비스, 팀 구성 검증 요약·검증 경로",
        provides=(RUN_PREPARERS, RUN_SERVICES, GRAPH_VALIDATION),
        requires=(RUNS_STARTER, DEFINITIONS_LOOKUP),
        optional=(WORKSPACE_SETTINGS, RESOURCES_LOOKUP, RESOURCE_TYPES, DEFINITION_CHECKS),
        contracts={"definitions": CONTRACT_VERSIONS["definitions"]},
        web_roles=WEB_ROLES,
        settings_schema=RunsTeamsLinkSettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        checker = ctx.port(RUNS_STARTER)
        lookup = ctx.port(DEFINITIONS_LOOKUP)
        if checker is None or lookup is None:  # pragma: no cover - 조립기가 보장한다
            raise RuntimeError("runs.starter·definitions.lookup이 없습니다")
        cfg = ctx.settings
        if not isinstance(cfg, RunsTeamsLinkSettings):
            cfg = RunsTeamsLinkSettings()
        base = ctx.paths.base_dir if ctx.paths is not None else None
        rules = TeamRules(
            lookup,
            catalog=lambda: catalog_from_registries(ctx.registries),
            registries=lambda: ctx.registries,
            workspace=lambda: reader() if (reader := ctx.port(WORKSPACE_SETTINGS)) else None,
            resources=lambda: ctx.port(RESOURCES_LOOKUP),
            types=lambda: ctx.port(RESOURCE_TYPES),
            graphs=lambda: checker.load_graph,
            issue_fixes=issue_fixes_of(cfg.issue_fixes_file, base),
        )
        summaries = ValidationSummaries(checker, lookup)
        ctx.provide(RUN_PREPARERS, rules)
        ctx.provide(RUN_SERVICES, rules)
        ctx.provide(GRAPH_VALIDATION, summaries)
        ctx.subscribe(DEFINITIONS_SAVED, summaries.invalidate)
        return ModuleParts(
            routers=[build_router(lambda: checker, lambda: ctx.ports(DEFINITION_CHECKS))]
        )


module = RunsTeamsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "RunsTeamsLink", "module"]
