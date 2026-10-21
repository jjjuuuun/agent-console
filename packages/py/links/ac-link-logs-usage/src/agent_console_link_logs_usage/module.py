"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-logs-usage``).

로그(``mod-logs``)와 사용량(``mod-usage``)을 잇는다(design §4R.8 연동 표 셋째 행).

- 필수: ``logs.query``(토큰 표본), ``usage.service``(존재 확인 — 사용량 모듈이 꺼지면 이 연동도
  꺼진다).
- 선택: ``logs.ingest``(첫 조회가 진행 중인 수집을 기다림).
- 제공: ``usage.sources``에 ``local-logs``(신뢰 등급 ``estimated``, 설정 없이 켜짐).
- 제공: ``logs.source_defaults`` — 이 PC에 로그 폴더가 있는 로그 출처를 기본으로 켠다(규칙 데이터
  ``data/auto_log_sources.json``, 설정 파일 무변경, 사용자가 적은 ``enabled``가 이김,
  ``autoenable``).
- 구독: ``logs.ingested`` → 표본 캐시 무효화.
- 이 연동이 꺼지면 사용량 출처 목록에 로컬 추정 창이 없다(나머지는 그대로).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import CONTRACT_VERSIONS, x_ui
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .autoenable import load_auto_log_sources, log_source_defaults
from .estimate import load_default_config
from .ports import (
    LOGS_INGEST,
    LOGS_INGESTED,
    LOGS_QUERY,
    SOURCE_DEFAULTS,
    USAGE_SERVICE,
    USAGE_SOURCES,
)
from .source import DEFAULT_SOURCE_ID, LocalLogsUsageSource

MODULE_ID = "link-logs-usage"
WEB_ROLES: tuple[str, ...] = ()
"""웹 연동 부분 역할 없음(사용량 화면이 출처 목록으로 그린다)."""


class LogsUsageLinkSettings(BaseModel):
    """세션 로그로 사용량을 셀 때 쓰는 설치자 설정입니다. 창·예산은 사용량 설정에서 정합니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 설치자 설정(``modules.options.link-logs-usage``). 창·예산·필터는 사용자 데이터
    # (워크스페이스 설정 ``usage.sources``)라 여기 없다.

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(
        title="사용량 출처 id",
        json_schema_extra=x_ui(tier="advanced"),
        default=DEFAULT_SOURCE_ID,
        min_length=1,
        description="로그로 만든 사용량 출처의 id. 플러그인 출처와 겹치면 빠진다.",
    )
    defaults_file: str | None = Field(
        title="기본값 파일",
        json_schema_extra=x_ui(tier="advanced", example="usage-defaults.json"),
        default=None,
        description=(
            "설정에서 생략한 키의 기본값 JSON 파일(상대 경로면 설정 파일 폴더 기준). 비우면 기본값."
        ),
    )
    auto_enable_log_sources: bool = Field(
        title="로그 출처 자동 켜기",
        json_schema_extra=x_ui(
            tier="basic", when="Claude Code 로그를 자동으로 읽지 않게 하고 싶을 때 끕니다."
        ),
        default=True,
        description=(
            "이 PC에 로그 폴더가 있는 출처(기본: Claude Code 세션 로그)를 읽기 전용으로 켠다. "
            "직접 적은 값이 이긴다."
        ),
    )
    auto_log_sources_file: str | None = Field(
        title="자동 켜기 규칙 파일",
        json_schema_extra=x_ui(tier="advanced", example="auto-log-sources.json"),
        default=None,
        description="자동 켜기 규칙 JSON 파일(상대 경로면 설정 파일 폴더 기준). 비우면 기본 규칙.",
    )
    first_scan_wait_seconds: float = Field(
        default=5.0,
        ge=0,
        title="첫 조회 대기 시간",
        description="첫 사용량 조회가 로그 수집을 기다리는 최대 시간(초). 0이면 기다리지 않는다.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )


def _version() -> str:
    try:
        return version("agent-console-link-logs-usage")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class LogsUsageLink:
    """로그 ↔ 사용량 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="로그·사용량 연동",
        description=(
            "로컬 로그 토큰 추정 창(사용량 출처 local-logs, 신뢰 등급 estimated)과 "
            "이 PC에 있는 로그 출처의 기본 켜기"
        ),
        provides=(USAGE_SOURCES, SOURCE_DEFAULTS),
        requires=(LOGS_QUERY, USAGE_SERVICE),
        optional=(LOGS_INGEST,),
        settings_schema=LogsUsageLinkSettings,
        contracts={"usage": CONTRACT_VERSIONS["usage"], "logs": CONTRACT_VERSIONS["logs"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, LogsUsageLinkSettings):
            cfg = LogsUsageLinkSettings()
        defaults = None
        if cfg.defaults_file:
            defaults = load_default_config(self._path(cfg.defaults_file, ctx))
        query = ctx.port(LOGS_QUERY)
        if query is None:  # pragma: no cover - 조립기가 보장한다
            raise RuntimeError("logs.query가 없습니다")
        source = LocalLogsUsageSource(
            query,
            source_id=cfg.source_id,
            defaults=defaults,
            ingest=lambda: ctx.port(LOGS_INGEST),
            first_scan_wait_seconds=cfg.first_scan_wait_seconds,
        )
        ctx.provide(USAGE_SOURCES, source)
        ctx.subscribe(LOGS_INGESTED, source.on_ingested)
        if cfg.auto_enable_log_sources:
            rules = load_auto_log_sources(
                self._path(cfg.auto_log_sources_file, ctx) if cfg.auto_log_sources_file else None
            )
            environ = ctx.environ
            ctx.provide(SOURCE_DEFAULTS, lambda: log_source_defaults(rules, environ))
        return ModuleParts()

    @staticmethod
    def _path(value: str, ctx: ModuleContext) -> Path:
        path = Path(value)
        if not path.is_absolute() and ctx.paths is not None:
            path = ctx.paths.base_dir / path
        return path


module = LogsUsageLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "LogsUsageLink", "LogsUsageLinkSettings", "module"]
