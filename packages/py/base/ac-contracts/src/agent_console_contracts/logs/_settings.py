"""로그 분석 설정(`WorkspaceSettings.logs`, design §4R.2·§4R.9 표 2).

전부 "생략 = 상속"이다. 필드를 생략하면(`model_fields_set`에 없으면) 기본값을 따른다:
출처는 디스크립터 `default_enabled`·`config_schema` 기본값, 분류 체계는 `ac-logs` 기본 분류 체계,
프로젝트 묶기는 "경로 그대로 + worktree 묶기", 대시보드는 없음. 저장·전송은
`model_dump(exclude_unset=True)`로 한다. 모르는 키는 보존한다(손으로 고친 YAML 왕복).

범주·위젯 종류·차원·지표 이름은 모두 열린 문자열이다(알려진 값은 문서 상수·디스크립터).
"""

from typing import Literal

from pydantic import ConfigDict, Field

from agent_console_contracts._base import DefinitionModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import x_ui

type LogUngroupedPolicy = Literal["cwd", "repo_root", "none"]
"""묶기 규칙에 맞지 않는 경로의 프로젝트. 동작 모드라 고정 어휘다.
cwd = 자기 경로, repo_root = 본 저장소 경로(없으면 cwd), none = 한 묶음("기타")."""


class LogCategory(DefinitionModel):
    """범주 하나의 표시 정보. 비운 항목은 기본 분류 체계 값을 따른다."""

    model_config = ConfigDict(title="로그 범주")

    label: str | None = Field(
        default=None,
        title="표시 이름",
        description="범주를 화면에 보일 이름입니다. 비우면 범주 id를 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="범주 id가 알아보기 어려울 때 쉬운 이름을 붙이세요.",
            example="도구 호출",
        ),
    )
    description: str | None = Field(
        default=None,
        title="설명",
        description="이 범주가 무엇을 뜻하는지 적습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 범주가 무엇인지 함께 보는 사람에게 알리고 싶을 때 적으세요.",
            example="에이전트가 도구를 부른 기록",
        ),
    )
    visible: bool | None = Field(
        default=None,
        title="보이기",
        description="끄면 목록·타임라인에서 기본으로 숨깁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="자주 보지 않는 범주가 목록을 어지럽힐 때 끄세요."
        ),
    )
    tone: str | None = Field(
        default=None,
        title="강조",
        description=(
            "danger면 이 범주를 오류로 표시합니다(그 밖에 warning, success, info, neutral)."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 범주를 오류처럼 눈에 띄게 하고 싶을 때 danger로 바꾸세요.",
            example="danger",
        ),
    )
    color: str | None = Field(
        default=None,
        title="색",
        description="색 이름이나 CSS 색입니다. 화면이 알아보지 못하면 기본 색입니다.",
        json_schema_extra=x_ui(tier="advanced", example="#3b82f6"),
    )


class LogTaxonomy(DefinitionModel):
    """로그 범주의 표시 이름·설명·보이기·색. 분류 체계에 없는 범주도 이름 = id로 보인다."""

    # design §4R.2. 설정 logs.taxonomy는 기본 분류 체계 위에 범주별로 덮어쓴다.
    # GET /logs/taxonomy는 병합한 유효 분류 체계를 돌려준다.

    model_config = ConfigDict(title="로그 분류 체계")

    categories: dict[str, LogCategory] = Field(
        default_factory=dict,
        title="범주",
        description="범주마다 표시 이름·설명·색·보이기를 정합니다.",
        json_schema_extra=x_ui(
            tier="basic", when="로그 범주의 이름·색·보이기를 내 방식대로 바꾸고 싶을 때 바꾸세요."
        ),
    )
    order: list[str] | None = Field(
        default=None,
        title="표시 순서",
        description="필터 칩 등에 보일 범주 순서입니다. 빠진 범주는 뒤에 이름 순으로 붙습니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="필터 칩 순서를 자주 보는 범주부터 놓고 싶을 때 바꾸세요."
        ),
    )


