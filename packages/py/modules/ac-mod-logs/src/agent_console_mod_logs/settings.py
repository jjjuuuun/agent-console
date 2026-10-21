"""mod-logs 설정(설치자 값, ``modules.options.mod-logs``, design §4R.8).

출처 켜기·출처 설정·분류 체계·프로젝트 묶기·대시보드는 사용자 데이터(워크스페이스 설정 ``logs.*``)라
여기 없다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_logs import (
    DEFAULT_ARCHIVE_MAX_BYTES,
    DEFAULT_ARCHIVE_MAX_EVENTS,
    DEFAULT_ARCHIVE_TITLE,
    DEFAULT_BATCH_SIZE,
    DEFAULT_BUDGET_BYTES,
    SessionTitleRule,
)

DEFAULT_MAX_DETAIL_BYTES = 80_000
"""상세 응답의 detail·raw 상한 기본값(agent_bench ``bounded``와 같은 80,000)."""

DEFAULT_TIMELINE_LIMIT = 5000
"""타임라인 한 번에 싣는 이벤트 수 기본값(``agent_console_logs`` 색인 기본값과 같다)."""

DEFAULT_ARCHIVE_FILE_PREFIX = "agent-console-logs"
"""보관본 내려받기 파일 이름 앞부분 기본값(``<앞부분>-<UTC 시각>.json|html``)."""


class SessionTitleRuleOption(BaseModel):
    """세션 제목으로 쓸 이벤트를 고르는 규칙 하나입니다. 위 규칙부터 먼저 봅니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 세션 제목 순위 규칙 하나(``agent_console_logs.SessionTitleRule``의 설정 모양).

    model_config = ConfigDict(extra="forbid")

    tag: str = Field(
        min_length=1,
        title="태그",
        description="후보 이벤트의 태그(분류기가 붙인다).",
        json_schema_extra=x_ui(tier="basic", when="제목으로 쓸 이벤트 종류를 바꿀 때 고칩니다."),
    )
    pick: Literal["first", "last"] = Field(
        default="first",
        title="고르는 쪽",
        description="후보가 여럿이면 시각순 처음(first) 또는 마지막(last).",
        json_schema_extra=x_ui(tier="advanced"),
    )


