"""REST: ``POST /graphs/{graph_id}/validate``(접두 없음, 호스트가 ``/api/v1`` 아래 붙인다).

결과 = 엔진 검증 + 팀 규칙(``runs.starter``) + 저장 전 정의 검사(``definitions.checks``)의
경고·정보. 질의 ``?project=<id>``를 주면 그 프로젝트에서 실행할 때 기준이다(``runs.starter``의
선택 메서드 ``check_project`` — 실행 시작과 같은 정의 출처·실행 범위, 공간에만 있는 구성도 읽는다).
그 메서드가 없으면 409 ``feature_unavailable``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Body

from agent_console_contracts import ErrorResponse, Graph, Issue
from agent_console_modkit import FeatureUnavailableError
from agent_console_modkit.host import SpaceQuery

from .definition_checks import with_definition_checks
from .ports import DefinitionCheck, ProjectRunChecker, RunChecker

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 413, 422, 500)
}


def _no_project_check() -> Exception:
    return FeatureUnavailableError(
        "link-runs-teams", "runs.starter", "실행 모듈이 프로젝트 기준 검증을 지원하지 않습니다"
    )


def build_router(
    checker: Callable[[], RunChecker],
    checks: Callable[[], Sequence[DefinitionCheck]] = lambda: (),
    *,
    project_unavailable: Callable[[], Exception] = _no_project_check,
) -> APIRouter:
    """검증 경로 라우터.

    Args:
        checker: 실행 검증(``runs.starter``)을 돌려준다.
        checks: 지금 저장 전 정의 검사 목록(``definitions.checks``, 요청마다 부른다). 기본은 없음
            (엔진 검증 + 팀 규칙만).
        project_unavailable: ``?project=``를 받았는데 ``checker``에 ``check_project``가 없을 때
            던질 오류(기본 409 ``feature_unavailable``).
    """
    router = APIRouter()

    @router.post("/graphs/{graph_id}/validate", response_model=list[Issue], responses=_ERRORS)
    async def validate_graph(
        graph_id: str,
        graph: Annotated[Graph | None, Body()] = None,
        space: SpaceQuery = None,
    ) -> list[Issue]:
        """본문 그래프(없으면 저장된 그래프)를 검증한다(이슈가 있어도 200). 엔진 검증 + 팀 규칙 +
        저장 전 정의 검사의 경고·정보(예: 프로젝트 범위 경고, 제공 모듈이 없으면 없음).
        ``?project=``를 주면 그 프로젝트에서 실행할 때 기준(그 공간의 정의, 실행 범위)이다."""
        check = checker()
        if space:
            if not isinstance(check, ProjectRunChecker):
                raise project_unavailable()
            target = graph or check.load_graph(graph_id, project_id=space)
            issues = check.check_project(graph_id, space, graph=target)
            return with_definition_checks(target, issues, checks)
        target = graph or check.load_graph(graph_id)
        return with_definition_checks(target, check.check(target), checks)

    return router


__all__ = ["build_router"]
