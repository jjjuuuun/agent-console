"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-logs-runs``, design §4R.8).

실행 기록(``mod-runs``)과 로그(``mod-logs``)를 잇는다.

- 필수: ``logs.ingest``·``logs.query``·``runs.reader``·``runs.events``.
- 제공: ``logs.sources``에 런타임 출처 ``platform-runs``(분류기 ``platform-run-event``).
- 구독: ``runs.event`` → 그 Run의 수집을 예약한다(디바운스, 옵션 ``debounce_seconds``).
- 경로: ``GET /runs/{id}/logs``(그 Run 세션 id들의 외부 세션 이벤트, ``total`` 채움).
- 이 연동이 꺼지면 로그 화면에 플랫폼 실행이 없고, 실행 상세의 "세션 로그" 탭이 숨는다
  (웹 역할 ``logs:runs``).
"""

from __future__ import annotations

from collections.abc import Collection
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import CONTRACT_VERSIONS, x_ui
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .errors import ERROR_MAP
from .ports import (
    LOG_SOURCES,
    LOGS_INGEST,
    LOGS_QUERY,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    EventLike,
)
from .routes import build_router
from .scheduler import ScanDebouncer
from .source import platform_runs
from .views import RunLogs

MODULE_ID = "link-logs-runs"
WEB_ROLES: tuple[str, ...] = ("logs:runs",)
"""웹 연동 부분 역할(실행 상세 "세션 로그" 탭)."""

DEFAULT_DEBOUNCE_SECONDS = 1.0
"""실행 이벤트 → 수집 예약 디바운스 기본값(design §4R.4)."""


class LogsRunsSettings(BaseModel):
    """플랫폼 실행 기록을 세션 로그로 모으는 시점을 정하는 설치자 설정입니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 설치자 값(``modules.options.link-logs-runs``).

    model_config = ConfigDict(extra="forbid")

    debounce_seconds: float = Field(
        title="수집 예약 지연",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
        default=DEFAULT_DEBOUNCE_SECONDS,
        ge=0,
        description="실행 이벤트가 오면 이 시간 동안 모아 로그 수집을 한 번 예약한다(0 = 바로).",
    )


def _version() -> str:
    try:
        return version("agent-console-link-logs-runs")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class LogsRunsLink:
    """로그 ↔ 실행 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="로그·실행 연동",
        description=(
            "플랫폼 실행 이벤트 → 로그(런타임 출처 platform-runs)·실행 세션 로그(/runs/{id}/logs)"
        ),
        provides=(LOG_SOURCES,),
        requires=(LOGS_INGEST, LOGS_QUERY, RUNS_READER, RUNS_EVENTS),
        settings_schema=LogsRunsSettings,
        contracts={"logs": CONTRACT_VERSIONS["logs"], "runs": CONTRACT_VERSIONS["runs"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings if isinstance(ctx.settings, LogsRunsSettings) else LogsRunsSettings()
        runs = ctx.port(RUNS_READER)
        events = ctx.port(RUNS_EVENTS)
        ingest = ctx.port(LOGS_INGEST)
        query = ctx.port(LOGS_QUERY)
        if runs is None or events is None or ingest is None or query is None:
            raise RuntimeError("logs.*·runs.* 포트가 없습니다")  # pragma: no cover - 조립기가 보장
        item = platform_runs(runs, events)
        source_id = item.source.descriptor.id
        ctx.provide(LOG_SOURCES, item)

        def flush(run_ids: Collection[str]) -> None:
            hint = next(iter(run_ids)) if len(run_ids) == 1 else None
            ingest.request_scan([source_id], ref_hint=hint)

        debouncer = ScanDebouncer(flush, delay=cfg.debounce_seconds)

        def on_event(event: EventLike) -> None:
            item.source.invalidate(event.run_id)
            debouncer.mark(event.run_id)

        ctx.subscribe(RUNS_EVENT, on_event)
        views = RunLogs(runs, query, source_id=source_id)

        async def stop() -> None:
            debouncer.close()

        return ModuleParts(
            routers=[build_router(lambda: views)],
            error_map=dict(ERROR_MAP),
            shutdown=[stop],
        )


module = LogsRunsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "DEFAULT_DEBOUNCE_SECONDS",
    "MODULE_ID",
    "WEB_ROLES",
    "LogsRunsLink",
    "LogsRunsSettings",
    "module",
]
