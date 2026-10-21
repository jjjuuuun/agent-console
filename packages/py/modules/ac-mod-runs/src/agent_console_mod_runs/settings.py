"""mod-runs 설정(설치자 값, ``modules.options.mod-runs``).

옛 위치(통합 서버 최상위 ``runtime``·``backends``·``working_directory``)는 4R.18부터 읽지 않는다
(서버가 ``settings.removed_key`` 오류로 새 위치를 알린다, design §3R.1.6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import EnvSetting, RemovedSetting, SeedSetting, SettingsCompat

DEFAULT_RUN_FILES_DIR = Path("runs")
"""실행 묶음 파일 폴더(상태 폴더 기준 상대 경로)."""


class RuntimeOptions(BaseModel):
    """실행 엔진 한도."""

    model_config = ConfigDict(extra="forbid")

    max_concurrency: int | None = Field(
        default=None,
        ge=1,
        title="동시 실행 수",
        description="한꺼번에 실행하는 노드 수의 한도. 비우면 제한 없음.",
        json_schema_extra=x_ui(
            tier="basic",
            unit="개",
            example=4,
            when="컴퓨터가 느려지거나 사용량을 아낄 때 줄입니다.",
        ),
    )
    cancel_grace: float = Field(
        default=2.0,
        ge=0,
        title="취소 대기 시간",
        description="취소한 뒤 노드가 스스로 끝나기를 기다리는 시간.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    event_queue_size: int = Field(
        default=10_000,
        ge=1,
        title="이벤트 대기열 크기",
        description="실행 이벤트를 받는 쪽마다 쌓아 둘 수 있는 이벤트 수.",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
    )
    shutdown_timeout: float = Field(
        default=10.0,
        ge=0,
        title="종료 대기 시간",
        description="서버 종료 때 실행 중인 작업 정리를 기다리는 최대 시간(넘으면 강제 취소).",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )


class RunsModuleSettings(BaseModel):
    """실행 모듈 설정."""

    model_config = ConfigDict(extra="forbid")

    runtime: RuntimeOptions = Field(
        default_factory=RuntimeOptions,
        title="실행 한도",
        description="동시 실행 수·취소·종료 대기 같은 실행 엔진 한도.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    backends: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        title="실행 방식별 설치 옵션",
        description="실행 방식 id → 그 실행 방식이 받는 설치 옵션(키는 실행 방식이 정한다).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    working_directory: Path | None = Field(
        default=None,
        title="작업 폴더",
        description=(
            "에이전트가 파일을 읽고 쓰는 폴더. 상대 경로는 설정 파일 폴더 기준, 비우면 그 폴더."
        ),
        json_schema_extra=x_ui(
            tier="basic", example="./project", when="에이전트가 다른 프로젝트 폴더에서 일할 때."
        ),
    )
    run_files_dir: Path = Field(
        default=DEFAULT_RUN_FILES_DIR,
        title="실행 파일 폴더",
        description=(
            "실행마다 만드는 파일을 두는 폴더. 상대 경로는 상태 폴더(`<workspace>/.state`) 기준."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )
    min_redact_chars: int = Field(
        default=4,
        ge=1,
        title="가릴 비밀 최소 길이",
        description="이보다 짧은 비밀 값은 실행 기록에서 가리지 않는다(너무 짧으면 오탐이 많다).",
        json_schema_extra=x_ui(tier="advanced", unit="자"),
    )
    backend_probe_timeout_max_s: float = Field(
        default=20.0,
        gt=0,
        le=600,
        title="연결 테스트 최대 대기",
        description=(
            "실행 백엔드 [연결 테스트]가 기다리는 최대 시간. 요청이 더 길게 달라고 해도 이 값에서 "
            "멈춘다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            unit="초",
            when="느린 네트워크에서 연결 테스트가 자꾸 시간 초과로 끝날 때 늘립니다.",
        ),
    )
    resume_origin: str = Field(
        default="resume",
        title="이어 간 실행 표시",
        description="끊긴 실행을 이어 간 기록(대화 턴이 아닌 것)에 붙는 출처 이름.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    activity_limit: int = Field(
        default=100,
        ge=1,
        title="최근 활동 개수",
        description="에이전트 최근 활동 목록에 기본으로 보이는 개수.",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
    )


SETTINGS_COMPAT = SettingsCompat(
    removed=(
        RemovedSetting("runtime", new="modules.options.mod-runs.runtime"),
        RemovedSetting("backends", new="modules.options.mod-runs.backends"),
        RemovedSetting("working_directory", new="modules.options.mod-runs.working_directory"),
    ),
    env=(
        EnvSetting("WORKING_DIRECTORY", ("working_directory",)),
        EnvSetting("MAX_CONCURRENCY", ("runtime", "max_concurrency")),
    ),
    seeds=(SeedSetting("min_redact_chars", "secrets.min_redact_chars"),),
)
"""호스트 설정 호환: 옛 최상위 ``runtime``·``backends``·``working_directory``는 4R.18에서 읽기
호환을 끝냈다(``settings.removed_key`` 오류로 새 위치 안내). 환경변수
``<접두어>WORKING_DIRECTORY``·``MAX_CONCURRENCY``는 이 모듈 설정으로 들어간다. 호스트
``secrets.min_redact_chars``는
기록 가리기 최소 길이의 기본값이다."""


__all__ = [
    "DEFAULT_RUN_FILES_DIR",
    "SETTINGS_COMPAT",
    "RunsModuleSettings",
    "RuntimeOptions",
]
