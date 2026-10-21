"""REST: 사용량(design §R4.3·§3R.5). 출처·창 이름을 모른다(레지스트리·설정 데이터).

경로는 접두 없이 만들고 호스트가 ``/api/v1`` 아래 붙인다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query

from agent_console_contracts import ErrorResponse, UsageReport, UsageSourceInfo

from .service import UsageReportService, parse_parts

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 422, 500)
}

PartsQuery = Annotated[
    list[str] | None,
    Query(
        description=(
            "필요한 부분(쉼표 목록, 여러 번 가능): `windows`(창 스냅샷), `tokens`(토큰 집계). "
            "생략하면 전부. 요청하지 않은 부분은 null이다. 모르는 이름은 무시한다."
        )
    ),
]


def build_router(service: Callable[[], UsageReportService]) -> APIRouter:
    """``/usage``·``/usage/sources`` 라우터.

    Args:
        service: 서비스를 돌려주는 함수(요청마다 부른다).
    """
    router = APIRouter()

    @router.get("/usage", response_model=UsageReport, responses=_ERRORS)
    async def usage(parts: PartsQuery = None) -> UsageReport:
        """창 스냅샷(켜진 출처를 지금 수집, 관측값은 기록) + 플랫폼 실행분 토큰 집계(서버
        시간대). `parts=windows`만 요청하면 실행 기록을 읽지 않는다(셸 표시기용).
        """
        return await service().report(parse_parts(parts))

    @router.get("/usage/sources", response_model=list[UsageSourceInfo], responses=_ERRORS)
    async def usage_sources() -> list[UsageSourceInfo]:
        """출처 디스크립터 + 사용 여부·설정 + 마지막 수집 상태(오류 코드만, 예외 문장 없음)."""
        return service().sources()

    return router


__all__ = ["build_router"]
