"""mod-projects 설정(설치자 값, ``modules.options.mod-projects``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import SeedSetting, SettingsCompat
from agent_console_project_space import DEFAULT_CONFIG_DIR

DEFAULT_DIRECTORY = "projects"
"""등록부 폴더(워크스페이스 기준, ``projects/<id>.yaml``, design §PI.2)."""


class FolderDialogSettings(BaseModel):
    """서버 컴퓨터의 폴더 선택 창을 띄우는 방법입니다."""

    # X35: 명령 표 = ac-local-folders 패키지 데이터 + providers, 코드 제공자 = entry point.

    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "off"] = Field(
        default="auto",
        title="폴더 선택 창",
        description="auto면 서버 컴퓨터에서 쓸 수 있는 선택 창을 찾아 쓴다. off면 앱 안 찾아보기만 "
        "쓴다.",
        json_schema_extra=x_ui(tier="advanced", enum_labels={"auto": "자동", "off": "쓰지 않음"}),
    )
    providers: list[dict[str, Any]] | None = Field(
        default=None,
        title="선택 창 명령",
        description=(
            "더하거나 바꿀 선택 창 명령 목록. 같은 id는 기본 항목을 바꾸고, enabled를 false로 "
            "두면 뺀다. 비우면 기본 목록만."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example=[{"id": "my-picker", "platforms": ["linux"], "argv": ["my-picker"]}],
        ),
    )
    include_default_providers: bool = Field(
        default=True,
        title="기본 명령 함께 쓰기",
        description="패키지에 들어 있는 기본 선택 창 명령(Windows·macOS·Linux)을 함께 쓴다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    timeout_seconds: float = Field(
        default=300.0,
        ge=1,
        title="선택 창 대기 시간",
        description="사용자가 폴더를 고를 때까지 기다리는 최대 시간. 지나면 창을 닫는다.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )


class ProjectModuleSettings(BaseModel):
    """프로젝트 모듈 설정."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(
        title="등록부 폴더",
        json_schema_extra=x_ui(tier="advanced"),
        default=DEFAULT_DIRECTORY,
        pattern=r"^[A-Za-z0-9_\-]+$",
        description="프로젝트 등록 파일을 둘 워크스페이스 안 폴더 이름.",
    )
    config_dir: str = Field(
        title="프로젝트 구성 폴더 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default=DEFAULT_CONFIG_DIR,
        min_length=1,
        description=(
            "프로젝트 폴더 안에 이 앱이 구성·기록을 두는 폴더 이름. 다른 이름을 쓰는 앱끼리는 같은 "
            "폴더의 구성을 보지 못한다."
        ),
    )
    records_file: str | None = Field(
        default=None,
        title="기록 DB 파일 이름",
        description="프로젝트 구성 폴더 안 기록 DB 파일 이름. 비우면 패키지 기본값"
        "(records.sqlite3).",
        json_schema_extra=x_ui(tier="advanced", example="records.sqlite3"),
    )
    messages: dict[str, str] = Field(
        title="문구 바꾸기",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=dict,
        description="이슈 문구 바꾸기(문제 코드 → 문구 틀, $이름 자리 채움). 비운 코드는 "
        "기본 문구.",
    )
    working_directory: Path | None = Field(
        default=None,
        title="앱 작업 폴더(읽지 않음)",
        description=(
            "더 이상 읽지 않습니다. 로그는 등록한 프로젝트 전체를 모읍니다(옛 로그 범위 current용 "
            "값이었음). 설정에서 지워도 됩니다."
        ),
        json_schema_extra={"deprecated": True, **x_ui(tier="advanced", example="./project")},
    )
    snapshot_ttl_seconds: float = Field(
        title="정의 목록 재사용 시간",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
        default=2.0,
        ge=0,
        description="옛 범위 정리 화면이 읽은 정의 목록을 다시 쓰는 시간. 0이면 매번 읽는다.",
    )
    status_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        title="폴더 상태 확인 시간 상한",
        description="프로젝트 폴더 상태를 확인할 때 기다리는 최대 시간. 느린 드라이브에서 화면이 "
        "멈추지 않게 한다.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    browse_roots: list[str] | None = Field(
        default=None,
        title="찾아보기 시작 위치",
        description="앱 안 찾아보기의 시작 위치·범위(절대 경로). 비우면 홈·드라이브 등 기본값.",
        json_schema_extra=x_ui(tier="advanced", example=["/home/me/work"]),
    )
    allow_remote_browse: bool = Field(
        default=False,
        title="원격 바인딩에서 찾아보기 허용",
        description=(
            "서버가 루프백이 아닌 주소에 묶였을 때도 폴더 찾아보기·확인을 연다. 네이티브 선택 창은 "
            "이 값과 무관하게 루프백에서만 열린다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )
    server_host: str | None = Field(
        default=None,
        title="서버 바인딩 주소",
        description="서버가 묶인 주소(서버 설정 host를 자동으로 이어받는다). 비우면 "
        "루프백으로 본다.",
        json_schema_extra=x_ui(tier="advanced", example="127.0.0.1"),
    )
    case_insensitive_paths: list[str] = Field(
        default_factory=list,
        title="대소문자 무시 경로",
        description=(
            "폴더 비교에서 대소문자를 무시할 POSIX 경로 앞부분(fnmatch, 예 /mnt/?). Windows 경로는 "
            "늘 무시한다."
        ),
        json_schema_extra=x_ui(tier="advanced", example=["/mnt/?"]),
    )
    max_open_spaces: int = Field(
        default=8,
        ge=1,
        title="동시에 열어 둘 프로젝트 공간 수",
        description="열어 둔 프로젝트 공간 캐시 상한. 넘으면 오래 안 쓴 것부터 닫는다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    idle_close_seconds: float = Field(
        default=300.0,
        ge=0,
        title="안 쓰는 공간 닫기",
        description="이 시간 동안 쓰지 않은 프로젝트 공간을 캐시에서 뺀다. 0이면 빼지 않는다.",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    records_space_prefix: str = Field(
        default="project:",
        title="기록 공간 이름 접두",
        description="기록 공간 이름 = 이 접두 + 등록 id(기록 연동 설정 space_prefix를 이어받는다).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    folder_dialog: FolderDialogSettings = Field(
        default_factory=FolderDialogSettings,
        title="네이티브 폴더 선택 창",
        description="[폴더 선택…]이 띄우는 서버 컴퓨터의 폴더 선택 창 설정.",
        json_schema_extra=x_ui(tier="advanced"),
    )


SETTINGS_COMPAT = SettingsCompat(
    seeds=(
        SeedSetting("server_host", "host"),
        SeedSetting("records_space_prefix", "modules.options.link-projects-records.space_prefix"),
    ),
)
"""다른 설정 값을 기본값으로 이어받는다(값이 없을 때만): 서버 바인딩 주소, 기록 연동의 공간 이름
접두. 실행 모듈 작업 폴더는 5.7R.33i부터 이어받지 않는다(옛 로그 범위 current 삭제)."""


__all__ = [
    "DEFAULT_DIRECTORY",
    "SETTINGS_COMPAT",
    "FolderDialogSettings",
    "ProjectModuleSettings",
]
