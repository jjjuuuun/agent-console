"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-logs-trace``).

로그 색인(``mod-logs``의 ``logs.query``)과 위임 흐름 모양(``Trace``)을 잇는다(design §4R.8).

- 필수: ``logs.query``. 선택: 없음.
- 경로: ``GET /logs/sessions/{session}/trace``.
- 이 연동이 꺼지면 경로가 404이고, 웹은 세션 화면에서 위임 흐름 그림을 숨긴다
  (웹 역할 ``logs:trace``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS, ErrorCodes
from agent_console_modkit import ErrorMapping, ModuleContext, ModuleDescriptor, ModuleParts

from .ports import LOGS_QUERY
from .routes import build_router
from .settings import LogTraceSettings
from .views import LogTraceViews, SessionNotFoundError

MODULE_ID = "link-logs-trace"
WEB_ROLES: tuple[str, ...] = ("logs:trace",)
"""웹 연동 부분 역할(세션 화면의 위임 흐름 그림)."""

ERROR_MAP: dict[type[Exception], ErrorMapping] = {SessionNotFoundError: ErrorCodes.NOT_FOUND}


def _version() -> str:
    try:
        return version("agent-console-link-logs-trace")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class LogsTraceLink:
    """로그 ↔ 위임 흐름 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="로그·추적 연동",
        description="세션 로그 위임 흐름(/logs/sessions/{id}/trace)",
        requires=(LOGS_QUERY,),
        contracts={"logs": CONTRACT_VERSIONS["logs"], "runs": CONTRACT_VERSIONS["runs"]},
        settings_schema=LogTraceSettings,
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        query = ctx.port(LOGS_QUERY)
        if query is None:  # pragma: no cover - 조립기가 보장한다
            raise RuntimeError("logs.query가 없습니다")
        cfg = ctx.settings if isinstance(ctx.settings, LogTraceSettings) else LogTraceSettings()
        views = LogTraceViews(query, link_keys=cfg.link_keys, max_events=cfg.max_events)
        return ModuleParts(routers=[build_router(lambda: views)], error_map=dict(ERROR_MAP))


module = LogsTraceLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["ERROR_MAP", "MODULE_ID", "WEB_ROLES", "LogsTraceLink", "module"]
