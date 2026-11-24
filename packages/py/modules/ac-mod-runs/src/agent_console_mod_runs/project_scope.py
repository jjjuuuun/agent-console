"""맡는 범위 없는 프로젝트 실행 정책(5.7R.33t1, design K33-10·§PI.10 끄기 표).

프로젝트 기능(선택 포트 ``projects.lookup``)이 켜진 조립에서 ``project_id``를 붙인 실행을 맡는 실행
범위 공급자(``runs.scopes``의 ``RunProjectScoper``, 보통 ``link-projects-runs``)가 없으면, 그 실행은
프로젝트 폴더·사전 점검·정의 출처 없이 서버 작업 폴더에서 돈다. 이 모듈은 그때 막을지(설정
``unscoped_project_runs``)와 오류·경고 본문을 만든다. 실행 모듈은 프로젝트를 모른다 — "프로젝트
기능이 있나"는 호출자가 함수로 넘긴다.

>>> from agent_console_mod_runs.settings import UnscopedProjectRuns
>>> gate = unscoped_project_policy(UnscopedProjectRuns(), projects_on=lambda: True)
>>> error = gate("p1")
>>> (error.code, error.details["port"], error.details["project_id"])
('feature_unavailable', 'runs.scopes', 'p1')
>>> unscoped_project_policy(UnscopedProjectRuns(), projects_on=lambda: False)("p1") is None
True
>>> unscoped_project_policy(UnscopedProjectRuns(policy="allow"), projects_on=lambda: True)("p1")
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from agent_console_contracts import ErrorCodes, ErrorInfo, Issue

from .settings import UnscopedProjectRuns

UNSCOPED_PROJECT_PORT: Final = "runs.scopes"
"""막은 오류·경고의 ``details.port``(프로젝트 범위를 맡는 공급자가 들어오는 포트)."""

DEFAULT_MODULE_ID: Final = "mod-runs"
"""오류·경고의 ``details.module`` 기본값(요청을 받은 모듈 id)."""


def _details(module_id: str) -> dict[str, str]:
    return {"module": module_id, "port": UNSCOPED_PROJECT_PORT}


def unscoped_project_policy(
    settings: UnscopedProjectRuns,
    *,
    projects_on: Callable[[], bool],
    module_id: str = DEFAULT_MODULE_ID,
) -> Callable[[str], ErrorInfo | None]:
    """``RunService(unscoped_project=)``에 넘길 함수: ``project_id`` → 막을 오류 또는 None.

    Args:
        settings: 정책·문구(``RunsModuleSettings.unscoped_project_runs``).
        projects_on: 지금 프로젝트 기능이 있나(예: 선택 포트 ``projects.lookup``이 있나). 요청마다
            부른다.
        module_id: 오류 ``details.module``.

    Returns:
        ``policy = reject``이고 프로젝트 기능이 있으면 409 ``feature_unavailable``
        (``details = {module, port: "runs.scopes", project_id}``), 아니면 None.
    """

    def check(project_id: str) -> ErrorInfo | None:
        if settings.policy != "reject" or not projects_on():
            return None
        return ErrorInfo(
            code=ErrorCodes.FEATURE_UNAVAILABLE,
            message=settings.message,
            details={**_details(module_id), "project_id": project_id},
        )

    return check


def unscoped_project_warning(
    settings: UnscopedProjectRuns, *, module_id: str = DEFAULT_MODULE_ID
) -> Issue:
    """서버 정보(``server.warnings``) 경고: 프로젝트를 붙인 실행·대화 턴이 지금 막힌다.

    화면은 ``code = feature_unavailable``·``details.port = "runs.scopes"``로 알아보고 시작 단추를
    막는다. 문구는 ``settings.message``.
    """
    return Issue(
        severity="warning",
        code=ErrorCodes.FEATURE_UNAVAILABLE,
        message=settings.message,
        details=_details(module_id),
    )


__all__ = [
    "DEFAULT_MODULE_ID",
    "UNSCOPED_PROJECT_PORT",
    "unscoped_project_policy",
    "unscoped_project_warning",
]
