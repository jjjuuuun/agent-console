"""REST: 구조도 프로필·검사·단독 투영(design §5.5R.3). 칸·연결·출처 이름을 모른다(프로필 데이터).

경로는 접두 없이 만들고 호스트가 ``/api/v1`` 아래 붙인다. 계산이 있는 처리기(검사·투영)는 동기
함수라 FastAPI가 스레드에서 부른다(이벤트 루프를 막지 않는다).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from agent_console_contracts import ErrorResponse
from agent_console_contracts.architecture import (
    ArchitectureProfileCheckRequest,
    ArchitectureProfileCheckResult,
    ArchitectureProfileDetail,
    ArchitectureProfileList,
    ArchitectureProjectRequest,
    ArchitectureView,
)

from .catalog import ArchitectureCatalogService


def _errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": ErrorResponse} for status in statuses}


def build_router(service: Callable[[], ArchitectureCatalogService]) -> APIRouter:
    """``/architecture/*`` 라우터.

    Args:
        service: 서비스를 돌려주는 함수(요청마다 부른다).
    """
    router = APIRouter()

    @router.get(
        "/architecture/profiles",
        response_model=ArchitectureProfileList,
        responses=_errors(401, 403, 500),
    )
    def list_profiles() -> ArchitectureProfileList:
        """병합된 프로필 목록(기본 → 플러그인 → 사용자 순, 끈 프로필은 뒤에 ``disabled``).

        프로필이 하나도 없어도 200과 빈 목록이다("구조도 규칙 없음").
        """
        return service().profile_list()

    @router.post(
        "/architecture/profiles/check",
        response_model=ArchitectureProfileCheckResult,
        responses=_errors(401, 403, 422, 500),
    )
    def check_profile(body: ArchitectureProfileCheckRequest) -> ArchitectureProfileCheckResult:
        """편집 중인 프로필을 검사한다. 형식 오류도 문제 목록으로 알린다(저장을 막지 않는다)."""
        return service().check(body)

    @router.get(
        "/architecture/profiles/{profile_id}",
        response_model=ArchitectureProfileDetail,
        responses=_errors(401, 403, 404, 500),
    )
    def get_profile(profile_id: str) -> ArchitectureProfileDetail:
        """프로필 하나(본문 + 검사 결과). 끈 프로필도 ``disabled: true``로 돌려준다.

        없으면 404 ``architecture.profile_not_found``.
        """
        return service().profile_detail(profile_id)

    @router.post(
        "/architecture/project",
        response_model=ArchitectureView,
        responses=_errors(401, 403, 404, 422, 500),
    )
    def project(body: ArchitectureProjectRequest) -> ArchitectureView:
        """본문의 이벤트를 프로필로 투영한다(로그 모듈 없이 단독으로).

        이벤트 수가 설치자 상한(``max_request_events``)을 넘으면 422
        ``architecture.scope_too_large``. 프로필이 하나도 없고 인라인 본문도 없으면 404
        ``architecture.profile_not_found``. 없는 id를 주면 기본 프로필로 그리고 안내를 단다.
        """
        return service().project_request(body)

    return router


__all__ = ["build_router"]
