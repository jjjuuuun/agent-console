"""REST: 호스트 경로 — 준비 신호 `GET /health`(모듈 시작 전·종료 중 503 `not_ready`),
토큰 `GET /bootstrap`, 모듈 목록 `GET /modules`, 모듈 옵션 읽기 전용 보기
`GET /modules/{id}/options`(`_module_options`), 서버 정보 `GET /server-info`(모듈이 경고·속성을
기여, `_server_info`).

기능 모듈과 상관없이 항상 있다(모듈을 모두 꺼도 웹이 토큰·모듈 목록을 읽을 수 있다, design §3R.1.3
호스트). 라우터는 modkit 호스트 부품을 쓰고 응답 모양만 계약(`HealthResponse`·`BootstrapResponse`·
`ModuleInfo`)으로 정한다. 경로는 접두 없이 만들고, 앱이 `API_PREFIX` 아래 붙인다.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from agent_console_contracts import (
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    BootstrapResponse,
    HealthResponse,
    ModuleInfo,
    ModuleOptionsView,
    ServerInfo,
)
from agent_console_modkit.host import (
    build_health_router,
    build_module_options_router,
    build_modules_router,
)

from ._restkit import errors


def build_host_router(
    *,
    server_version: str,
    token: str,
    modules: Callable[[], list[ModuleInfo]],
    info: Callable[[], ServerInfo] | None = None,
    ready: Callable[[], bool] | None = None,
    module_options: Callable[[str], ModuleOptionsView | None] | None = None,
) -> APIRouter:
    """호스트 경로 라우터.

    Args:
        server_version: 서버 버전(`/health`·`/bootstrap`).
        token: 로컬 API 토큰(`/bootstrap`이 Host·Origin 검사를 통과한 요청에만 준다).
        modules: 모듈 목록 함수(부를 때마다 새로 — 시작 실패로 바뀐 상태도 보인다).
        info: 서버 정보 함수(`GET /server-info`). None이면 그 경로가 없다.
        ready: 준비 여부(보통 `assembly.running`). 거짓이면 `/health`가 503 `not_ready`
            (200 = 준비라는 준비 신호 계약 유지, 3R.16). None이면 늘 준비.
        module_options: 모듈 옵션 읽기 전용 보기 함수(`GET /modules/{id}/options`, 모르는 id면
            None → 404). None이면 그 경로가 없다.
    """
    router = APIRouter()

    def health() -> HealthResponse:
        return HealthResponse(server_version=server_version, contracts_version=CONTRACTS_VERSION)

    router.include_router(
        build_health_router(
            payload=health,
            response_model=HealthResponse,
            responses=errors(503),
            ready=ready,
            error_status=HTTP_STATUS_BY_ERROR_CODE,
        )
    )

    @router.get("/bootstrap", response_model=BootstrapResponse, responses=errors())
    async def bootstrap() -> BootstrapResponse:
        """로컬 API 토큰. Host·Origin 검사(같은 출처 또는 허용 출처)를 통과한 요청에만 준다."""
        return BootstrapResponse(
            token=token, server_version=server_version, contracts_version=CONTRACTS_VERSION
        )

    router.include_router(
        build_modules_router(payload=modules, response_model=list[ModuleInfo], responses=errors())
    )
    if module_options is not None:
        router.include_router(
            build_module_options_router(
                payload=module_options,
                response_model=ModuleOptionsView,
                responses=errors(),
                error_status=HTTP_STATUS_BY_ERROR_CODE,
            )
        )
    if info is not None:
        server_info = info

        @router.get("/server-info", response_model=ServerInfo, responses=errors())
        async def get_server_info() -> ServerInfo:
            """서버 버전·계약 버전·플러그인 로딩 보고·속성·경고(읽기 전용, 비밀 값 없음).

            `warnings`: 모듈이 기여한 경고(`server.warnings` — 저장된 정의의 평문 비밀 의심
            `secret.plain_found`, 팀 규칙 없음 `team.rules_unavailable` 등)와 옛 위치에서 옮긴
            설정 키(`settings.moved_key`). `attributes`: 바인딩·출처 + 모듈 기여
            (`server.attributes` — 복구한 Run 수 `recovered_runs` 등). `security.expose_paths`가
            false면 workspace 경로를 뺀다.
            """
            return server_info()

    return router


__all__ = ["build_host_router"]
