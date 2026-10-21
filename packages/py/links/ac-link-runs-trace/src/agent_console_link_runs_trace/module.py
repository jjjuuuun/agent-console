"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-runs-trace``).

실행 기록(``mod-runs``)과 위임 흐름 계산(``ac-trace``)을 잇는다(design §3R.1.4 L6).

- 필수: ``runs.reader``·``runs.events``. 선택: ``definitions.lookup``(당시 팀 구성의 연결 종류).
- 경로: ``GET /runs/{id}/trace``·``GET /runs/handoffs``.
- 이 연동이 꺼지면 경로가 404이고 웹은 실행 상세의 흐름 탭·넘김 보기를 숨긴다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS, ErrorCodes
from agent_console_modkit import ErrorMapping, ModuleContext, ModuleDescriptor, ModuleParts

from .ports import DEFINITIONS_LOOKUP, RUNS_EVENTS, RUNS_READER
from .routes import build_router
from .views import RunNotFoundError, TraceViews

MODULE_ID = "link-runs-trace"
WEB_ROLES: tuple[str, ...] = ("runs:trace",)
"""웹 연동 부분 역할(실행 상세 흐름 탭·넘김 보기)."""

ERROR_MAP: dict[type[Exception], ErrorMapping] = {RunNotFoundError: ErrorCodes.NOT_FOUND}


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
        description="위임 흐름(/runs/{id}/trace)·넘김 집계(/runs/handoffs)",
        requires=(RUNS_READER, RUNS_EVENTS),
        optional=(DEFINITIONS_LOOKUP,),
        contracts={"runs": CONTRACT_VERSIONS["runs"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        runs = ctx.port(RUNS_READER)
        events = ctx.port(RUNS_EVENTS)
        if runs is None or events is None:  # pragma: no cover - 조립기가 보장한다
            raise RuntimeError("runs.reader·runs.events가 없습니다")
        views = TraceViews(runs, events, history=lambda: ctx.port(DEFINITIONS_LOOKUP))
        return ModuleParts(routers=[build_router(lambda: views)], error_map=dict(ERROR_MAP))


module = RunsTraceLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["ERROR_MAP", "MODULE_ID", "WEB_ROLES", "RunsTraceLink", "module"]
