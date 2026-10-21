"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-runs-usage``).

실행 기록(``mod-runs``)과 사용량(``mod-usage``)을 잇는다(design §3R.1.4 L5·§3R.5).

- 필수: ``runs.reader``·``runs.events``. 구독: ``runs.event``(집계 캐시 표시).
- 제공: ``usage.event_query``(실행 이벤트 조회), ``usage.token_rollups``(증분 캐시 토큰 집계).
- 이 연동이 꺼지면 사용량 화면은 외부 출처(statusline 등)만 보이고 토큰 집계는 빈 목록이다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .ports import RUNS_EVENT, RUNS_EVENTS, RUNS_READER, USAGE_EVENT_QUERY, USAGE_TOKEN_ROLLUPS
from .rollups import IncrementalTokenRollups

MODULE_ID = "link-runs-usage"
WEB_ROLES: tuple[str, ...] = ("usage:tokens",)
"""웹 연동 부분 역할(사용량 화면 토큰 집계)."""


def _version() -> str:
    try:
        return version("agent-console-link-runs-usage")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class RunsUsageLink:
    """실행 ↔ 사용량 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="실행·사용량 연동",
        description="실행 이벤트 조회·플랫폼 실행분 토큰 집계(증분 캐시)",
        provides=(USAGE_EVENT_QUERY, USAGE_TOKEN_ROLLUPS),
        requires=(RUNS_READER, RUNS_EVENTS),
        contracts={"usage": CONTRACT_VERSIONS["usage"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        runs = ctx.port(RUNS_READER)
        events = ctx.port(RUNS_EVENTS)
        if runs is None or events is None:  # pragma: no cover - 조립기가 보장한다
            raise RuntimeError("runs.reader·runs.events가 없습니다")
        rollups = IncrementalTokenRollups(runs, events)
        ctx.provide(USAGE_EVENT_QUERY, events)
        ctx.provide(USAGE_TOKEN_ROLLUPS, rollups)
        ctx.subscribe(RUNS_EVENT, rollups.mark)
        return ModuleParts()


module = RunsUsageLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "RunsUsageLink", "module"]
