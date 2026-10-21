"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-definitions-resources``).

정의(``mod-definitions``)와 리소스(``mod-resources``)를 잇는다(design §3R.1.4 L8).

- 필수: ``definitions.lookup``·``resources.types``. 선택: ``resources.lookup``·``secrets.rules``.
- 제공: ``definitions.checks``(리소스 종류 검사·첨부 검사·``x-secret`` 평문 거부). 정의 저장 전
  검사와 ``/server-info`` 평문 점검(정의 모듈이 이 검사의 평문 이슈를 모은다)에 쓰인다.
- 디스크립터(리소스 연결 해석): 호스트 기본 서비스 ``registries``를 요청마다 읽는다.
- 이 연동이 꺼지면: 정의는 리소스 검사 없이 저장된다(정의 모듈의 모델 검증·비밀 규칙 검사는 남음).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS, Graph
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_resources import ResourceLookup
from agent_console_teams import TeamPlan, catalog_from_registries

from .checks import DefinitionChecker, LookupResources
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    SECRET_RULES,
)

MODULE_ID = "link-definitions-resources"


def _version() -> str:
    try:
        return version("agent-console-link-definitions-resources")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class DefinitionsResourcesLink:
    """정의 ↔ 리소스 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="정의·리소스 연동",
        description="저장 전 리소스 종류 검사·첨부 검사, 평문 점검 기여",
        provides=(DEFINITION_CHECKS,),
        requires=(DEFINITIONS_LOOKUP, RESOURCE_TYPES),
        optional=(RESOURCES_LOOKUP, SECRET_RULES),
        contracts={"resources": CONTRACT_VERSIONS["resources"]},
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        lookup = ctx.port(DEFINITIONS_LOOKUP)
        types = ctx.port(RESOURCE_TYPES)
        if lookup is None or types is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.lookup·resources.types가 없습니다")
        fallback = LookupResources(lookup)

        def resources() -> ResourceLookup:
            return ctx.port(RESOURCES_LOOKUP) or fallback

        def plan_of(graph: Graph) -> TeamPlan | None:
            return catalog_from_registries(ctx.registries).try_plan(graph)

        ctx.provide(
            DEFINITION_CHECKS,
            DefinitionChecker(
                types=lambda: types,
                resources=resources,
                plan_of=plan_of,
                secret_rules=lambda: r() if (r := ctx.port(SECRET_RULES)) else None,
            ),
        )
        return ModuleParts()


module = DefinitionsResourcesLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "DefinitionsResourcesLink", "module"]
