"""agent-console-link-runs-sdd: 스펙 작업 ↔ 팀 구성 실행 연동(design §6R.1.5·§6R.1.6·§6R.3).

공개 API:
    - ``RunsTaskIntegration``: 작업 연동 X43(실행 프로필 = 작업 동작, ``invoke``·``start``·
      ``links``·``check_profile``·``task_issues``). ``link_kinds = ("run",)``.
    - ``RunsVerificationSource``: 검증 출처 X42 ``runs``(검증 목적 실행 → ``VerificationResult``).
    - ``StatusReflector``·``TrackedRun``: 실행 상태 이벤트 → 실행 프로필 ``status_on`` 반영(작업
      머리
      줄 하나, 줄 해시 충돌 규칙). 반영 뒤 알림 ``add_listener``(자동 진행 자리).
    - ``labeled_runs``·``run_time``: 라벨 질의 페이지 모으기.
    - ``start_issue``: 실행 시작 예외 → 오류 이슈.
    - ``RunsSddSettings``: 설치자 설정(기본값 = 패키지 데이터 ``data/defaults.json``).
    - 모듈: ``module``(entry point ``link-runs-sdd``).
    - 가짜: ``agent_console_link_runs_sdd.testing``.
"""

from __future__ import annotations

from .integration import SECRET_REJECT, RunsTaskIntegration, start_issue
from .module import MODULE_ID, RunsSddLink, module
from .records import labeled_runs, run_time
from .reflect import (
    REASON_ERROR,
    REASON_GATE_BLOCKED,
    REASON_TASK_CHANGED,
    RunListener,
    StatusReflector,
    TrackedRun,
)
from .settings import RunsSddSettings, package_defaults
from .verification import RunsVerificationSource

__all__ = [
    "MODULE_ID",
    "REASON_ERROR",
    "REASON_GATE_BLOCKED",
    "REASON_TASK_CHANGED",
    "SECRET_REJECT",
    "RunListener",
    "RunsSddLink",
    "RunsSddSettings",
    "RunsTaskIntegration",
    "RunsVerificationSource",
    "StatusReflector",
    "TrackedRun",
    "labeled_runs",
    "module",
    "package_defaults",
    "run_time",
    "start_issue",
]
