"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-runs-sdd``).

스펙(``mod-sdd``)과 실행 기록(``mod-runs``)을 잇는다(design §6R.3·§6R.4).

- 필수: ``runs.starter``·``runs.reader``·``sdd.service``. 구독: ``runs.event``(결과 반영).
- 제공: ``sdd.integrations``(작업 연동 ``runs`` — 실행 프로필 동작·실행 연결·프로필 검사·결과
  반영 이슈), ``sdd.verification_sources``(검증 출처 ``runs``).
- 설정 ``modules.options.link-runs-sdd``(``RunsSddSettings``, 기본값 = 패키지 데이터).
- 이 연동(또는 ``mod-runs``)이 꺼지면 스펙 화면의 실행 버튼·실행 칩·검증 열이 없고
  (``capabilities.runs=false``), 문서·작업·계획·추적(요구 ↔ 작업)은 그대로 동작한다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .integration import RunsTaskIntegration
from .ports import (
    RUNS_EVENT,
    RUNS_READER,
    RUNS_STARTER,
    SDD_INTEGRATIONS,
    SDD_SERVICE,
    SDD_VERIFICATION_SOURCES,
)
from .reflect import StatusReflector
from .settings import RunsSddSettings, finished_statuses, max_kept_issues
from .verification import RunsVerificationSource

MODULE_ID = "link-runs-sdd"


def _version() -> str:
    try:
        return version("agent-console-link-runs-sdd")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class RunsSddLink:
    """스펙 ↔ 실행 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="스펙·실행 연동",
        description="스펙 작업을 팀 구성으로 실행하고 결과를 작업 표시와 추적 표에 반영한다",
        provides=(SDD_INTEGRATIONS, SDD_VERIFICATION_SOURCES),
        requires=(RUNS_STARTER, RUNS_READER, SDD_SERVICE),
        contracts={"sdd": CONTRACT_VERSIONS["sdd"], "runs": CONTRACT_VERSIONS["runs"]},
        settings_schema=RunsSddSettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        starter = ctx.port(RUNS_STARTER)
        reader = ctx.port(RUNS_READER)
        sdd = ctx.port(SDD_SERVICE)
        if starter is None or reader is None or sdd is None:  # pragma: no cover - 조립기가 보장
            raise RuntimeError("runs.starter·runs.reader·sdd.service가 없습니다")
        cfg = ctx.settings if isinstance(ctx.settings, RunsSddSettings) else RunsSddSettings()
        reflector = StatusReflector(
            sdd,
            run_outcomes=cfg.run_outcomes,
            status_events=cfg.status_events,
            finished_statuses=finished_statuses(),
            max_issues=max_kept_issues(),
        )
        integration = RunsTaskIntegration(
            sdd=sdd, starter=starter, reader=reader, reflector=reflector, settings=cfg
        )
        ctx.provide(SDD_INTEGRATIONS, integration)
        ctx.provide(SDD_VERIFICATION_SOURCES, RunsVerificationSource(integration))
        ctx.subscribe(RUNS_EVENT, reflector.on_event)
        return ModuleParts()


module = RunsSddLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "RunsSddLink", "module"]
