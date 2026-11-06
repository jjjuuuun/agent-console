"""검증 결과 출처 ``runs``(X42 ``VerificationSource``, design §6R.1.6).

스펙 규칙 ``verification.purposes``에 든 목적 라벨의 루트 Run → ``VerificationResult``. 결과 값은
``result_map[결과 이름]``(없으면 ``result_map[실행 상태]``, 둘 다 없으면 결과 이름 그대로 —
계약 ``VerificationConfig.result_map`` 설명과 같다). 요구 id는 그 작업의 요구 역할 필드(지금
문서 기준)다. 목적이 비면 결과 없음.
"""

from __future__ import annotations

from agent_console_contracts.sdd import VerificationRef, VerificationResult
from agent_console_sdd import VerificationContext, find_task

from .integration import RunsTaskIntegration
from .ports import LABEL_PROFILE, LABEL_PURPOSE, LABEL_TASK
from .records import run_time


class RunsVerificationSource:
    """검증 목적 실행 → 검증 결과(``sdd.verification_sources`` 항목).

    Args:
        integration: 실행 기록을 읽는 작업 연동(같은 라벨·읽기 한도를 쓴다).
    """

    def __init__(self, integration: RunsTaskIntegration) -> None:
        self.integration = integration

    @property
    def id(self) -> str:
        return self.integration.settings.verification_source_id

    async def collect(self, ctx: VerificationContext) -> list[VerificationResult]:
        spec_ctx = ctx.spec
        config = spec_ctx.spec.rules.verification
        if config is None or not config.purposes:
            return []
        sdd = self.integration.sdd
        purpose_label = sdd.label_key(LABEL_PURPOSE)
        task_label = sdd.label_key(LABEL_TASK)
        profile_label = sdd.label_key(LABEL_PROFILE)
        titles = {p.id: p.title for p in spec_ctx.spec.rules.run_profiles or ()}
        outcome_of = self.integration.reflector.outcome_of
        out: list[VerificationResult] = []
        for purpose in dict.fromkeys(config.purposes):
            for run in self.integration.spec_runs(spec_ctx, {purpose_label: purpose}):
                key = run.labels.get(task_label)
                task = find_task(spec_ctx.index, key) if key else None
                outcome = outcome_of(run.status)
                status = config.result_map.get(outcome) or config.result_map.get(run.status)
                profile = run.labels.get(profile_label)
                out.append(
                    VerificationResult(
                        source=self.id,
                        status=status or outcome,
                        task_key=key,
                        requirement_ids=list(task.requirements) if task is not None else [],
                        label=titles.get(profile or "", profile or purpose),
                        at=run_time(run),
                        ref=VerificationRef(run_id=run.id),
                    )
                )
        return out


__all__ = ["RunsVerificationSource"]
