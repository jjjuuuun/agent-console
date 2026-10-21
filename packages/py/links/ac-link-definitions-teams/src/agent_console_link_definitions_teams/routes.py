"""REST: 정의·팀 연동 경로(design §2R.6, §3R.1.4 L9). 저장본과 초안(저장하지 않은 본문 그래프)을
같은 계산으로 답한다. 경로는 접두 없이 만들고 호스트가 ``/api/v1``을 붙인다.

- ``GET /agents/{id}/usages``·``GET /resources/{id}/usages`` → ``DefinitionReference[]``
- ``GET /agents/{id}/effective-settings`` → ``EffectiveSettings``(팀 밖 2층)
- 유효 설정 경로는 선택 질의 ``project``(범위 id)를 받는다. 범위 층 공급자
  (``settings.scope_layers``, 예: link-projects-runs)가 있으면 그 층을 공통 바로 아래에 끼운다
  (없으면 무시).
- ``GET /graphs/{id}/plan``·``POST /graphs/plan``(초안) → ``TeamPlanSummary``
- ``GET /graphs/{id}/nodes/{node}/effective-settings``·``POST /graphs/effective-settings``(초안)
- ``GET /graphs/{id}/nodes/{node}/bundle-preview``·``POST /graphs/bundle-preview``(초안)

이 연동이 꺼지면 위 경로는 404이고 웹은 해당 패널을 숨긴다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Query

from agent_console_contracts import (
    BundlePreview,
    DefinitionReference,
    DraftGraphRequest,
    DraftNodeRequest,
    EffectiveSettings,
    ErrorResponse,
    Graph,
    TeamPlanSummary,
)
from agent_console_store import AGENT_KIND, GRAPH_KIND, RESOURCE_KIND

from .views import TeamViews

_ERROR_STATUSES = (400, 401, 403, 404, 413, 422, 500)

_PROJECT = Query(
    default=None,
    description=(
        "범위 id(예: 프로젝트 id). 범위 층 공급자가 있으면 공통 바로 아래에 그 층을 끼운다."
    ),
)


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def build_router(views: Callable[[], TeamViews]) -> APIRouter:
    """연동 경로 라우터(``views``는 요청마다 부른다)."""
    router = APIRouter()
    agent_kind, graph_kind, resource_kind = AGENT_KIND.name, GRAPH_KIND.name, RESOURCE_KIND.name

    # ------------------------------------------------------------ 사용처

    @router.get(
        "/agents/{agent_id}/usages", response_model=list[DefinitionReference], responses=errors()
    )
    async def agent_usages(agent_id: str) -> list[DefinitionReference]:
        """이 에이전트를 쓰는 팀 구성(노드 id 목록). 에이전트가 없으면 404."""
        v = views()
        v.lookup.get(agent_kind, agent_id)
        return v.references(agent_kind, agent_id)

    @router.get(
        "/resources/{resource_id}/usages",
        response_model=list[DefinitionReference],
        responses=errors(),
    )
    async def resource_usages(resource_id: str) -> list[DefinitionReference]:
        """붙은 곳: 리소스 노드, 팀 구성·노드·에이전트·공통 층 첨부. 리소스가 없으면 404."""
        v = views()
        v.lookup.get(resource_kind, resource_id)
        return v.references(resource_kind, resource_id)

    # ------------------------------------------------------------ 유효 설정·미리보기

    @router.get(
        "/agents/{agent_id}/effective-settings",
        response_model=EffectiveSettings,
        responses=errors(),
    )
    async def agent_effective(agent_id: str, project: str | None = _PROJECT) -> EffectiveSettings:
        """팀 구성 밖 유효 설정(공통 → [범위 층] → 에이전트)과 출처. ``x-secret`` 평문은 가린다."""
        return views().agent_effective(agent_id, scope=project)

    @router.get("/graphs/{graph_id}/plan", response_model=TeamPlanSummary, responses=errors())
    async def get_plan(graph_id: str) -> TeamPlanSummary:
        """저장된 팀 구성의 실행 계획 요약(입구·답변 자리·노드별 허용 상호작용)."""
        v = views()
        return v.plan_summary(v.model(graph_kind, graph_id, Graph))

    @router.post("/graphs/plan", response_model=TeamPlanSummary, responses=errors())
    async def draft_plan(body: DraftGraphRequest) -> TeamPlanSummary:
        """초안 그래프의 실행 계획 요약(저장하지 않는다)."""
        return views().plan_summary(body.graph)

    @router.get(
        "/graphs/{graph_id}/nodes/{node_id}/effective-settings",
        response_model=EffectiveSettings,
        responses=errors(),
    )
    async def node_effective(
        graph_id: str, node_id: str, project: str | None = _PROJECT
    ) -> EffectiveSettings:
        """저장된 팀 구성 안 노드의 유효 설정(4층 + 리소스 연결)·출처·경고(``x-secret`` 가림)."""
        v = views()
        return v.node_effective(v.model(graph_kind, graph_id, Graph), node_id, scope=project)

    @router.post("/graphs/effective-settings", response_model=EffectiveSettings, responses=errors())
    async def draft_effective(
        body: DraftNodeRequest, project: str | None = _PROJECT
    ) -> EffectiveSettings:
        """초안 그래프 안 노드의 유효 설정(저장하지 않는다, 가림은 저장본과 같다)."""
        return views().node_effective(body.graph, body.node_id, scope=project)

    @router.get(
        "/graphs/{graph_id}/nodes/{node_id}/bundle-preview",
        response_model=BundlePreview,
        responses=errors(),
    )
    async def node_bundle(graph_id: str, node_id: str) -> BundlePreview:
        """실행 묶음 미리보기 + 경고. 비밀 참조는 그대로, 해석한 값과 ``x-secret`` 평문은 가린다."""
        v = views()
        return v.node_bundle(v.model(graph_kind, graph_id, Graph), node_id)

    @router.post("/graphs/bundle-preview", response_model=BundlePreview, responses=errors())
    async def draft_bundle(body: DraftNodeRequest) -> BundlePreview:
        """초안 그래프 안 노드의 실행 묶음 미리보기(저장하지 않는다, 가림은 저장본과 같다)."""
        return views().node_bundle(body.graph, body.node_id)

    return router


__all__ = ["build_router", "errors"]
