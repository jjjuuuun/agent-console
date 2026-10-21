"""REST: ``POST /graphs/{graph_id}/validate``(접두 없음, 호스트가 ``/api/v1`` 아래 붙인다).

결과 = 엔진 검증 + 팀 규칙(``runs.starter``) + 저장 전 정의 검사(``definitions.checks``)의
경고·정보.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Body

from agent_console_contracts import ErrorResponse, Graph, Issue

from .definition_checks import with_definition_checks
from .ports import DefinitionCheck, RunChecker

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 413, 422, 500)
}


def build_router(
    checker: Callable[[], RunChecker],
    checks: Callable[[], Sequence[DefinitionCheck]] = lambda: (),
) -> APIRouter:
    """검증 경로 라우터.

    Args:
        checker: 실행 검증(``runs.starter``)을 돌려준다.
        checks: 지금 저장 전 정의 검사 목록(``definitions.checks``, 요청마다 부른다). 기본은 없음
            (엔진 검증 + 팀 규칙만).
    """
    router = APIRouter()

    @router.post("/graphs/{graph_id}/validate", response_model=list[Issue], responses=_ERRORS)
    async def validate_graph(
        graph_id: str,
        graph: Annotated[Graph | None, Body()] = None,
    ) -> list[Issue]:
        """본문 그래프(없으면 저장된 그래프)를 검증한다(이슈가 있어도 200). 엔진 검증 + 팀 규칙 +
        저장 전 정의 검사의 경고·정보(예: 프로젝트 범위 경고, 제공 모듈이 없으면 없음)."""
        check = checker()
        target = graph or check.load_graph(graph_id)
        return with_definition_checks(target, check.check(target), checks)

    return router


__all__ = ["build_router"]