class LogsModuleSettings(BaseModel):
    """로그 수집 주기·예산·보존·색인 위치(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    scan_interval_seconds: float = Field(
        default=30,
        ge=0,
        title="수집 주기",
        description="배경 수집 주기(초). 0이면 배경 수집 없음(수동 [지금 수집]만).",
        json_schema_extra=x_ui(
            tier="basic", unit="초", when="새 로그가 화면에 늦게 보이거나 디스크 읽기를 줄일 때."
        ),
    )
    startup_scan: bool = Field(
        default=True,
        title="시작할 때 수집",
        description="서버 시작 직후 한 번 수집한다(주기와 따로 정한다).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    scan_budget_bytes: int = Field(
        default=DEFAULT_BUDGET_BYTES,
        gt=0,
        title="한 번에 읽는 양",
        description="출처 하나를 한 번 수집할 때 읽는 최대 바이트. 남은 것은 다음 수집에서 읽는다.",
        json_schema_extra=x_ui(tier="advanced", unit="바이트", group="scan"),
    )
    batch_size: int = Field(
        default=DEFAULT_BATCH_SIZE,
        gt=0,
        title="한 번에 쓰는 이벤트 수",
        description="색인에 한 번에 묶어 쓰는 이벤트 수.",
        json_schema_extra=x_ui(tier="advanced", unit="개", group="scan"),
    )
    retention_days: float | None = Field(
        default=None,
        gt=0,
        title="보존 기간",
        description="이보다 오래된 색인 이벤트를 지운다(원본 파일은 건드리지 않는다). 비우면 영구.",
        json_schema_extra=x_ui(
            tier="basic", unit="일", example=30, when="색인 파일이 너무 커질 때 줄입니다."
        ),
    )
    index_path: Path | None = Field(
        default=None,
        title="색인 파일",
        description=(
            "색인을 둘 별도 SQLite 파일. 비우면 서버 DB를 쓴다. 상대 경로는 설정 파일 폴더 기준."
        ),
        json_schema_extra=x_ui(tier="advanced", example="state/logs-index.db"),
    )
    max_detail_bytes: int = Field(
        default=DEFAULT_MAX_DETAIL_BYTES,
        gt=0,
        title="상세 최대 크기",
        description="이벤트 상세(detail·raw)를 응답에 실을 최대 크기(넘으면 잘림 표시).",
        json_schema_extra=x_ui(tier="advanced", unit="바이트", group="view"),
    )
    timeline_limit: int = Field(
        default=DEFAULT_TIMELINE_LIMIT,
        gt=0,
        title="타임라인 이벤트 수",
        description="세션 타임라인에 한 번에 싣는 이벤트 수(넘으면 앞부분만).",
        json_schema_extra=x_ui(tier="advanced", unit="개", group="view"),
    )
    dashboard_templates_dir: Path | None = Field(
        default=None,
        title="대시보드 템플릿 폴더",
        description=(
            "대시보드 템플릿 폴더(*.yaml·*.json, 파일 하나 = 대시보드 하나). "
            "비우면 기본 템플릿. 상대 경로는 설정 파일 폴더 기준."
        ),
        json_schema_extra=x_ui(tier="advanced", example="dashboards", group="view"),
    )
    archive_max_events: int = Field(
        default=DEFAULT_ARCHIVE_MAX_EVENTS,
        gt=0,
        title="보관본 이벤트 수",
        description="보관본 내려받기에 담는 최대 이벤트 수. 넘으면 앞부분만 담는다.",
        json_schema_extra=x_ui(tier="advanced", unit="개", group="archive"),
    )
    archive_max_bytes: int = Field(
        default=DEFAULT_ARCHIVE_MAX_BYTES,
        gt=0,
        title="보관본 최대 크기",
        description="보관본에 담는 이벤트 크기 합의 상한. 넘으면 앞부분만 담는다.",
        json_schema_extra=x_ui(tier="advanced", unit="바이트", group="archive"),
    )
    archive_file_prefix: str = Field(
        default=DEFAULT_ARCHIVE_FILE_PREFIX,
        min_length=1,
        pattern=r"^[A-Za-z0-9._-]+$",
        title="보관본 파일 이름",
        description="보관본 내려받기 파일 이름 앞부분(영문·숫자·._-).",
        json_schema_extra=x_ui(tier="advanced", group="archive"),
    )
    archive_title: str = Field(
        default=DEFAULT_ARCHIVE_TITLE,
        min_length=1,
        title="보관본 제목",
        description="보관본 HTML 파일 맨 위에 보이는 제목.",
        json_schema_extra=x_ui(tier="advanced", group="archive"),
    )
    session_title_rules: list[SessionTitleRuleOption] | None = Field(
        default=None,
        title="세션 제목 규칙",
        description=(
            "세션 제목을 고르는 규칙(위에서부터, 후보가 있는 첫 규칙이 이긴다). "
            "비우면 기본 규칙, 빈 목록이면 제목 없음."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )

    def title_rules(self) -> tuple[SessionTitleRule, ...] | None:
        """``session_title_rules`` → 질의 규칙(None = 패키지 기본 데이터)."""
        if self.session_title_rules is None:
            return None
        return tuple(SessionTitleRule(r.tag, r.pick) for r in self.session_title_rules)


__all__ = [
    "DEFAULT_ARCHIVE_FILE_PREFIX",
    "DEFAULT_MAX_DETAIL_BYTES",
    "DEFAULT_TIMELINE_LIMIT",
    "LogsModuleSettings",
    "SessionTitleRuleOption",
]
