"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-runs-trace``).

실행 기록(``mod-runs``)과 위임 흐름 계산(``ac-trace``)을 잇는다(design §3R.1.4 L6).

- 필수: ``runs.reader``·``runs.events``. 선택: ``definitions.lookup``(당시 팀 구성의 연결 종류)·
  ``definitions.spaces``(프로젝트 Run의 당시 팀 구성은 그 공간 저장소에서만 읽는다).
- 경로: ``GET /runs/{id}/trace``·``GET /runs/handoffs``(둘 다 ``?project=`` — 그 프로젝트 기록,
  모르는 프로젝트 404 ``project.not_found``).
- 이 연동이 꺼지면 경로가 404이고 웹은 실행 상세의 흐름 탭·넘김 보기를 숨긴다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_console_contracts import CONTRACT_VERSIONS, ErrorCodes
from agent_console_modkit import (
    ErrorMapping,
    ErrorReply,
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
)
from agent_console_store import RecordsUnavailable, SpaceStores, UnknownSpace

from .ports import DEFINITIONS_LOOKUP, DEFINITIONS_SPACES, RUNS_EVENTS, RUNS_READER, GraphHistory
from .routes import build_router
from .views import RunNotFoundError, TraceViews

MODULE_ID = "link-runs-trace"
WEB_ROLES: tuple[str, ...] = ("runs:trace",)
"""웹 연동 부분 역할(실행 상세 흐름 탭·넘김 보기)."""


def _unknown_space(exc: Exception) -> ErrorReply:
    space = exc.space if isinstance(exc, UnknownSpace) else ""
    return ErrorReply(code=ErrorCodes.PROJECT_NOT_FOUND, details={"project_id": space})


def _records_unavailable(exc: Exception) -> ErrorReply:
    if not isinstance(exc, RecordsUnavailable):  # pragma: no cover
        return ErrorReply(code=ErrorCodes.INTERNAL)
    return ErrorReply(code=exc.code, details=exc.details())


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    RunNotFoundError: ErrorCodes.NOT_FOUND,
    UnknownSpace: _unknown_space,
    RecordsUnavailable: _records_unavailable,
}
"""Run 없음 404 ``not_found``, 모르는 프로젝트 404 ``project.not_found``(``details.project_id``),
그 프로젝트 기록을 읽을 수 없음 409 ``project.records_unavailable``(``details``)."""


def _version() -> str:
    try:
        return version("agent-console-link-runs-trace")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class RunsTraceLink:
    """실행 ↔ 추적 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="실행·추적 연동",
        description="실행에서 에이전트 사이 위임 흐름과 넘김 횟수를 보여 준다",
        requires=(RUNS_READER, RUNS_EVENTS),
        optional=(DEFINITIONS_LOOKUP, DEFINITIONS_SPACES),
        contracts={"runs": CONTRACT_VERSIONS["runs"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        runs = ctx.port(RUNS_READER)
        events = ctx.port(RUNS_EVENTS)
        if runs is None or events is None:  # pragma: no cover - 조립기가 보장한다
            raise RuntimeError("runs.reader·runs.events가 없습니다")
        history = ctx.port(DEFINITIONS_LOOKUP)
        stores: SpaceStores[Any] = SpaceStores(history, lambda: ctx.port(DEFINITIONS_SPACES))

        def space_history(space: str) -> GraphHistory | None:
            # 공간 제공자가 없으면(기능 단독) 라이브러리 정의 읽기(Run의 project_id는 이름표뿐).
            if not stores.available:
                return ctx.port(DEFINITIONS_LOOKUP)
            found: GraphHistory = stores.get(space)
            return found

        views = TraceViews(
            runs,
            events,
            history=lambda: ctx.port(DEFINITIONS_LOOKUP),
            space_history=space_history,
        )
        return ModuleParts(routers=[build_router(lambda: views)], error_map=dict(ERROR_MAP))


module = RunsTraceLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["ERROR_MAP", "MODULE_ID", "WEB_ROLES", "RunsTraceLink", "module"]
