"""mod-versions 설정(설치자 값, ``modules.options.mod-versions``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import RemovedSetting, SettingsCompat

DEFAULT_SECRET_ISSUE_CODES: tuple[str, ...] = (
    "resource.plain_secret",
    "resource.override_secret_suspected",
)
"""저장 전 검사 이슈 중 "평문 비밀"을 뜻하는 기본 코드(비교 결과에서 값을 가린다)."""


class VersionedCollectionSetting(BaseModel):
    """버전 기록을 남길 정의 종류 하나입니다(예: 에이전트)."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 버전 경로를 붙일 컬렉션 하나(데이터).
    #
    # Attributes:
    #     path: 컬렉션 경로(``/agents``).
    #     kind: 저장소 정의 종류 이름(``agent``).
    #     id_param: 경로의 id 매개변수 이름(``agent_id``). None이면 싱글턴(id = 종류 이름).
    #     label: 오류·검사 메시지에 쓰는 이름.

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(
        pattern=r"^/[A-Za-z0-9_\-/]+$",
        title="경로",
        description="버전 기록을 붙일 목록 경로.",
        json_schema_extra=x_ui(tier="advanced", example="/agents"),
    )
    kind: str = Field(
        min_length=1,
        title="정의 종류",
        description="저장된 정의의 종류 이름.",
        json_schema_extra=x_ui(tier="advanced", example="agent"),
    )
    id_param: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        title="id 자리 이름",
        description="경로에서 정의 id가 들어가는 자리 이름. 비우면 하나뿐인 정의(id = 종류 이름).",
        json_schema_extra=x_ui(tier="advanced", example="agent_id"),
    )
    label: str = Field(
        default="",
        title="화면 이름",
        description="오류·검사 메시지에 쓰는 이름.",
        json_schema_extra=x_ui(tier="advanced", example="에이전트 설정"),
    )


DEFAULT_COLLECTIONS: tuple[VersionedCollectionSetting, ...] = (
    VersionedCollectionSetting(
        path="/agents", kind="agent", id_param="agent_id", label="에이전트 설정"
    ),
    VersionedCollectionSetting(path="/graphs", kind="graph", id_param="graph_id", label="팀 구성"),
    VersionedCollectionSetting(
        path="/resources", kind="resource", id_param="resource_id", label="리소스 설정"
    ),
    VersionedCollectionSetting(path="/settings", kind="settings", label="공통 설정"),
)
"""기본 버전 경로 표(데이터). 새 정의 종류는 항목 하나를 더하면 같은 경로가 생긴다."""


class VersionModuleSettings(BaseModel):
    """버전 경로·보존 개수."""

    model_config = ConfigDict(extra="forbid")

    max_per_definition: int | None = Field(
        title="정의마다 남길 버전 수",
        json_schema_extra=x_ui(
            tier="basic", unit="개", example=50, when="버전 기록이 너무 많이 쌓일 때 줄입니다."
        ),
        default=None,
        ge=1,
        description=(
            "정의마다 남길 버전 수(현재 포함, 실행이 쓴 팀 구성 버전은 더 남는다). 비우면 모두 "
            "남긴다."
        ),
    )
    collections: list[VersionedCollectionSetting] = Field(
        title="버전을 남길 정의 종류",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=lambda: list(DEFAULT_COLLECTIONS),
        description="버전 기록 경로를 붙일 정의 종류 표(기본: 에이전트·팀 구성·리소스·공통 설정).",
    )
    secret_issue_codes: list[str] = Field(
        title="값을 가릴 문제 코드",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=lambda: list(DEFAULT_SECRET_ISSUE_CODES),
        description="버전 비교에서 값을 가릴 저장 전 검사 문제 코드(평문 비밀).",
    )


SETTINGS_COMPAT = SettingsCompat(
    removed=(RemovedSetting("versions", new="modules.options.mod-versions"),)
)
"""호스트 설정 호환: 옛 최상위 ``versions``는 4R.18에서 읽기 호환을 끝냈다(``settings.removed_key``
오류로 새 위치 ``modules.options.mod-versions`` 안내)."""


__all__ = [
    "DEFAULT_COLLECTIONS",
    "DEFAULT_SECRET_ISSUE_CODES",
    "SETTINGS_COMPAT",
    "VersionModuleSettings",
    "VersionedCollectionSetting",
]
