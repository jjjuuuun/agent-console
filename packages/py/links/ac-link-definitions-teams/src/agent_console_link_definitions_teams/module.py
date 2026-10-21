"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-definitions-teams``).

정의(``mod-definitions``)와 팀 의미(``ac-teams``)를 잇는다(design §3R.1.4 L9).

- 필수: ``definitions.lookup``. 선택: ``workspace.settings``·``resources.lookup``·
  ``resources.types``·``secrets.redact``·``secrets.rules``·``settings.scope_layers``(유효 설정
  ``?project=``의 범위 층, 5.2R.34).
- 제공: ``graphs.entry_labels``(팀 구성 목록 입구 이름), ``definitions.usages``(리소스 목록
  ``usage_count``), ``definitions.dependencies``(문서가 쓰는 정의 — 프리셋 적용 순서),
  ``definitions.references``(같은 계산의 참조 추출 함수, 여러 제공자 포트 X25 — 프로젝트 범위 검사).
  경로: 사용처·유효 설정·실행 계획·묶음 미리보기(저장본·초안).
- 디스크립터: 호스트 기본 서비스 ``registries``(노드·엣지·위임 방식·백엔드)를 요청마다 읽는다.
- 웹 역할 ``definitions:teams``: 팀 구성 편집기의 초안 미리보기(실행 계획·유효 설정·묶음 미리보기
  ``POST /graphs/*``)와 에이전트 상세의 사용처 패널(``GET /agents/{id}/usages``).
- 이 연동이 꺼지면: 경로 404(웹이 패널을 숨김), 목록 입구 이름·``usage_count``는 null.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS, ErrorCodes
from agent_console_modkit import ErrorMapping, ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_teams import catalog_from_registries

from .dependencies import TeamDocumentDependencies
from .ports import (
    DEFINITION_DEPENDENCIES,
    DEFINITION_REFERENCES,
    DEFINITION_USAGES,
    DEFINITIONS_LOOKUP,
    GRAPH_ENTRY_LABELS,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    SCOPE_LAYERS,
    SECRET_REDACT,
    SECRET_RULES,
    WORKSPACE_SETTINGS,
    Redactor,
)
from .routes import build_router
from .views import NodeNotFoundError, TeamViews

MODULE_ID = "link-definitions-teams"
WEB_ROLES: tuple[str, ...] = ("definitions:teams",)
"""웹 연동 부분 역할(팀 구성 초안 미리보기·에이전트 사용처 패널)."""

ERROR_MAP: dict[type[Exception], ErrorMapping] = {NodeNotFoundError: ErrorCodes.NOT_FOUND}
"""모듈 ``error_map``(정의 읽기 오류는 정의 저장소를 제공하는 모듈의 오류 맵이 바꾼다)."""


def _version() -> str:
    try:
        return version("agent-console-link-definitions-teams")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class DefinitionsTeamsLink:
    """정의 ↔ 팀 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="정의·팀 연동",
        description="사용처·유효 설정·실행 계획·묶음 미리보기, 목록 입구 이름·사용 수·쓰는 정의",
        provides=(
            GRAPH_ENTRY_LABELS,
            DEFINITION_USAGES,
            DEFINITION_DEPENDENCIES,
            DEFINITION_REFERENCES,
        ),
        requires=(DEFINITIONS_LOOKUP,),
        optional=(
            WORKSPACE_SETTINGS,
            RESOURCES_LOOKUP,
            RESOURCE_TYPES,
            SECRET_REDACT,
            SECRET_RULES,
            SCOPE_LAYERS,
        ),
        contracts={"definitions": CONTRACT_VERSIONS["definitions"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        lookup = ctx.port(DEFINITIONS_LOOKUP)
        if lookup is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.lookup이 없습니다")

        def redactor() -> Redactor:
            redact = ctx.port(SECRET_REDACT)
            if redact is not None:
                return redact
            rules = ctx.port(SECRET_RULES)
            if rules is not None:
                current = rules()
                return current.redact_suspected
            return lambda text: text

        views = TeamViews(
            lookup,
            catalog=lambda: catalog_from_registries(ctx.registries),
            workspace=lambda: reader() if (reader := ctx.port(WORKSPACE_SETTINGS)) else None,
            resources=lambda: ctx.port(RESOURCES_LOOKUP),
            types=lambda: ctx.port(RESOURCE_TYPES),
            redact=redactor,
            scopes=lambda: ctx.ports(SCOPE_LAYERS),
        )
        ctx.provide(GRAPH_ENTRY_LABELS, views)
        ctx.provide(DEFINITION_USAGES, views)
        documents = TeamDocumentDependencies(lambda: catalog_from_registries(ctx.registries))
        ctx.provide(DEFINITION_DEPENDENCIES, documents)
        ctx.provide(DEFINITION_REFERENCES, documents.references)
        return ModuleParts(routers=[build_router(lambda: views)], error_map=dict(ERROR_MAP))


module = DefinitionsTeamsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["ERROR_MAP", "MODULE_ID", "WEB_ROLES", "DefinitionsTeamsLink", "module"]
