"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-wiki-runs``).

위키(``mod-wiki``)와 실행(``mod-runs``)을 잇는다(design §7R.3·§7R.4).

- 필수: ``wiki.service``. 없으면(``mod-wiki`` 꺼짐) 이 연동도 꺼진다. 그래도 실행은 정상이고, 위키
  리소스를 붙인 에이전트에게는 칸이 적용되지 않았다는 경고(R13.5)가 한 번 난다.
- 선택: ``projects.lookup``(저장 전 검사가 프로젝트 공간 위키 id도 본다).
- 제공: ``runs.scopes``(Run마다 노드 서비스 ``TOOL_PROVIDERS``에 위키 도구 공급자),
  ``runs.services``(노드 종류 ``wiki-update``의 위키 서비스 ``WIKI_UPDATE_SERVICE``),
  ``definitions.checks``(위키 리소스의 모르는 위키 id 경고), ``wiki.integrations``
  (``{runs}`` — 위키 화면의 ``capabilities.runs``).
- 노드 종류 ``wiki-update``는 이 패키지의 entry point ``agent_console.node_types``로 따로 등록된다.
  이 연동이 꺼지면 노드는 그래프 검증 경고를 받고, 실행하면 건너뛴다(``update_node``).
- 리소스 종류 ``wiki``는 이 패키지의 entry point ``agent_console.resource_types``(패키지 데이터)로
  따로 등록된다. 이 연동 모듈을 끄더라도 리소스는 만들 수 있다(칸을 받을 공급자만 없다).
- 웹 역할 ``wiki:runs``(실행 상세의 위키 칩·링크).
- 설정 ``modules.options.link-wiki-runs``: ``max_writes_per_run``(기본 100, 비우면 한도 없음).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .checks import WikiResourceCheck
from .ports import (
    DEFINITION_CHECKS,
    PROJECTS_LOOKUP,
    RUN_SCOPES,
    RUN_SERVICES,
    WIKI_INTEGRATIONS,
    WIKI_SERVICE,
    WikiRunsIntegration,
)
from .resource_type import load_wiki_resource_type, wiki_slot
from .scope import WikiRunScope
from .settings import WikiRunsSettings
from .update_node import WikiNodeServices

MODULE_ID = "link-wiki-runs"
WEB_ROLES: tuple[str, ...] = ("wiki:runs",)
"""웹 연동 부분 역할(실행 상세의 위키 칩·링크)."""


def _version() -> str:
    try:
        return version("agent-console-link-wiki-runs")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class WikiRunsLink:
    """위키 ↔ 실행 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="위키·실행 연동",
        description="실행 중인 에이전트가 위키를 검색·읽기·고치게 하고 그 기록을 남긴다",
        provides=(RUN_SCOPES, RUN_SERVICES, DEFINITION_CHECKS, WIKI_INTEGRATIONS),
        requires=(WIKI_SERVICE,),
        optional=(PROJECTS_LOOKUP,),
        settings_schema=WikiRunsSettings,
        contracts={"wiki": CONTRACT_VERSIONS["wiki"], "runs": CONTRACT_VERSIONS["runs"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, WikiRunsSettings):
            cfg = WikiRunsSettings()
        rtype = load_wiki_resource_type()
        ctx.provide(
            RUN_SCOPES,
            WikiRunScope(
                lambda: ctx.port(WIKI_SERVICE),
                slot=wiki_slot(rtype),
                max_writes_per_run=cfg.max_writes_per_run,
                provider_id=MODULE_ID,
            ),
        )
        ctx.provide(RUN_SERVICES, WikiNodeServices(lambda: ctx.port(WIKI_SERVICE)))
        ctx.provide(
            DEFINITION_CHECKS,
            WikiResourceCheck(
                lambda: ctx.port(WIKI_SERVICE),
                resource_type=rtype.id,
                projects=lambda: ctx.port(PROJECTS_LOOKUP),
            ),
        )
        ctx.provide(WIKI_INTEGRATIONS, WikiRunsIntegration(id=MODULE_ID))
        return ModuleParts()


module = WikiRunsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "WikiRunsLink", "module"]