class LogSourceSetting(DefinitionModel):
    """로그 출처 하나의 사용 여부와 설정. 비운 항목은 출처 기본값을 따른다."""

    model_config = ConfigDict(title="로그 출처")

    id: NonEmptyStr = Field(
        title="출처",
        description="로그를 읽어 올 곳입니다(예: Claude Code 세션 로그).",
        json_schema_extra=x_ui(tier="basic", when="다른 곳의 로그를 읽고 싶을 때 고르세요."),
    )
    enabled: bool | None = Field(
        default=None,
        title="사용",
        description="이 출처를 읽을지 정합니다. 비우면 출처의 기본값을 따릅니다.",
        json_schema_extra=x_ui(
            tier="basic", when="이 출처의 로그가 필요 없거나 읽기 느릴 때 끄세요."
        ),
    )
    config: JsonObject | None = Field(
        default=None,
        title="출처 설정",
        description="출처마다 정한 설정입니다(예: 읽을 폴더, 분류 방식).",
        json_schema_extra=x_ui(
            tier="advanced", when="출처가 읽을 폴더가 기본 위치와 다를 때 바꾸세요."
        ),
    )


class LogProjectGroup(DefinitionModel):
    """경로 패턴(예: ~/work/app/**)에 맞는 로그를 한 프로젝트로 묶습니다."""

    model_config = ConfigDict(title="프로젝트 묶음")

    id: NonEmptyStr = Field(
        title="묶음 id",
        description="묶음을 가리키는 고유 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="새 묶음을 만들 때 한 번 정하세요.", example="my-app"
        ),
    )
    label: str | None = Field(
        default=None,
        title="표시 이름",
        description="화면에 보일 묶음 이름입니다. 비우면 id를 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록에서 묶음을 알아보기 쉬운 이름으로 보고 싶을 때 적으세요.",
            example="내 앱",
        ),
    )
    match: list[str] = Field(
        default_factory=list,
        title="경로 글롭",
        description=(
            "저장소 경로(없으면 작업 폴더)와 맞춰 봅니다. 하위 폴더까지는 /proj/** 처럼 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="다른 폴더의 로그도 이 묶음에 넣고 싶을 때 더하세요.",
            example=["/home/me/app/**"],
        ),
    )


class LogProjectSettings(DefinitionModel):
    """로그를 프로젝트별로 묶는 규칙. 바꾸면 바로 반영된다(다시 수집할 필요 없음)."""

    # design §4R.6. 질의 때 적용한다(group_projects).

    model_config = ConfigDict(title="프로젝트 묶기")

    groups: list[LogProjectGroup] | None = Field(
        default=None,
        title="묶음",
        description="경로로 로그를 묶는 규칙입니다. 위에서부터 보고 처음 맞는 묶음이 이깁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="여러 폴더의 로그를 한 프로젝트로 묶어 보고 싶을 때 더하세요."
        ),
    )
    ungrouped: LogUngroupedPolicy | None = Field(
        default=None,
        title="묶음 밖 경로",
        description=(
            "맞는 묶음이 없으면 자기 경로(cwd), 저장소(repo_root), 기타 한 묶음(none)으로 둡니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={
                "cwd": "작업 폴더로 묶기",
                "repo_root": "저장소 루트로 묶기",
                "none": "묶지 않기",
            },
            tier="advanced",
            when="묶음에 들지 않은 로그를 한곳에 모으고 싶을 때 none으로 바꾸세요.",
        ),
    )
    git_worktrees: bool | None = Field(
        default=None,
        title="worktree 묶기",
        description="git worktree 폴더를 원래 저장소와 한 묶음으로 봅니다. 기본은 켬입니다.",
        json_schema_extra=x_ui(tier="advanced", when="worktree마다 따로 보고 싶을 때 끄세요."),
    )


