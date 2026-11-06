"""link-runs-sdd 설치자 설정(``modules.options.link-runs-sdd``, design §6R.1.5·§6R.1.6).

기본값은 패키지 데이터(``data/defaults.json``)에 있다(이름·숫자를 코드 두 곳에 두지 않는다).
실행 프로필·``status_on``·검증 ``purposes``·``result_map``은 사용자 데이터(스펙 규칙)라 여기 없다.
여기 두는 것은 연동 이름(REST 경로·검증 출처 id), 실행 ``origin``, 실행 상태 → 결과 이름 표, 읽기
한도뿐이다.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

DEFAULTS_RESOURCE = "data/defaults.json"
"""설치자 옵션 기본값(패키지 데이터)."""


@cache
def _data(name: str) -> Any:
    text = resources.files("agent_console_link_runs_sdd").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


def package_defaults() -> dict[str, Any]:
    """설치자 옵션 기본값 사본(패키지 데이터)."""
    copied: dict[str, Any] = json.loads(json.dumps(_data(DEFAULTS_RESOURCE)))
    return copied


_D = package_defaults()


class RunsSddSettings(BaseModel):
    """스펙 작업을 팀 구성 실행으로 돌리는 연동의 이름·결과 표·한도(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    integration_id: str = Field(
        default=_D["integration_id"],
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$",
        title="연동 이름",
        description=(
            "작업 동작 주소와 실행 메뉴 항목이 쓰는 연동 이름입니다. 바꾸면 화면이 기억한 동작 "
            "이름도 바뀝니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="runs",
            when="다른 작업 연동 플러그인과 이름이 겹칠 때만 바꾸세요.",
        ),
    )
    verification_source_id: str = Field(
        default=_D["verification_source_id"],
        min_length=1,
        title="검증 출처 이름",
        description=(
            "검증 목적 실행의 결과를 추적 표에 넣는 검증 출처의 이름입니다. 스펙 설정의 검증 "
            "출처 목록에서 이 이름으로 끄고 켭니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="runs",
            when="다른 검증 출처 플러그인과 이름이 겹칠 때만 바꾸세요.",
        ),
    )
    origin: str = Field(
        default=_D["origin"],
        min_length=1,
        title="실행 시작 경로 이름",
        description="작업에서 시작한 실행의 시작 경로(Run origin)로 남길 이름입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="sdd",
            when="실행 목록에서 작업 실행을 다른 이름으로 구분하고 싶을 때 바꾸세요.",
        ),
    )
    run_outcomes: dict[str, str] = Field(
        default_factory=lambda: dict(_D["run_outcomes"]),
        title="실행 상태 → 결과 이름",
        description=(
            "실행 상태(예: completed)를 스펙 규칙이 쓰는 결과 이름(예: succeeded)으로 바꿉니다. "
            "표에 없는 상태는 그 이름을 그대로 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example={"completed": "succeeded"},
            when="스펙 규칙에서 다른 결과 이름을 쓰고 싶을 때 고치세요.",
        ),
    )
    status_events: list[str] = Field(
        default_factory=lambda: list(_D["status_events"]),
        title="상태 반영 이벤트",
        description=(
            "이 실행 이벤트가 오면 실행 프로필 status_on대로 작업 상태를 바꿉니다. 비우면 "
            "상태를 바꾸지 않습니다(실행 연결 칩은 그대로 보입니다)."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example=["run.started", "run.completed"],
            when="실행이 끝날 때만 상태를 바꾸고 싶으면 시작 이벤트를 빼세요.",
        ),
    )
    max_link_runs: int = Field(
        default=_D["max_link_runs"],
        ge=1,
        title="스펙당 읽을 실행 수",
        description=(
            "작업 실행 칩·추적 표를 만들 때 스펙 하나에서 읽는 최근 실행 수의 상한입니다. 넘으면 "
            "오래된 실행은 보이지 않습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            unit="개",
            when="실행이 아주 많은 스펙에서 화면이 느릴 때 줄이세요.",
        ),
    )
    page_size: int = Field(
        default=_D["page_size"],
        ge=1,
        le=1000,
        title="한 번에 읽을 실행 수",
        description="실행 기록을 읽을 때 한 쪽에 담는 실행 수입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="개", when="보통은 바꾸지 않아도 됩니다."),
    )


def finished_statuses() -> frozenset[str]:
    """끝난 실행 상태(패키지 데이터 — 계약 ``RunStatus`` 어휘 중 종료 상태)."""
    return frozenset(_D["finished_statuses"])


def max_kept_issues() -> int:
    """기억하는 ``sdd.status_not_applied`` 이슈 수 상한(패키지 데이터)."""
    return int(_D["max_kept_issues"])


__all__ = [
    "DEFAULTS_RESOURCE",
    "RunsSddSettings",
    "finished_statuses",
    "max_kept_issues",
    "package_defaults",
]
