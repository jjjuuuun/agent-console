"""mod-runs 설정(설치자 값, ``modules.options.mod-runs``).

옛 위치(통합 서버 최상위 ``runtime``·``backends``·``working_directory``)는 4R.18부터 읽지 않는다
(서버가 ``settings.removed_key`` 오류로 새 위치를 알린다, design §3R.1.6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class BackendLoginOptions(BaseModel):
    """실행 백엔드 계정 로그인(앱 화면에서 시작·완료)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        title="앱 화면 로그인",
        description=(
            "실행 백엔드 계정 로그인·로그아웃을 앱 화면에서 할 수 있게 한다. 끄면 그 버튼과 경로가 "
            "없어진다(터미널에서 로그인한 정보는 그대로 쓴다)."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="이 PC에서 앱이 로그인 과정을 띄우지 않게 할 때 끕니다."
        ),
    )
    timeout_s: float = Field(
        default=300.0,
        gt=0,
        title="로그인 기본 시간",
        description="로그인 한 번을 기다리는 기본 시간. 넘으면 멈추고 다시 시도하게 한다.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    timeout_max_s: float = Field(
        default=900.0,
        gt=0,
        le=3600,
        title="로그인 최대 시간",
        description="화면이 더 길게 달라고 해도 이 시간에서 멈춘다.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    heartbeat_s: float = Field(
        default=30.0,
        gt=0,
        title="화면 연결 확인 간격",
        description="로그인 창이 이 시간 넘게 상태를 묻지 않으면(창을 닫음 등) 로그인을 취소한다.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    retain_s: float = Field(
        default=60.0,
        ge=0,
        title="끝난 로그인 보관 시간",
        description="끝난 로그인 결과를 다시 볼 수 있는 시간.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    screen_max_lines: int = Field(
        default=40,
        ge=0,
        le=500,
        title="로그인 화면 줄 수",
        description="문제 해결용으로 보여 주는 로그인 과정 화면의 마지막 줄 수.",
        json_schema_extra=x_ui(tier="advanced", unit="줄"),
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
    show_hidden_backends: bool = Field(
        default=False,
        title="숨긴 실행 방식 보이기",
        description=(
            "개발·테스트용으로 숨겨 둔 실행 방식(예: 가짜 에이전트)을 선택지와 설정 카드에 "
            "보이게 한다. 꺼 두어도 이미 지정한 정의는 그대로 실행된다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="테스트·e2e·화면 개발에서 모델을 부르지 않는 실행 방식을 고를 때 켭니다.",
        ),
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
    backend_login: BackendLoginOptions = Field(
        default_factory=BackendLoginOptions,
        title="실행 백엔드 로그인",
        description="앱 화면에서 실행 백엔드 계정(예: 구독)에 로그인하는 기능의 시간·표시 한도.",
        json_schema_extra=x_ui(tier="advanced"),
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
    observe_event_prefixes: list[str] | None = Field(
        default=None,
        title="관측 탭 이벤트 접두어",
        description=(
            "실행 상세 [관측] 탭이 모을 실행 이벤트 type 접두어(예: mcp.). "
            "비우면 패키지 기본, 빈 목록이면 관측 탭에 아무 이벤트도 모으지 않는다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example=["hook.", "mcp."],
            when="새 관측 수집기가 다른 접두어로 이벤트를 낼 때 더하거나, 관측 탭을 끌 때.",
        ),
    )

    @field_validator("observe_event_prefixes")
    @classmethod
    def _clean_prefixes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(v.strip() for v in value if v.strip()))


SETTINGS_COMPAT = SettingsCompat(
    removed=(
        RemovedSetting("runtime", new="modules.options.mod-runs.runtime"),
        RemovedSetting("backends", new="modules.options.mod-runs.backends"),
        RemovedSetting("working_directory", new="modules.options.mod-runs.working_directory"),
    ),
    env=(
        EnvSetting("WORKING_DIRECTORY", ("working_directory",)),
        EnvSetting("MAX_CONCURRENCY", ("runtime", "max_concurrency")),
        EnvSetting("SHOW_HIDDEN_BACKENDS", ("show_hidden_backends",)),
    ),
    seeds=(SeedSetting("min_redact_chars", "secrets.min_redact_chars"),),
)
"""호스트 설정 호환: 옛 최상위 ``runtime``·``backends``·``working_directory``는 4R.18에서 읽기
호환을 끝냈다(``settings.removed_key`` 오류로 새 위치 안내). 환경변수
``<접두어>WORKING_DIRECTORY``·``MAX_CONCURRENCY``·``SHOW_HIDDEN_BACKENDS``는 이 모듈 설정으로
들어간다. 호스트
``secrets.min_redact_chars``는
기록 가리기 최소 길이의 기본값이다."""


__all__ = [
    "DEFAULT_RUN_FILES_DIR",
    "SETTINGS_COMPAT",
    "BackendLoginOptions",
    "RunsModuleSettings",
    "RuntimeOptions",
]