class LogWidgetQuery(DefinitionModel):
    """위젯이 보일 집계: 나눌 차원, 지표, 필터."""

    # design §4R.6. 차원·지표·필터 이름은 열린 문자열이다.

    model_config = ConfigDict(title="위젯 질의")

    group_by: list[str] = Field(
        default_factory=list,
        title="차원",
        description="집계를 나눌 기준입니다(예: 도구, 모델).",
        json_schema_extra=x_ui(
            tier="basic",
            when="집계를 다른 기준(예: 모델)으로 나눠 보고 싶을 때 바꾸세요.",
            example=["tool"],
        ),
    )
    metric: NonEmptyStr = Field(
        title="지표",
        description="셀 값입니다(예: events = 이벤트 수, tokens.total = 토큰 합계).",
        json_schema_extra=x_ui(
            tier="basic",
            when="이벤트 수 대신 토큰 등 다른 값을 보고 싶을 때 바꾸세요.",
            example="events",
        ),
    )
    filter: JsonObject = Field(
        default_factory=dict,
        title="필터",
        description="거를 조건입니다(필터 이름 → 값). 기간은 절대 시각으로 저장됩니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class LogWidget(DefinitionModel):
    """대시보드 위젯 하나."""

    # kind는 웹 위젯 레지스트리 id(X21, 열린 문자열). 격자 크기는 좌표 없이 options.w·options.h.

    model_config = ConfigDict(title="위젯")

    id: NonEmptyStr = Field(
        title="위젯 id",
        description="대시보드 안에서 위젯을 가리키는 고유 이름입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    kind: NonEmptyStr = Field(
        title="종류",
        description="위젯 모양입니다(예: 표, 막대). 모르는 종류는 표로 보입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="표 대신 막대 등 다른 모양으로 보고 싶을 때 바꾸세요."
        ),
    )
    title: str | None = Field(
        default=None,
        title="제목",
        description="위젯 위에 보일 제목입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="위젯이 무엇을 보이는지 제목으로 알리고 싶을 때 적으세요.",
            example="도구별 호출 수",
        ),
    )
    query: LogWidgetQuery = Field(
        title="질의",
        description="위젯이 보일 집계입니다.",
        json_schema_extra=x_ui(tier="basic", when="위젯이 보일 값을 바꾸고 싶을 때 바꾸세요."),
    )
    options: JsonObject = Field(
        default_factory=dict,
        title="표시 옵션",
        description="w·h는 격자 칸 수입니다(비우면 기본 크기). 나머지는 위젯 종류가 읽습니다.",
        json_schema_extra=x_ui(tier="advanced", example={"w": 2, "h": 1}),
    )


class LogDashboard(DefinitionModel):
    """위젯을 모은 로그 대시보드."""

    # 설정 logs.dashboards, 템플릿 GET /logs/dashboard-templates.

    model_config = ConfigDict(title="대시보드")

    id: NonEmptyStr = Field(
        title="대시보드 id",
        description="대시보드를 가리키는 고유 이름입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    title: NonEmptyStr = Field(
        title="제목",
        description="대시보드 목록에 보일 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="대시보드 목록에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="이번 주 사용량",
        ),
    )
    widgets: list[LogWidget] = Field(
        default_factory=list,
        title="위젯",
        description="대시보드에 놓인 위젯입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="대시보드에 보일 집계를 더하거나 빼고 싶을 때 바꾸세요."
        ),
    )


class LogSettings(DefinitionModel):
    """읽을 로그 출처, 범주 표시, 프로젝트 묶기, 대시보드. 비운 항목은 기본값을 따른다."""

    model_config = ConfigDict(title="로그 설정")

    sources: list[LogSourceSetting] | None = Field(
        default=None,
        title="출처",
        description="출처마다 켜고 끄며 설정합니다. 목록에 없는 출처는 출처 기본값을 따릅니다.",
        json_schema_extra=x_ui(
            tier="basic", when="다른 로그 폴더를 읽거나 필요 없는 출처를 끄고 싶을 때 바꾸세요."
        ),
    )
    taxonomy: LogTaxonomy | None = Field(
        default=None,
        title="분류 체계",
        description="범주별 표시 이름·색·보이기를 기본값 위에 덮어씁니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="로그 범주 이름·색이 알아보기 어려울 때 바꾸세요."
        ),
    )
    projects: LogProjectSettings | None = Field(
        default=None,
        title="프로젝트 묶기",
        description="로그를 경로에 따라 프로젝트별로 묶는 규칙입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="로그를 프로젝트별로 묶어 보고 싶을 때 바꾸세요."
        ),
    )
    dashboards: list[LogDashboard] | None = Field(
        default=None,
        title="대시보드",
        description="위젯을 모은 로그 대시보드입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


__all__ = [
    "LogCategory",
    "LogDashboard",
    "LogProjectGroup",
    "LogProjectSettings",
    "LogSettings",
    "LogSourceSetting",
    "LogTaxonomy",
    "LogUngroupedPolicy",
    "LogWidget",
    "LogWidgetQuery",
]
